class Node(object):
    def __init__(self, name, flavor, image, networks, disk, export, runner, keypair=None, userdata=None, attempts_left=1):
        self.name = name
        self.flavor_name = flavor
        self.image_name = image
        self.networks = networks
        self.disk = disk
        self.export = export
        self.runner = runner
        self.keypair = keypair
        self.userdata = userdata
        self.attempts_left = attempts_left

        self.server_id = None
        self.fips = set()
        self.flavor = None
        self.image = None
        self.ports = []
        self.server_status = None

    @property
    def mapped_flavor_name(self):
        if self.runner is None:
            return self.flavor_name
        return self.runner.mappings.get('flavors', {}).get(self.flavor_name, self.flavor_name)

    @property
    def mapped_image_name(self):
        if self.runner is None:
            return self.image_name
        return self.runner.mappings.get('images', {}).get(self.image_name, self.image_name)

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


class FloatingIP(object):
    def __init__(self, id, ip_address):
        self.id = id
        self.ip_address = ip_address

    def __repr__(self):
        return "<FloatingIP id='%s' ip_address='%s'>" % (self.id, self.ip_address)

    def __eq__(self, other):
        return (self.id == other.id) and (self.ip_address == other.ip_address)

    def __hash__(self):
        return hash(self.id) ^ hash(self.ip_address)


class SecurityGroup(object):
    pass
