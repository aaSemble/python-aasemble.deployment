import time

class Node(object):
    def __init__(self, name, info, runner, keypair=None, userdata=None):
        self.name = name
        self.info = info
        self.runner = runner
        self.keypair = keypair
        self.userdata = userdata
        self.server_id = None
        self.fip_ids = set()
        self.ports = []
        self.server_status = None
        self.image = None
        self.flavor = None
        self.attempts_left = runner.retry_count + 1

        if self.info.get('image') in self.runner.mappings.get('images', {}):
            self.info['image'] = self.runner.mappings['images'][self.info['image']]

        if self.info.get('flavor') in self.runner.mappings.get('flavors', {}):
            self.info['flavor'] = self.runner.mappings['flavors'][self.info['flavor']]

    def poll(self, desired_status='ACTIVE'):
        """
        This one poll nova and return the server status
        """
        if self.server_status != desired_status:
            self.server_status = self.runner.cloud_driver.get_nova_client().servers.get(self.server_id).status
        return self.server_status

    def clean(self):
        """
        Cleaner: This method remove server, fip, port etc.
        We could keep fip and may be ports (ports are getting deleted with current
        neutron client), but that is going to be bit more complex to make sure
        right port is assigned to right fip etc, so atm, just removing them.
        """
        for fip_id in self.fip_ids:
            self.runner.delete_floatingip(fip_id)
        self.fip_ids = set()

        for port in self.ports:
            self.runner.delete_port(port['id'])
        self.ports = []

        self.runner.delete_server(self.server_id)
        self.server_id = None

    def create_nics(self, networks):
        nics = []
        for eth_idx, network in enumerate(networks):
            port_name = '%s_eth%d' % (self.name, eth_idx)
            port_info = self.runner.create_port(port_name, network['network'],
                                                [self.runner.secgroups[secgroup] for secgroup in network.get('securitygroups', [])])
            self.ports.append(port_info)

            if network.get('assign_floating_ip', False):
                fip_id, fip_address = self.runner.create_floating_ip()
                self.runner.associate_floating_ip(port_info['id'], fip_id)
                port_info['floating_ip'] = fip_address
                self.fip_ids.add(fip_id)

            nics.append(port_info['id'])
        return nics

    def build(self):
        if self.flavor is None:
            self.flavor = self.runner.cloud_driver.get_flavor(self.info['flavor'])

        nics = [{'port-id': port_id} for port_id in self.create_nics(self.info['networks'])]

        volume = self.runner.create_volume(size=self.info['disk'],
                                           image_ref=self.info['image'])

        while volume.status != 'available':
            time.sleep(3)
            volume = self.runner.cloud_driver.get_volume(volume.id)

        bdm = {'vda': '%s:::1' % (volume.id,)}

        server = self.runner.cloud_driver.create_server(name=self.name, image=None,
                                                        block_device_mapping=bdm,
                                                        flavor=self.flavor, nics=nics,
                                                        key_name=self.keypair, userdata=self.userdata)
        self.server_id = server.id
        self.attempts_left -= 1

    @property
    def floating_ip(self):
        for port in self.ports:
            if 'floating_ip' in port:
                return port['floating_ip']




class Network(object):
    pass


class FloatingIP(object):
    pass


class SecurityGroup(object):
    pass
