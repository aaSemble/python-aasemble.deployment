import os
import time

from neutronclient.common.exceptions import Conflict as NeutronConflict

from novaclient.exceptions import Conflict as NovaConflict

from aasemble.deployment.cloud import models
from aasemble.deployment.cloud.base import CloudDriver


def get_creds_from_env():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    d['password'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['tenant_name'] = os.environ['OS_TENANT_NAME']
    return d


class OpenStackDriver(CloudDriver):
    def create_floating_ip(self):
        nc = self._get_neutron_client()
        floating_network = self._find_floating_network()
        floatingip = {'floating_network_id': floating_network}
        floatingip = nc.create_floatingip({'floatingip': floatingip})
        self.record_resource('floatingip', floatingip['floatingip']['id'])
        return models.FloatingIP(id=floatingip['floatingip']['id'],
                                 ip_address=floatingip['floatingip']['floating_ip_address'])

    def create_keypair(self, name, keydata, retry_count):
        nc = self._get_nova_client()
        attempts_left = retry_count + 1
        while attempts_left > 0:
            try:
                nc.keypairs.create(name, keydata)
                self.record_resource('keypair', name)
                break
            except NovaConflict:
                return
            except Exception as e:
                if attempts_left == 0:
                    raise
                print(e)
                attempts_left -= 1

    def create_network(self, name, info, mappings):
        nc = self._get_neutron_client()
        network = {'name': name, 'admin_state_up': True}
        network = nc.create_network({'network': network})
        self.record_resource('network', network['network']['id'])

        subnet = {"network_id": network['network']['id'],
                  "ip_version": 4,
                  "cidr": info['cidr'],
                  "name": name}
        subnet = nc.create_subnet({'subnet': subnet})['subnet']
        self.record_resource('subnet', subnet['id'])

        if '*' in mappings.get('routers', {}):
            nc.add_interface_router(mappings['routers']['*'], {'subnet_id': subnet['id']})

        return network['network']['id']

    def create_port(self, name, network, network_id, secgroups):
        nc = self._get_neutron_client()
        port = {'name': name,
                'admin_state_up': True,
                'network_id': network_id,
                'security_groups': secgroups}
        port = nc.create_port({'port': port})['port']
        self.record_resource('port', port['id'])
        return {'id': port['id'],
                'fixed_ip': port['fixed_ips'][0]['ip_address'],
                'mac': port['mac_address'],
                'network_name': network}

    def create_security_group(self, base_name, name, info, secgroups):
        nc = self._get_neutron_client()

        secgroup = {'name': name}
        secgroup = nc.create_security_group({'security_group': secgroup})['security_group']

        self.record_resource('secgroup', secgroup['id'])
        secgroups[base_name] = secgroup['id']

        for rule in (info or []):
            secgroup_rule = {"direction": "ingress",
                             "ethertype": "IPv4",
                             "port_range_min": rule['from_port'],
                             "port_range_max": rule['to_port'],
                             "protocol": rule['protocol'],
                             "security_group_id": secgroup['id']}

            if 'source_group' in rule:
                secgroup_rule['remote_group_id'] = secgroups.get(rule['source_group'], rule['source_group'])
            else:
                secgroup_rule['remote_ip_prefix'] = rule['cidr']

            secgroup_rule = nc.create_security_group_rule({'security_group_rule': secgroup_rule})
            self.record_resource('secgroup_rule', secgroup_rule['security_group_rule']['id'])

    def create_volume(self, size, image_ref, retry_count):
        cc = self._get_cinder_client()
        attempts_left = retry_count + 1
        while attempts_left > 0:
            try:
                volume = cc.volumes.create(size=size,
                                           imageRef=image_ref)
                self.record_resource('volume', volume.id)
                return volume
            except Exception as e:
                if attempts_left == 0:
                    raise
                print(e)
                attempts_left -= 1

    def get_floating_ips(self):
        return self._get_neutron_client().list_floatingips()['floatingips']

    def get_networks(self):
        return self._get_neutron_client().list_networks()['networks']

    def get_ports(self):
        return self._get_neutron_client().list_ports()['ports']

    def get_security_groups(self):
        return self._get_neutron_client().list_security_groups()['security_groups']

    def get_servers(self):
        return self._get_nova_client().servers.list()

    def delete_floatingip(self, fip):
        nc = self._get_neutron_client()
        nc.delete_floatingip(fip.id)

    def delete_keypair(self, name):
        nc = self._get_nova_client()
        nc.keypairs.delete(name)

    def delete_network(self, uuid):
        self._get_neutron_client().delete_network(uuid)

    def delete_port(self, uuid):
        self._get_neutron_client().delete_port(uuid)

    def delete_router(self, uuid):
        self._get_neutron_client().delete_router(uuid)

    def delete_volume(self, uuid):
        cc = self._get_cinder_client()
        cc.volumes.delete(uuid)

    def delete_secgroup(self, uuid):
        self._get_neutron_client().delete_security_group(uuid)

    def delete_secgroup_rule(self, uuid):
        nc = self._get_neutron_client()
        nc.delete_security_group_rule(uuid)

    def delete_subnet(self, uuid):
        nc = self._get_neutron_client()
        try:
            nc.delete_subnet(uuid)
        except NeutronConflict:
            # This is probably due to the router port. Let's find it.
            router_found = False
            for port in nc.list_ports(device_owner='network:router_interface')['ports']:
                for fixed_ip in port['fixed_ips']:
                    if fixed_ip['subnet_id'] == uuid:
                        router_found = True
                        nc.remove_interface_router(port['device_id'],
                                                   {'subnet_id': uuid})
                        break
            if router_found:
                # Let's try again
                nc.delete_subnet(uuid)
            else:
                # Ok, we didn't find a router, so clearly this is a different
                # problem. Just re-raise the original exception.
                raise

    def associate_floating_ip(self, port_id, fip):
        nc = self._get_neutron_client()
        nc.update_floatingip(fip.id, {'floatingip': {'port_id': port_id}})

    def build_server(self, server):
        if server.flavor is None:
            server.flavor = self._get_flavor(server.mapped_flavor_name)

        nics = [{'port-id': port_id} for port_id in self._create_nics(server, server.networks)]

        volume = self.create_volume(size=server.disk,
                                    image_ref=server.image, retry_count=3)

        while volume.status != 'available':
            time.sleep(3)
            volume = self._get_volume(volume.id)

        bdm = {'vda': '%s:::1' % (volume.id,)}

        server_info = self._create_server(name=server.name, image=None,
                                         block_device_mapping=bdm,
                                         flavor=server.flavor, nics=nics,
                                         key_name=server.keypair, userdata=server.userdata)
        server.server_id = server_info.id
        server.attempts_left -= 1

    def poll_server(self, server, desired_status='ACTIVE'):
        """
        This one poll nova and return the server status
        """
        if server.server_status != desired_status:
            server.server_status = self._get_nova_client().servers.get(server.server_id).status
        return server.server_status

    def clean_server(self, server):
        """
        Cleaner: This method remove server, fip, port etc.
        We could keep fip and may be ports (ports are getting deleted with current
        neutron client), but that is going to be bit more complex to make sure
        right port is assigned to right fip etc, so atm, just removing them.
        """
        for fip in server.fips:
            self.delete_floatingip(fip)
        server.fips = set()

        for port in server.ports:
            self.delete_port(port['id'])
        server.ports = []

        self._delete_server(server.server_id)
        server.server_id = None

    def _find_floating_network(self):
        nc = self._get_neutron_client()
        networks = nc.list_networks(**{'router:external': True})
        return networks['networks'][0]['id']

    def _delete_server(self, uuid):
        nc = self._get_nova_client()
        nc.servers.delete(uuid)

    def _get_flavor(self, name):
        return self._get_nova_client().flavors.get(name)

    def _get_volume(self, id):
        return self._get_cinder_client().volumes.get(id)

    def _create_server(self, name, image, block_device_mapping,
                      flavor, nics, key_name, userdata):

        server = self._get_nova_client().servers.create(name, image=image,
                                                       block_device_mapping=block_device_mapping,
                                                       flavor=flavor, nics=nics, key_name=key_name,
                                                       userdata=userdata)
        self.record_resource('server', server.id)
        return server

    def _create_nics(self, server, networks):
        nics = []
        for eth_idx, network in enumerate(networks):
            port_name = '%s_eth%d' % (server.name, eth_idx)
            port_info = self.create_port(port_name, network['network'],
                                         [self.secgroups[secgroup] for secgroup in network.get('securitygroups', [])])
            server.ports.append(port_info)

            if network.get('assign_floating_ip', False):
                fip = self.create_floating_ip()
                self.associate_floating_ip(port_info['id'], fip)
                port_info['floating_ip'] = fip.ip_address
                server.fips.add(fip)

            nics.append(port_info['id'])
        return nics

    def _get_keystone_session(self):
        from keystoneclient import session as keystone_session
        from keystoneclient.auth.identity import v2 as keystone_auth_id_v2
        if 'keystone_session' not in self.conncache:
            self.conncache['keystone_auth'] = keystone_auth_id_v2.Password(**get_creds_from_env())
            self.conncache['keystone_session'] = keystone_session.Session(auth=self.conncache['keystone_auth'])
        return self.conncache['keystone_session']

    def _get_nova_client(self):
        import novaclient.client as novaclient
        if 'nova' not in self.conncache:
            kwargs = {'session': self._get_keystone_session()}
            if 'OS_REGION_NAME' in os.environ:
                kwargs['region_name'] = os.environ['OS_REGION_NAME']
            self.conncache['nova'] = novaclient.Client("2", **kwargs)
        return self.conncache['nova']

    def _get_cinder_client(self):
        import cinderclient.client as cinderclient
        if 'cinder' not in self.conncache:
            kwargs = {'session': self._get_keystone_session()}
            if 'OS_REGION_NAME' in os.environ:
                kwargs['region_name'] = os.environ['OS_REGION_NAME']
            self.conncache['cinder'] = cinderclient.Client('1', **kwargs)
        return self.conncache['cinder']

    def _get_neutron_client(self):
        import neutronclient.neutron.client as neutronclient
        if 'neutron' not in self.conncache:
            kwargs = {'session': self._get_keystone_session()}
            if 'OS_REGION_NAME' in os.environ:
                kwargs['region_name'] = os.environ['OS_REGION_NAME']
            self.conncache['neutron'] = neutronclient.Client('2.0', **kwargs)
        return self.conncache['neutron']
