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
from contextlib import nested
import mock
import os.path
import unittest
from StringIO import StringIO
import yaml

import overcast.runner

yaml_data = '''---
foo:
  - bar
  - baz:
      wibble: []
'''

mappings_data = '''[images]
trusty = 7cd9416f-9167-4371-a04a-a7939c5372ab

[networks]
common = b2b2f6a6-228f-4d42-b4f7-0d340b3390e7

[flavors]
small = 34fb3740-d158-472c-8520-017278c75008
'''

class MainTests(unittest.TestCase):
    def setUp(self):
        self.dr = overcast.runner.DeploymentRunner()

    def test_load_yaml(self):
        with mock.patch('__builtin__.open') as m:
            m.return_value.__enter__.return_value = StringIO(yaml_data)
            self.assertEquals(overcast.runner.load_yaml(),
                              {'foo': ['bar', {'baz': {'wibble': []}}]})
            m.assert_called_once_with('.overcast.yaml', 'r')

    def test_load_mappings(self):
        with mock.patch('__builtin__.open') as m:
            m.return_value.__enter__.return_value = StringIO(mappings_data)
            self.assertEquals(overcast.runner.load_mappings(),
                              {'flavors': {'small': '34fb3740-d158-472c-8520-017278c75008'},
                               'images': {'trusty': '7cd9416f-9167-4371-a04a-a7939c5372ab'},
                               'networks': {'common': 'b2b2f6a6-228f-4d42-b4f7-0d340b3390e7'}})
            m.assert_called_once_with('.overcast.mappings.ini', 'r')

    def test_find_weak_refs(self):
        example_file = os.path.join(os.path.dirname(__file__),
                                    'examplestack1.yaml')
        stack = overcast.runner.load_yaml(example_file)
        self.assertEquals(overcast.runner.find_weak_refs(stack),
                          (set(['trusty']),
                           set(['bootstrap']),
                           set(['default'])))

    def test_run_cmd_once_simple(self):
        overcast.runner.run_cmd_once(shell_cmd='bash',
                                     real_cmd='true',
                                     environment={},
                                     deadline=None)

    def test_run_cmd_once_fail(self):
        self.assertRaises(overcast.exceptions.CommandFailedException,
                          overcast.runner.run_cmd_once, shell_cmd='bash',
                                                        real_cmd='false',
                                                        environment={},
                                                        deadline=None)

    def test_run_cmd_once_with_deadline(self):
        deadline = 10
        with mock.patch('overcast.runner.time') as time_mock:
            time_mock.time.return_value = 9
            overcast.runner.run_cmd_once(shell_cmd='bash',
                                         real_cmd='true',
                                         environment={},
                                         deadline=deadline)
            time_mock.time.return_value = 11
            self.assertRaises(overcast.exceptions.CommandTimedOutException,
                              overcast.runner.run_cmd_once, shell_cmd='bash',
                                                            real_cmd='true',
                                                            environment={},
                                                            deadline=deadline)


    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step(self, run_cmd_once):
        details = {'cmd': 'true'}
        self.dr.shell_step(details, {})
        run_cmd_once.assert_called_once_with(mock.ANY, 'true', mock.ANY, None)

    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_failure(self, run_cmd_once):
        details = {'cmd': 'false'}
        self.dr.shell_step(details, {})
        run_cmd_once.assert_called_once_with(mock.ANY, 'false', mock.ANY, None)

    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_failed_until_success(self, run_cmd_once):
        details = {'cmd': 'true',
                   'retry-if-fails': True}

        side_effects = [overcast.exceptions.CommandFailedException()]*100 + [True]
        run_cmd_once.side_effect = side_effects
        self.dr.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])

    @mock.patch('overcast.runner.time')
    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_failed_until_success_with_delay(self, run_cmd_once, time):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'retry-delay': '5s'}

        curtime = [0]
        def sleep(s, curtime=curtime):
            curtime[0] += s

        time.time.side_effect = lambda:curtime[0]
        time.sleep.side_effect = sleep

        side_effects = [overcast.exceptions.CommandFailedException()]*2 + [True]
        run_cmd_once.side_effect = side_effects
        self.dr.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])
        self.assertEquals(curtime[0], 10)

    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_timedout_until_success(self, run_cmd_once):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'timeout': '10s'}

        side_effects = [overcast.exceptions.CommandTimedOutException()]*10 + [True]
        run_cmd_once.side_effect = side_effects
        self.dr.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])


    @mock.patch('overcast.runner.time')
    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_timedout_until_total_timeout(self,
                                                                run_cmd_once,
                                                                time):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'total-timeout': '10s'}

        time.time.return_value = 10

        side_effects = [overcast.exceptions.CommandTimedOutException()]*2
        def side_effect(*args, **kwargs):
            if len(side_effects) < 2:
                time.time.return_value = 100

            ret = side_effects.pop(0)
            if isinstance(ret, Exception):
                raise ret
            return ret

        run_cmd_once.side_effect = side_effect
        self.assertRaises(overcast.exceptions.CommandTimedOutException,
                          self.dr.shell_step, details, {})
        self.assertEquals(side_effects, [])

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_network_conflict(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        neutron.list_networks.return_value = {'networks': [{'name': 'somename',
                                                            'id': 'uuid1'},
                                                           {'name': 'somename',
                                                            'id': 'uuid2'}]}

        neutron.list_security_groups.return_value = {'security_groups': []}
        nova.servers.list.return_value = []

        self.assertRaises(overcast.exceptions.DuplicateResourceException,
                          self.dr.detect_existing_resources)

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_network_conflict_in_other_suffix(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        neutron.list_networks.return_value = {'networks': [{'name': 'somename_foo',
                                                            'id': 'uuid1'},
                                                           {'name': 'somename_foo',
                                                            'id': 'uuid2'}]}

        neutron.list_security_groups.return_value = {'security_groups': []}
        nova.servers.list.return_value = []

        self.dr.suffix = 'bar'
        self.dr.detect_existing_resources()

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_secgroup_conflict(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        neutron.list_networks.return_value = {'networks': []}
        neutron.list_security_groups.return_value = {'security_groups':
                                                          [{'name': 'somename',
                                                            'id': 'uuid1'},
                                                           {'name': 'somename',
                                                            'id': 'uuid2'}]}

        nova.servers.list.return_value = []

        self.assertRaises(overcast.exceptions.DuplicateResourceException,
                          self.dr.detect_existing_resources)

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_secgroup_conflict_in_other_suffix(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        neutron.list_networks.return_value = {'networks': []}
        neutron.list_security_groups.return_value = {'security_groups':
                                                          [{'name': 'somename_foo',
                                                            'id': 'uuid1'},
                                                           {'name': 'somename_foo',
                                                            'id': 'uuid2'}]}
        nova.servers.list.return_value = []

        self.dr.suffix = 'bar'
        self.dr.detect_existing_resources()

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_server_conflict(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        class Server(object):
            def __init__(self, name, id):
                self.name = name
                self.id = id

        neutron.list_networks.return_value = {'networks': []}
        neutron.list_security_groups.return_value = {'security_groups': []}
        nova.servers.list.return_value = [Server('server1', 'uuid1'),
                                          Server('server1', 'uuid2')]

        self.assertRaises(overcast.exceptions.DuplicateResourceException,
                          self.dr.detect_existing_resources)

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def test_detect_existing_resources_server_conflict_in_other_suffix(self, get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        nova = get_nova_client.return_value

        class Server(object):
            def __init__(self, name, id):
                self.name = name
                self.id = id

        neutron.list_networks.return_value = {'networks': []}
        neutron.list_security_groups.return_value = {'security_groups': []}
        nova.servers.list.return_value = [Server('server1_foo', 'uuid1'),
                                          Server('server1_foo', 'uuid2')]

        self.dr.suffix = 'bar'
        self.dr.detect_existing_resources()

    def test_detect_existing_resources_no_suffix(self):
        self._test_detect_existing_resources(None,
                                             {'other': '98765432-e3c0-41a5-880d-ebeb6b1ded5e',
                                              'default_mysuffix': '12345678-e3c0-41a5-880d-ebeb6b1ded5e'},
                                             {'testnet': '123123123-524c-406b-b7c1-9bc069251d22',
                                              'testnet2_mysuffix': '123123123-524c-406b-b7c1-987665441d22'},
                                             {'server1_mysuffix': 'server1_mysuffixuuid',
                                              'server1': 'server1uuid'})

    def test_detect_existing_resources_with_suffix(self):
        self._test_detect_existing_resources('mysuffix',
                                             {'default': '12345678-e3c0-41a5-880d-ebeb6b1ded5e'},
                                             {'testnet2': '123123123-524c-406b-b7c1-987665441d22'},
                                             {'server1': 'server1_mysuffixuuid'})

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    def _test_detect_existing_resources(self, suffix, expected_secgroups, expected_networks, expected_nodes,
                                        get_nova_client, get_neutron_client):
        neutron = get_neutron_client.return_value
        neutron.list_networks.return_value = {'networks': [{'status': 'ACTIVE',
                                                            'router:external': False,
                                                            'subnets': ['12345678-acab-4949-b06b-b095f9a6ca8c'],
                                                            'name': 'testnet',
                                                            'admin_state_up': True,
                                                            'tenant_id': '987654331abcdef98765431',
                                                            'shared': False,
                                                            'id': '123123123-524c-406b-b7c1-9bc069251d22'},
                                                           {'status': 'ACTIVE',
                                                            'router:external': False,
                                                            'subnets': ['98766544-acab-4949-b06b-b095f9a6ca8c'],
                                                            'name': 'testnet2_mysuffix',
                                                            'admin_state_up': True,
                                                            'tenant_id': '987654331abcdef98765431',
                                                            'shared': False,
                                                            'id': '123123123-524c-406b-b7c1-987665441d22'}]}

        neutron.list_security_groups.return_value = {'security_groups': [{'id': '98765432-e3c0-41a5-880d-ebeb6b1ded5e',
                                                                          'tenant_id': '987654331abcdef98765431',
                                                                          'description': None,
                                                                          'security_group_rules': [],
                                                                          'name': 'other'},
                                                                         {'id': '12345678-e3c0-41a5-880d-ebeb6b1ded5e',
                                                                          'tenant_id': '987654331abcdef98765431',
                                                                          'description': None,
                                                                          'security_group_rules': [],
                                                                          'name': 'default_mysuffix'}]}
        nova = get_nova_client.return_value

        class Server(object):
            def __init__(self, name, id):
                self.name = name
                self.id = id

        nova.servers.list.return_value = [Server('server1', 'server1uuid'),
                                          Server('server1_mysuffix', 'server1_mysuffixuuid')]

        self.dr.suffix = suffix
        self.dr.detect_existing_resources()

        self.assertEquals(self.dr.secgroups, expected_secgroups)
        self.assertEquals(self.dr.networks, expected_networks)
        self.assertEquals(self.dr.nodes, expected_nodes)


    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    def test_find_floating_network(self, get_neutron_client):
        nc = get_neutron_client.return_value
        nc.list_networks.return_value = {'networks': [{'id': 'netuuid'}]}

        self.assertEquals(self.dr.find_floating_network(), 'netuuid')

        nc.list_networks.assert_called_once_with(**{'router:external': True})

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    @mock.patch('overcast.runner.DeploymentRunner.find_floating_network')
    def test_create_floating_ip(self, find_floating_network, get_neutron_client):
        nc = get_neutron_client.return_value

        find_floating_network.return_value = 'netuuid'

        nc.create_floatingip.return_value = {'floatingip': {'id': 'theuuid',
                                                            'floating_ip_address': '1.2.3.4'}}

        self.assertEquals(self.dr.create_floating_ip(), ('theuuid', '1.2.3.4'))

        nc.create_floatingip.assert_called_once_with({'floatingip': {'floating_network_id': 'netuuid'}})

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    def test_create_network(self, get_neutron_client):
        nc = get_neutron_client.return_value
        nc.create_network.return_value = {'network': {'id': 'theuuid'}}
        nc.create_subnet.return_value = {'subnet': {'id': 'thesubnetuuid'}}

        self.dr.record_resource = mock.MagicMock()
        self.dr.create_network('netname', {'cidr': '10.0.0.0/12'})

        nc.create_network.assert_called_once_with({'network': {'name': 'netname',
                                                               'admin_state_up': True}})
        nc.create_subnet.assert_called_once_with({'subnet': {'name': 'netname',
                                                             'cidr': '10.0.0.0/12',
                                                             'ip_version': 4,
                                                             'network_id': 'theuuid'}})
        self.dr.record_resource.assert_any_call('network', 'theuuid')
        self.dr.record_resource.assert_any_call('subnet', 'thesubnetuuid')

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    def test_create_security_group(self, get_neutron_client):
        nc = get_neutron_client.return_value
        nc.create_security_group.return_value = {'security_group': {'id': 'theuuid'}}
        nc.create_security_group_rule.return_value = {'security_group_rule': {'id': 'theruleuuid'}}

        self.dr.record_resource = mock.MagicMock()
        self.dr.create_security_group('secgroupname', [{'cidr': '12.0.0.0/12',
                                                                'protocol': 'tcp',
                                                                'from_port': 21,
                                                                'to_port': 22}])

        nc.create_security_group.assert_called_once_with({'security_group': {'name': 'secgroupname'}})
        nc.create_security_group_rule.assert_called_once_with({'security_group_rule': {'remote_ip_prefix': '12.0.0.0/12',
                                                                                       'direction': 'ingress',
                                                                                       'ethertype': 'IPv4',
                                                                                       'port_range_min': 21,
                                                                                       'port_range_max': 22,
                                                                                       'protocol': 'tcp',
                                                                                       'security_group_id': 'theuuid'}})
        self.dr.record_resource.assert_any_call('secgroup', 'theuuid')
        self.dr.record_resource.assert_any_call('secgroup_rule', 'theruleuuid')

    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    def test_create_security_group_without_rules(self, get_neutron_client):
        nc = get_neutron_client.return_value
        nc.create_security_group.return_value = {'security_group': {'id': 'theuuid'}}

        self.dr.create_security_group('secgroupname', None)
        nc.create_security_group.assert_called_once_with({'security_group': {'name': 'secgroupname'}})

    @mock.patch('overcast.runner.DeploymentRunner.create_port')
    @mock.patch('overcast.runner.DeploymentRunner.get_nova_client')
    @mock.patch('overcast.runner.DeploymentRunner.get_neutron_client')
    def test_create_node(self, get_neutron_client, get_nova_client, create_port):
        nc = get_nova_client.return_value
        self.dr.record_resource = mock.MagicMock()

        nc.flavors.get.return_value = 'smallflavorobject'
        nc.images.get.return_value = 'trustyimageobject'
        nc.servers.create.return_value.id = 'serveruuid'

        def _create_port(name, network, secgroups):
            return {'yes,mapped': 'nicuuid1',
                    'theoneIjustcreated': 'nicuuid2',
                    'passedthrough': 'nicuuid3'}[network]

        create_port.side_effect = _create_port

        self.dr.networks = {'ephemeral': 'theoneIjustcreated'}
        self.dr.secgroups = {}
        self.dr.mappings = {'networks': {'mapped': 'yes,mapped'},
                            'images': {'trusty': 'trustyuuid'},
                            'flavors': {'small': 'smallid'}}

        self.dr.create_node('test1_x123',
                                    {'image': 'trusty',
                                     'flavor': 'small',
                                     'disk': 10,
                                     'networks': [{'network': 'mapped'},
                                                  {'network': 'ephemeral', 'assign_floating_ip': True},
                                                  {'network': 'passedthrough'}]},
                                    userdata='foo',
                                    keypair='key_x123')

        nc.flavors.get.assert_called_with('smallid')
        nc.images.get.assert_called_with('trustyuuid')

        nc.servers.create.assert_called_with('test1_x123',
                                             nics=[{'port-id': 'nicuuid1'},
                                                   {'port-id': 'nicuuid2'},
                                                   {'port-id': 'nicuuid3'}],
                                             block_device_mapping_v2=[
                                                     {'boot_index': '0',
                                                      'uuid': 'trustyuuid',
                                                      'volume_size': 10,
                                                      'source_type': 'image',
                                                      'destination_type': 'volume',
                                                      'delete_on_termination': 'true'}],
                                             image=None,
                                             userdata='foo',
                                             key_name='key_x123',
                                             flavor='smallflavorobject')

        self.dr.record_resource.assert_any_call('port', 'nicuuid1')
        self.dr.record_resource.assert_any_call('port', 'nicuuid2')
        self.dr.record_resource.assert_any_call('port', 'nicuuid3')
        self.dr.record_resource.assert_any_call('server', 'serveruuid')

    def test_list_refs_human(self):
        self._test_list_refs(False, 'Images:\n  trusty\n\nFlavors:\n  bootstrap\n')

    def test_list_refs_cfg_tmpl(self):
        self._test_list_refs(True, '[images]\ntrusty = <missing value>\n\n[flavors]\nbootstrap = <missing value>\n\n')

    def _test_list_refs(self, tmpl_, expected_value):
        example_file = os.path.join(os.path.dirname(__file__),
                                    'examplestack1.yaml')
        class Args(object):
            stack = example_file
            tmpl = tmpl_

        args = Args()
        output = StringIO()
        overcast.runner.list_refs(args, output)
        self.assertEquals(output.getvalue(), expected_value)


    @mock.patch('overcast.runner.DeploymentRunner.create_network')
    @mock.patch('overcast.runner.DeploymentRunner.create_security_group')
    @mock.patch('overcast.runner.DeploymentRunner.create_node')
    def test_provision_step(self, create_node, create_security_group, create_network):
        create_network.return_value = 'netuuid'
        create_security_group.return_value = 'sguuid'
        self.dr.suffix = 'x123'
        self.dr.provision_step({'stack': 'overcast/tests/runner/examplestack1.yaml'})

        create_network.assert_called_with('undercloud_x123', {'cidr': '10.240.292.0/24'})
        create_security_group.assert_called_with('jumphost_x123',
                                                 [{'to_port': 22,
                                                   'cidr': '0.0.0.0/0',
                                                   'from_port': 22}])
        create_node.assert_any_call('other_x123',
                                    {'networks': [{'securitygroups': ['jumphost'],
                                                   'network': 'default',
                                                   'assign_floating_ip': True},
                                              {'network': 'undercloud'}],
                                     'flavor': 'bootstrap',
                                     'image': 'trusty'},
                                    userdata=None,
                                    keypair=None)
        create_node.assert_any_call('bootstrap1_x123',
                                    {'networks': [{'securitygroups': ['jumphost'], 'network': 'default'},
                                                  {'network': 'undercloud'}],
                                     'flavor': 'bootstrap',
                                     'image': 'trusty'},
                                    userdata=None,
                                    keypair=None)
        create_node.assert_any_call('bootstrap2_x123',
                                    {'networks': [{'securitygroups': ['jumphost'], 'network': 'default'},
                                                  {'network': 'undercloud'}],
                                     'flavor': 'bootstrap',
                                     'image': 'trusty'},
                                    userdata=None,
                                    keypair=None)
