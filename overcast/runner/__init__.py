#!/usr/bin/env python
#
#   Copyright 2015 Reliance Jio Infocomm, Ltd.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
import ConfigParser
import logging
import os
import select
import subprocess
import sys
import time
import yaml

from overcast import utils
from overcast import exceptions

def load_yaml(f='.overcast.yaml'):
    with open(f, 'r') as fp:
        return yaml.load(fp)

def load_mappings(f='.overcast.mappings.ini'):
    with open(f, 'r') as fp:
        parser = ConfigParser.SafeConfigParser()
        parser.readfp(fp)
        mappings = {}
        for t in ('flavors', 'networks', 'images'):
            mappings[t] = {}
            if parser.has_section(t):
                mappings[t].update(parser.items(t))

        return mappings

def find_weak_refs(stack):
    images = set()
    flavors = set()
    networks = set()
    for node_name, node in stack['nodes'].items():
        images.add(node['image'])
        flavors.add(node['flavor'])
        networks.update([n['network'] for n in node['nics']])

    dynamic_networks = set()
    for network_name, network in stack.get('networks', {}).items():
        dynamic_networks.add(network_name)

    return images, flavors, networks-dynamic_networks

def list_refs(args, stdout=sys.stdout):
    stack = load_yaml(args.stack)
    images, flavors, networks = find_weak_refs(stack)
    if args.tmpl:
        cfg = ConfigParser.SafeConfigParser()
        cfg.add_section('images')
        cfg.add_section('flavors')
        for image in images:
            cfg.set('images', image, '<missing value>')
        for flavor in flavors:
            cfg.set('flavors', flavor, '<missing value>')
        cfg.write(stdout)
    else:
        stdout.write('Images:\n  ')

        if images:
            stdout.write('  '.join(images))
        else:
            stdout.write('None')

        stdout.write('\n\nFlavors:\n  ')

        if flavors:
            stdout.write('  '.join(flavors))
        else:
            stdout.write('None')

        stdout.write('\n')

def shell_step_cmd(details):
    if details.get('type', None) == 'remote':
         node = self.nodes[details['node']]
         return 'ssh -o StrictHostKeyChecking=no ubuntu@%s bash' % (node)
    else:
         return 'bash'

def run_cmd_once(shell_cmd, real_cmd, environment, deadline):
    proc = subprocess.Popen(shell_cmd,
                            env=environment,
                            shell=True,
                            stdin=subprocess.PIPE)
    stdin = real_cmd + '\n'
    while True:
        if stdin:
            _, rfds, xfds = select.select([], [proc.stdin], [proc.stdin], 1)
            if rfds:
                proc.stdin.write(stdin[0])
                stdin = stdin[1:]
                if not stdin:
                    proc.stdin.close()
            if xfds:
                if proc.stdin.feof():
                    stdin = ''

        if proc.poll() is not None:
            if proc.returncode == 0:
                return True
            else:
                raise exceptions.CommandFailedException(stdin)

        if deadline and time.time() > deadline:
            if proc.poll() is None:
                proc.kill()
            raise exceptions.CommandTimedOutException(stdin)


def shell_step(details, environment=None, args=None, mappings=None):
    cmd = shell_step_cmd(details)

    if details.get('total-timeout', False):
        overall_deadline = time.time() + utils.parse_time(details['total-timeout'])
    else:
        overall_deadline = None

    if details.get('timeout', False):
        individual_exec_limit = utils.parse_time(details['timeout'])
    else:
        individual_exec_limit = None

    if details.get('retry-delay', False):
        retry_delay = utils.parse_time(details['retry-delay'])
    else:
        retry_delay = 0

    def wait():
        time.sleep(retry_delay)

    # Four settings matter here:
    # retry-if-fails: True/False
    # retry-delay: Time to wait between retries
    # timeout: Max time per command execution
    # total-timeout: How long time to spend on this in total
    while True:
        if individual_exec_limit:
            deadline = time.time() + individual_exec_limit
            if overall_deadline:
                if deadline > overall_deadline:
                    deadline = overall_deadline
        elif overall_deadline:
            deadline = overall_deadline
        else:
            deadline = None

        try:
            run_cmd_once(cmd, details['cmd'], environment, deadline)
            break
        except exceptions.CommandFailedException:
            if details.get('retry-if-fails', False):
                wait()
                continue
            raise
        except exceptions.CommandTimedOutException:
            if details.get('retry-if-fails', False):
                if time.time() + retry_delay < deadline:
                    wait()
                    continue
            raise

def get_creds_from_env():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    d['password'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['tenant_name'] = os.environ['OS_TENANT_NAME']
#    d['region_name'] = os.environ.get('OS_REGION_NAME')
#    d['cacert'] = os.environ.get('OS_CACERT', None)
    return d

conncache = {}
def get_keystone_session(conncache=conncache):
    from keystoneclient import session as keystone_session
    from keystoneclient.auth.identity import v2 as keystone_auth_id_v2
    if 'keystone_session' not in conncache:
        conncache['keystone_auth'] = keystone_auth_id_v2.Password(**get_creds_from_env())
        conncache['keystone_session'] = keystone_session.Session(auth=conncache['keystone_auth'])
    return conncache['keystone_session']

def get_keystone_client(conncache=conncache):
    from keystoneclient.v2_0 import client as keystone_client
    if 'keystone' not in conncache:
        ks = get_keystone_session()
        conncache['keystone'] = keystone_client.Client(session=ks)
    return conncache['keystone']

def get_nova_client(conncache=conncache):
    import novaclient.client as novaclient
    if 'nova' not in conncache:
        ks = get_keystone_session()
        conncache['nova'] = novaclient.Client("1.1", session=ks)
    return conncache['nova']

def get_neutron_client(conncache=conncache):
    import neutronclient.neutron.client as neutronclient
#    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    if 'neutron' not in conncache:
        ks = get_keystone_session()
        conncache['neutron'] = neutronclient.Client('2.0', session=ks)
    return conncache['neutron']

def delete_port(uuid):
    nc = get_neutron_client()
    nc.delete_port(uuid)

def delete_network(uuid):
    nc = get_neutron_client()
    nc.delete_network(uuid)

def delete_subnet(uuid):
    nc = get_neutron_client()
    nc.delete_subnet(uuid)

def delete_secgroup(uuid):
    nc = get_neutron_client()
    nc.delete_security_group(uuid)

def delete_secgroup_rule(uuid):
    nc = get_neutron_client()
    nc.delete_security_group_rule(uuid)

def delete_floatingip(uuid):
    nc = get_neutron_client()
    nc.delete_floatingip(uuid)

def delete_keypair(name):
    nc = get_nova_client()
    nc.keypairs.delete(name)

def delete_server(uuid):
    nc = get_nova_client()
    nc.servers.delete(uuid)

def create_port(name, network, secgroups):
    nc = get_neutron_client()
    port = {'name': name,
            'admin_state_up': True,
            'network_id': network,
            'security_groups': secgroups}
    port = nc.create_port({'port': port})
    return port['port']['id']

def create_keypair(name, path):
    nc = get_nova_client()
    with open(path, 'r') as fp:
        key = fp.read()
    nc.keypairs.create(name, key)

def find_floating_network():
    nc = get_neutron_client()
    networks = nc.list_networks(**{'router:external': True})
    return networks['networks'][0]['id']

def create_floating_ip(record_resource):
    nc = get_neutron_client()
    floating_network = find_floating_network()
    floatingip = {'floating_network_id': floating_network}
    floatingip = nc.create_floatingip({'floatingip': floatingip})
    record_resource('floatingip', floatingip['floatingip']['id'])
    return floatingip['floatingip']['id']

def associate_floating_ip(port_id, fip_id):
    nc = get_neutron_client()
    nc.update_floatingip(fip_id, {'floatingip': {'port_id': port_id}})

def create_network(name, info, record_resource):
    nc = get_neutron_client()
    network = {'name': name, 'admin_state_up': True}
    network = nc.create_network({'network': network})
    record_resource('network', network['network']['id'])

    subnet = {"network_id": network['network']['id'],
              "ip_version": 4,
              "cidr": info['cidr'],
              "name": name}
    subnet = nc.create_subnet({'subnet': subnet})
    record_resource('subnet', subnet['subnet']['id'])

    return network['network']['id']

def create_security_group(name, info, record_resource):
    nc = get_neutron_client()
    secgroup = {'name': name}
    secgroup = nc.create_security_group({'security_group': secgroup})
    record_resource('secgroup', secgroup['security_group']['id'])

    for rule in (info or []):
        secgroup_rule = {"direction": "ingress",
                         "remote_ip_prefix": rule['cidr'],
                         "ethertype": "IPv4",
                         "port_range_min": rule['from_port'],
                         "port_range_max": rule['to_port'],
                         "protocol": rule['protocol'],
                         "security_group_id": secgroup['security_group']['id']}
        secgroup_rule = nc.create_security_group_rule({'security_group_rule': secgroup_rule})
        record_resource('secgroup_rule', secgroup_rule['security_group_rule']['id'])
    return secgroup['security_group']['id']

def create_node(name, info, networks, secgroups,
                mappings, keypair, userdata, record_resource):
    nc = get_nova_client()

    if info['image'] in mappings.get('images', {}):
        info['image'] = mappings['images'][info['image']]

    if info['flavor'] in mappings.get('flavors', {}):
        info['flavor'] = mappings['flavors'][info['flavor']]

    image = nc.images.get(info['image'])
    flavor = nc.flavors.get(info['flavor'])

    def _map_network(network):
        if network in mappings.get('networks', {}):
            netid = mappings['networks'][network]
        elif network in networks:
            netid = networks[network]
        else:
            netid = network

        return netid

    nics = []
    for eth_idx, network in enumerate(info['networks']):
       port_name = '%s_eth%d' % (name, eth_idx)
       port_id = create_port(port_name, _map_network(network['network']),
                             [secgroups[secgroup] for secgroup in network.get('secgroups', [])])
       record_resource('port', port_id)

       if network.get('assign_floating_ip', False):
           fip_id = create_floating_ip(record_resource)
           associate_floating_ip(port_id, fip_id)

       nics.append({'port-id': port_id})

    bdm = [{'source_type': 'image',
            'uuid': info['image'],
            'destination_type': 'volume',
            'volume_size': info['disk'],
            'delete_on_termination': 'true',
            'boot_index': '0'}]
    server = nc.servers.create(name, image=None,
                               block_device_mapping_v2=bdm,
                               flavor=flavor, nics=nics,
                               key_name=keypair, userdata=userdata)
    record_resource('server', server.id)
    return server.id

def provision_step(details, args, mappings):
    stack = load_yaml(details['stack'])
    networks = {}
    secgroups = {}
    nodes = {}

    def _add_prefix(s):
        if args.prefix:
            return '%s_%s' % (args.prefix, s)
        else:
            return s

    if args.cleanup:
        cleanup = open(args.cleanup, 'a+')
        def record_resource(typ, id):
            cleanup.write('%s: %s\n' % (typ, id))
    else:
        def record_resource(typ, id):
            pass

    if args.key:
        keypair_name = _add_prefix('pubkey')
        create_keypair(keypair_name, args.key)
        record_resource('keypair', keypair_name)
    else:
        keypair_name = None

    if 'userdata' in details:
        with open(details['userdata'], 'r') as fp:
            userdata = fp.read()
    else:
        userdata = None

    for base_network_name, network_info in stack['networks'].items():
        network_name = _add_prefix(base_network_name)
        networks[base_network_name] = create_network(network_name,
                                                     network_info,
                                                     record_resource)

    for base_secgroup_name, secgroup_info in stack['securitygroups'].items():
        secgroup_name = _add_prefix(base_secgroup_name)
        secgroups[base_secgroup_name] = create_security_group(secgroup_name,
                                                              secgroup_info,
                                                              record_resource)

    for base_node_name, node_info in stack['nodes'].items():
        def _create_node(base_name):
            node_name = _add_prefix(base_name)
            nodes[base_name] = create_node(node_name, node_info,
                                           networks=networks,
                                           secgroups=secgroups,
                                           mappings=mappings,
                                           keypair=keypair_name,
                                           userdata=userdata,
                                           record_resource=record_resource)

        if 'number' in node_info:
            count = node_info.pop('number')
            for idx in range(1, count+1):
                _create_node('%s%d' % (base_node_name, idx))
        else:
            _create_node(base_node_name)


def deploy(args, stdout=sys.stdout):
    cfg = load_yaml(args.cfg)
    if args.mappings:
        mappings = load_mappings(args.mappings)
    else:
        mappings = {'images': {},
                    'networks': {},
                    'flavors': {}}
    for step in cfg[args.name]:
        step_type = step.keys()[0]
        details = step[step_type]
        func = globals()['%s_step' % step_type]
        func(details, args=args, mappings=mappings)

def cleanup(args, stdout=sys.stdout):
    with open(args.log, 'r') as fp:
        lines = [l.strip() for l in fp]

    lines.reverse()
    for l in lines:
        resource_type, uuid = l.split(': ')
        func = globals()['delete_%s' % resource_type]
        try:
            func(uuid)
        except:
            pass


def main(argv=sys.argv[1:], stdout=sys.stdout):
    parser = argparse.ArgumentParser(description='Run deployment')

    subparsers = parser.add_subparsers(help='Subcommand help')
    list_refs_parser = subparsers.add_parser('list-refs',
                                             help='List symbolic resources')
    list_refs_parser.set_defaults(func=list_refs)
    list_refs_parser.add_argument('--tmpl', action='store_true',
                                  help='Output template ini file')
    list_refs_parser.add_argument('stack', help='YAML file describing stack')

    deploy_parser = subparsers.add_parser('deploy', help='Perform deployment')
    deploy_parser.set_defaults(func=deploy)
    deploy_parser.add_argument('--cfg', default='.overcast.yaml',
                               help='Deployment config file')
    deploy_parser.add_argument('--prefix', help='Resource name prefix')
    deploy_parser.add_argument('--mappings', help='Resource map file')
    deploy_parser.add_argument('--key', help='Public key file')
    deploy_parser.add_argument('--cleanup', help='Cleanup file')
    deploy_parser.add_argument('name', help='Deployment to perform')

    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up')
    cleanup_parser.set_defaults(func=cleanup)
    cleanup_parser.add_argument('log', help='Clean up log (generated by deploy)')

    args = parser.parse_args(argv)

    if args.func:
        args.func(args)

if __name__ == '__main__':
    main()
