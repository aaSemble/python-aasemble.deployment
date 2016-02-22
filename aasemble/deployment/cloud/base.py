class CloudDriver(object):
    def __init__(self, record_resource, mappings=None, pool=None):
        self.record_resource = record_resource
        self.mappings = mappings or {}
        self.pool = pool
        self.secgroups = {}

    def create_floating_ip(name):
        raise NotImplementedError()

    def create_keypair(self, name, keydata, retry_count):
        raise NotImplementedError()

    def create_network(self, name, info, mappings):
        raise NotImplementedError()

    def create_port(self, name, network, network_id, secgroups):
        raise NotImplementedError()

    def create_security_group(self, base_name, name, info, secgroups):
        raise NotImplementedError()

    def create_volume(self, size, image_ref, retry_count):
        raise NotImplementedError()

    def get_floating_ips(self):
        raise NotImplementedError()

    def get_networks(self):
        raise NotImplementedError()

    def get_ports(self):
        raise NotImplementedError()

    def get_security_groups(self):
        raise NotImplementedError()

    def get_servers(self):
        raise NotImplementedError()

    def delete_floatingip(self, uuid):
        raise NotImplementedError()

    def delete_keypair(self, name):
        raise NotImplementedError()

    def delete_network(self, uuid):
        raise NotImplementedError()

    def delete_port(self, uuid):
        raise NotImplementedError()

    def delete_volume(self, uuid):
        raise NotImplementedError()

    def delete_router(self, uuid):
        raise NotImplementedError()

    def delete_secgroup(self, uuid):
        raise NotImplementedError()

    def delete_secgroup_rule(self, uuid):
        raise NotImplementedError()

    def delete_subnet(self, uuid):
        raise NotImplementedError()

    def associate_floating_ip(self, port_id, fip_id):
        raise NotImplementedError()

    def build_server(self, server):
        raise NotImplementedError()

    def poll_server(self, server):
        raise NotImplementedError()

    def clean_server(self, server):
        raise NotImplementedError()

    def apply_mappings(self, obj_type, name):
        return self.mappings.get(obj_type, {}).get(name, name)
