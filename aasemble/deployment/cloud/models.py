class NamedSet(dict):
    def add(self, item):
        self[item.name] = item

    def remove(self, item=None, name=None):
        if item is not None:
            del self[item.name]
            return

        if name is not None:
            del self[name]
            return

        raise TypeError('Must pass either item or name')

    def __sub__(self, other):
        diff_keys = set(self.keys()) - set(other.keys())
        difference = self.__class__()
        for key in diff_keys:
            difference[key] = self[key]
        return difference

    def __eq__(self, other):
        if type(other) == NamedSet:
            return set(self.values()) == set(other.values())
        return set(self.values()) == other

    def __ne__(self, other):
        return not (self == other)

    def __iter__(self):
        return iter(self.values())

    def __contains__(self, item):
        return item in self.values()


class Collection(object):
    def __init__(self, nodes=None, security_groups=None, security_group_rules=None, urls=None, containers=None, tasks=None):
        self.nodes = nodes or NamedSet()
        self.security_groups = security_groups or NamedSet()
        self.security_group_rules = security_group_rules or set()
        self.urls = urls or []
        self.containers = containers or []
        self.tasks = tasks or []
        self.original_collection = None

    def __sub__(self, other):
        diff = self.__class__()
        diff.nodes = self.nodes - other.nodes
        diff.security_groups = self.security_groups - other.security_groups
        diff.security_group_rules = self.security_group_rules - other.security_group_rules
        diff.urls = self.urls
        diff.containers = self.containers
        diff.tasks = self.tasks
        diff.original_collection = self
        return diff

    def __eq__(self, other):
        return (self.nodes == other.nodes and
                self.security_groups == other.security_groups and
                self.security_group_rules == other.security_group_rules,
                self.urls == other.urls)

    def connect(self):
        for node in self.nodes:
            for security_group_name in node.security_group_names:
                if security_group_name in self.security_groups.keys():
                    node.security_groups.add(self.security_groups[security_group_name])

    def as_dict(self):
        return {'nodes': [node.as_dict() for node in self.nodes],
                'security_groups': [sg.as_dict() for sg in self.security_groups],
                'security_group_rules': [sgr.as_dict() for sgr in self.security_group_rules],
                'urls': [url.as_dict() for url in self.urls]}


class CloudModel(object):
    def __eq__(self, other):
        return all([getattr(self, attr, False) == getattr(other, attr, False) for attr in self.id_attrs])

    def __hash__(self):
        retval = 0
        for attr in self.id_attrs:
            retval ^= hash(getattr(self, attr))
        return retval


class Node(CloudModel):
    def __init__(self, name, flavor, image, networks, disk, security_groups=None, runner=None, keypair=None, script=None, attempts_left=1, private=None):
        self.name = name
        self.flavor = flavor
        self.image = image
        self.networks = networks
        self.disk = disk
        self.security_groups = security_groups or set()
        self.runner = runner
        self.keypair = keypair
        self.script = script
        self.attempts_left = attempts_left
        self.private = private

        self.server_id = None
        self.fips = set()
        self.ports = []
        self.server_status = None

    id_attrs = ('name', 'flavor', 'image', 'disk', 'script')

    def __repr__(self):
        return "<Node name='%s'>" % (self.name,)  # pragma: no cover

    def __eq__(self, other):
        return super(Node, self).__eq__(other) and (stringify(self.security_groups) == stringify(other.security_groups))

    def __hash__(self):
        return super(Node, self).__hash__() ^ hash(stringify(self.security_groups))

    def as_dict(self):
        return {'name': self.name,
                'flavor': self.flavor,
                'image': self.image,
                'disk': self.disk,
                'security_groups': [sg.name for sg in self.security_groups],
                'script': self.script,
                'public_ips': getattr(getattr(self, 'private', None), 'public_ips', [])}


class Network(object):
    pass


class URLConf(CloudModel):
    pass


class URLConfStatic(URLConf):
    def __init__(self, hostname, path, local_path):
        self.hostname = hostname
        self.path = path
        self.local_path = local_path

    def __repr__(self):  # pragma: no cover
        return "<URLConfStatic hostname='%s', path='%s', local_path='%s'>" % (self.hostname, self.path, self.local_path)

    id_attrs = ('hostname', 'path', 'local_path')

    def as_dict(self):
        return {'domain': self.hostname,
                'path': self.path}


class URLConfBackend(URLConf):
    def __init__(self, hostname, path, destination):
        self.hostname = hostname
        self.path = path
        self.destination = destination

    def __repr__(self):  # pragma: no cover
        return "<URLConfBackend hostname='%s', path='%s', destination='%s'>" % (self.hostname, self.path, self.destination)

    id_attrs = ('hostname', 'path', 'destination')

    def as_dict(self):
        return {'domain': self.hostname,
                'path': self.path,
                'destination': self.destination}


class SecurityGroup(CloudModel):
    def __init__(self, name):
        self.name = name

    def __repr__(self):  # pragma: no cover
        return "<SecurityGroup name='%s'>" % (self.name,)

    id_attrs = ('name',)

    def as_dict(self):
        return {'name': self.name}


class SecurityGroupRule(CloudModel):
    def __init__(self, security_group, from_port, to_port, protocol, source_ip=None, source_group=None, private=None):
        self.security_group = security_group
        self.source_ip = source_ip
        self.source_group = source_group
        self.from_port = from_port
        self.to_port = to_port
        self.protocol = protocol
        self.private = private

    def __repr__(self):  # pragma: no cover
        rv = '<SecurityGroupRule '

        if self.source_ip:
            rv += "source_ip='%s' " % self.source_ip
        elif self.source_group:
            rv += "source_group='%s' " % self.source_group

        if self.from_port and self.to_port:
            rv += 'from_port=%d to_port=%d ' % (self.from_port, self.to_port)

        if self.protocol:
            rv += "protocol='%s' " % (self.protocol,)

        rv += "security_group='%s'>" % self.security_group.name

        return rv

    id_attrs = ('security_group', 'source_ip', 'source_group', 'from_port', 'to_port', 'protocol')

    def as_dict(self):
        d = {'security_group': self.security_group.name,
             'protocol': self.protocol}

        if self.source_ip:
            d['source_ip'] = self.source_ip
        else:
            d['source_group'] = self.source_group

        if self.from_port:
            d['from_port'] = self.from_port
            d['to_port'] = self.to_port

        return d


def stringify(security_groups):
    l = list([sg.name for sg in security_groups])
    l.sort()
    return ' '.join(l)
