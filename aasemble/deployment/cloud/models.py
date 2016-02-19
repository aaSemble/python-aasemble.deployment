class NamedSet(dict):
    def add(self, item):
        self[item.name] = item

    def __sub__(self, other):
        diff_keys = set(self.keys()) - set(other.keys())
        difference = self.__class__()
        for key in diff_keys:
            difference[key] = self[key]
        return difference

    def __eq__(self, other):
        return set(self.values()) == other

    def __iter__(self):
        return iter(self.values())

    def __contains__(self, item):
        return item in self.values()


class Collection(object):
    def __init__(self, nodes=None, security_groups=None, security_group_rules=None):
        self.nodes = nodes or NamedSet()
        self.security_groups = security_groups or NamedSet()
        self.security_group_rules = security_group_rules or set()

    def __sub__(self, other):
        diff = self.__class__()
        diff.nodes = self.nodes - other.nodes
        diff.security_groups = self.security_groups - other.security_groups
        diff.security_group_rules = self.security_group_rules - other.security_group_rules
        return diff

    def connect(self):
        for node in self.nodes:
            for security_group_name in node.security_group_names:
                node.security_groups.add(self.security_groups[security_group_name])


class CloudModel(object):
    def __eq__(self, other):
        return all([getattr(self, attr) == getattr(other, attr) for attr in self.id_attrs])

    def __hash__(self):
        retval = 0
        for attr in self.id_attrs:
            retval ^= hash(getattr(self, attr))
        return retval


class Node(CloudModel):
    def __init__(self, name, flavor, image, networks, disk, export, security_groups=None, runner=None, keypair=None, userdata=None, attempts_left=1):
        self.name = name
        self.flavor = flavor
        self.image = image
        self.networks = networks
        self.disk = disk
        self.export = export
        self.security_groups = security_groups or set()
        self.runner = runner
        self.keypair = keypair
        self.userdata = userdata
        self.attempts_left = attempts_left

        self.server_id = None
        self.fips = set()
        self.ports = []
        self.server_status = None

    id_attrs = ('name', 'flavor', 'image', 'disk', 'export')

    def __repr__(self):
        return "<Node name='%s'>" % (self.name,)

    def __eq__(self, other):
        return super(Node, self).__eq__(other) and (stringify(self.security_groups) == stringify(other.security_groups))

    def __hash__(self):
        return super(Node, self).__hash__() ^ hash(stringify(self.security_groups))

    @property
    def mapped_flavor(self):
        if self.runner is None:
            return self.flavor
        return self.runner.mappings.get('flavors', {}).get(self.flavor, self.flavor)

    @property
    def mapped_image(self):
        if self.runner is None:
            return self.image
        return self.runner.mappings.get('images', {}).get(self.image, self.image)

    def poll(self, desired_status='ACTIVE'):
        return self.runner.cloud_driver.poll_server(self, desired_status)

    def clean(self):
        return self.runner.cloud_driver.clean_server(self)

    def build(self):
        return self.runner.cloud_driver.build_server(self)

    @property
    def floating_ip(self):
        for port in self.ports:
            if 'floating_ip' in port:
                return port['floating_ip']


class Network(object):
    pass


class FloatingIP(CloudModel):
    def __init__(self, id, ip_address):
        self.id = id
        self.ip_address = ip_address

    def __repr__(self):
        return "<FloatingIP id='%s' ip_address='%s'>" % (self.id, self.ip_address)

    id_attrs = ('id', 'ip_address')


class SecurityGroup(CloudModel):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<SecurityGroup name='%s'>" % (self.name,)

    id_attrs = ('name',)


class SecurityGroupRule(CloudModel):
    def __init__(self, security_group, source_ip, from_port, to_port, protocol):
        self.security_group = security_group
        self.source_ip = source_ip
        self.from_port = from_port
        self.to_port = to_port
        self.protocol = protocol

    def __repr__(self):
        return ("<SecurityGroupRule source_ip='%s', from_port=%d, to_port=%d, protocol='%s'>" %
                (self.source_ip, self.from_port, self.to_port, self.protocol))

    id_attrs = ('security_group', 'source_ip', 'from_port', 'to_port', 'protocol')


def stringify(security_groups):
    l = list([sg.name for sg in security_groups])
    l.sort()
    return ' '.join(l)
