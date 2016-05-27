import os.path
import unittest
import unittest.util

from libcloud.compute.types import Provider

import mock

from six.moves import configparser

from testfixtures import log_capture

import aasemble.deployment.cloud.gce as gce
import aasemble.deployment.cloud.models as cloud_models


class FakeThreadPool(object):
    def map(self, func, iterable):
        return list(map(func, iterable))


class GCENode(object):
    def __init__(self, name, size='n1-standard-1', image='ubuntu-1404-trusty-v20151113', tags=None, namespace=None):
        self.name = name
        self.size = size
        self.image = image
        self.extra = {'metadata': {},
                      'disks': [{'source': 'http://link/to/disk/{}'.format(name)}],
                      'tags': tags or []}

        if namespace:
            self.extra['metadata']['items'] = [{'key': 'aasemble_namespace', 'value': namespace}]


class GCEDriverTestCase(unittest.TestCase):
    def setUp(self):
        super(GCEDriverTestCase, self).setUp()
        self.record_resource = mock.MagicMock()
        self.gce_key_file = os.path.join(os.path.dirname(__file__), 'test_key.json')
        self.cloud_driver = gce.GCEDriver(gce_key_file=self.gce_key_file,
                                          location='location1',
                                          record_resource=self.record_resource,
                                          pool=FakeThreadPool())

    def test_get_kwargs_from_cloud_config(self):
        cp = configparser.ConfigParser()
        cp.add_section('connection')
        cp.set('connection', 'key_file', 'somekey.json')
        cp.set('connection', 'location', 'some.region')
        self.assertEqual(gce.GCEDriver.get_kwargs_from_cloud_config(cp),
                         {'gce_key_file': 'somekey.json',
                          'location': 'some.region'})

    @mock.patch('aasemble.deployment.cloud.gce.get_driver')
    @log_capture()
    def test_connection(self, get_driver, log):
        self.assertEqual(self.cloud_driver.connection, get_driver.return_value.return_value)
        get_driver.assert_called_with(Provider.GCE)
        get_driver(Provider.GCE).assert_called_with('foobar@a-project-id.iam.gserviceaccount.com',
                                                    self.gce_key_file,
                                                    project='a-project-id',
                                                    datacenter='location1')
        log.check(('aasemble.deployment.cloud.gce', 'INFO', 'Connecting to Google Compute Engine'))

    def test_get_driver_args_and_kwargs(self):
        self.assertEqual(self.cloud_driver._get_driver_args_and_kwargs(),
                         (('foobar@a-project-id.iam.gserviceaccount.com', self.gce_key_file),
                          {'project': 'a-project-id', 'datacenter': 'location1'}))

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_volume_size_map(self, connection):
        class GCEVolume(object):
            def __init__(self, name, size):
                self.extra = {'selfLink': 'http://link/to/{}'.format(name)}
                self.size = size

        connection.list_volumes.return_value = [GCEVolume('vol1', 100), GCEVolume('vol2', 200)]

        self.assertEquals(self.cloud_driver.volume_size_map,
                          {'http://link/to/vol1': 100,
                           'http://link/to/vol2': 200})

        self.cloud_driver.volume_size_map

        self.assertEqual(len(connection.list_volumes.call_args_list), 1,
                         'Did not cache volume size map')

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.detect_nodes')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.detect_firewalls')
    def test_detect_resources(self, detect_firewalls, detect_nodes):
        node1 = cloud_models.Node(name='node1',
                                  flavor='n1-standard-4',
                                  image='ubuntu1404-12345678',
                                  networks=[],
                                  disk=20)

        node2 = cloud_models.Node(name='node2',
                                  flavor='n1-standard-4',
                                  image='ubuntu1404-12345678',
                                  networks=[],
                                  disk=20)

        node1.security_group_names = set(['webapp', 'ssh'])
        node2.security_group_names = set(['webapp'])

        sg_webapp = cloud_models.SecurityGroup(name='webapp')
        sg_ssh = cloud_models.SecurityGroup(name='ssh')

        sgr_https = cloud_models.SecurityGroupRule(security_group=sg_webapp,
                                                   source_ip='0.0.0.0/0',
                                                   from_port=443,
                                                   to_port=443,
                                                   protocol='tcp')

        sgr_ssh = cloud_models.SecurityGroupRule(security_group=sg_ssh,
                                                 source_ip='0.0.0.0/0',
                                                 from_port=22,
                                                 to_port=22,
                                                 protocol='tcp')

        detect_nodes.return_value = set([node1, node2])
        detect_firewalls.return_value = (set([sg_webapp, sg_ssh]), set([sgr_https, sgr_ssh]))

        collection = self.cloud_driver.detect_resources()

        self.assertIn(node1, collection.nodes)
        self.assertIn(node2, collection.nodes)

        self.assertIn(sg_webapp, collection.nodes['node1'].security_groups)
        self.assertIn(sg_ssh, collection.nodes['node1'].security_groups)

        self.assertIn(sg_webapp, collection.nodes['node2'].security_groups)

        self.assertIn(sg_webapp, collection.security_groups)
        self.assertIn(sg_ssh, collection.security_groups)

        self.assertIn(sgr_https, collection.security_group_rules)
        self.assertIn(sgr_ssh, collection.security_group_rules)

    def test_is_node_relevant_accepts_all_when_no_namespace_set(self):
        self.assertTrue(self.cloud_driver._is_node_relevant(GCENode('node1')))
        self.assertTrue(self.cloud_driver._is_node_relevant(GCENode('node1', namespace='something')))

    def test_is_node_relevant_only_matching_namespace(self):
        self.cloud_driver.namespace = 'testns'
        self.assertFalse(self.cloud_driver._is_node_relevant(GCENode('node1')))
        self.assertFalse(self.cloud_driver._is_node_relevant(GCENode('node1', namespace='something')))
        self.assertTrue(self.cloud_driver._is_node_relevant(GCENode('node1', namespace='testns')))
        self.assertFalse(self.cloud_driver._is_node_relevant(GCENode('node1', namespace='testns1')))

    def test_node_from_gcenode(self):
        gcenode = GCENode('testnode1', tags=['tag1', 'tag2'])
        self.cloud_driver._volume_size_map = {'http://link/to/disk/testnode1': 10}
        node = self.cloud_driver._node_from_gcenode(gcenode)
        self.assertEqual(node.name, 'testnode1')
        self.assertEqual(node.flavor, 'n1-standard-1')
        self.assertEqual(node.image, 'ubuntu-1404-trusty-v20151113')
        self.assertEqual(node.disk, 10)
        self.assertEqual(node.networks, [])
        self.assertEqual(node.security_group_names, set(['tag1', 'tag2']))
        self.assertEqual(node.private, gcenode)

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._is_node_relevant')
    def test_get_relevant_nodes_ignores_irrelevant_nodes(self, _is_node_relevant, connection):
        node1, node2 = GCENode('node1'), GCENode('node2')
        connection.list_nodes.return_value = [node1, node2]
        _is_node_relevant.side_effect = lambda n: n == node1

        nodes = list(self.cloud_driver._get_relevant_nodes())
        self.assertEqual(len(nodes), 1)
        self.assertIn(node1, nodes)

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._get_relevant_nodes')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._node_from_gcenode')
    def test_detect_nodes_converts_to_nodes_from_gcenodes(self, _node_from_gcenode, _get_relevant_nodes):
        _get_relevant_nodes.return_value = [mock.sentinel.node1, mock.sentinel.node2]

        _node_from_gcenode.side_effect = lambda x: x
        nodes = list(self.cloud_driver.detect_nodes())
        self.assertEqual(len(nodes), 2)
        _node_from_gcenode.assert_any_call(mock.sentinel.node1)
        _node_from_gcenode.assert_any_call(mock.sentinel.node2)

    def _get_firewalls(self):
        class GCEFirewall(object):
            def __init__(self, protocol, ports, tags):
                self.allowed = [{'IPProtocol': protocol, 'ports': [ports]}]
                self.target_tags = tags

        fw1 = GCEFirewall('tcp', '22', None)
        fw2 = GCEFirewall('tcp', '8000-8080', None)
        fw3 = GCEFirewall('tcp', '443', ['webapp', 'dev'])
        return fw1, fw2, fw3

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_detect_firewalls(self, connection):
        fw1, fw2, fw3 = self._get_firewalls()

        connection.ex_list_firewalls.return_value = [fw1, fw2, fw3]
        security_groups, security_group_rules = self.cloud_driver.detect_firewalls()
        self.assertIn(cloud_models.SecurityGroup(name='webapp'), security_groups)
        self.assertIn(cloud_models.SecurityGroup(name='dev'), security_groups)

        webapp = cloud_models.SecurityGroup(name='webapp')
        dev = cloud_models.SecurityGroup(name='dev')
        globalsg = cloud_models.SecurityGroup(name='global')

        self.assertIn(webapp, security_groups)
        self.assertIn(dev, security_groups)

        self.assertIn(cloud_models.SecurityGroupRule(security_group=webapp,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=443,
                                                     to_port=443,
                                                     protocol='tcp'),
                      security_group_rules)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=globalsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=22,
                                                     to_port=22,
                                                     protocol='tcp'),
                      security_group_rules)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=globalsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=8000,
                                                     to_port=8080,
                                                     protocol='tcp'),
                      security_group_rules)

    def test_get_all_security_group_names(self):
        firewalls = set(self._get_firewalls())
        self.assertEqual(self.cloud_driver._get_all_security_group_names(firewalls),
                         set(['global', 'dev', 'webapp']))

    def _example_collection(self):
        collection = cloud_models.Collection()
        webappsg = cloud_models.SecurityGroup(name='webapp')
        collection.nodes.add(cloud_models.Node(name='webapp',
                                               image='trusty',
                                               flavor='n1-standard-2',
                                               disk=37,
                                               networks=[],
                                               security_groups=set([webappsg]),
                                               private=mock.sentinel.webapp1priv))
        collection.nodes.add(cloud_models.Node(name='webapp2',
                                               image='trusty',
                                               flavor='n1-standard-2',
                                               disk=37,
                                               networks=[],
                                               security_groups=set([webappsg]),
                                               script='#!/bin/bash\necho hello\n',
                                               private=mock.sentinel.webapp2priv))
        collection.security_groups.add(webappsg)
        collection.security_group_rules.add(cloud_models.SecurityGroupRule(security_group=webappsg,
                                                                           source_ip='0.0.0.0/0',
                                                                           from_port=443,
                                                                           to_port=443,
                                                                           protocol='tcp'))
        collection.security_group_rules.add(cloud_models.SecurityGroupRule(security_group=webappsg,
                                                                           source_ip='212.10.10.10/32',
                                                                           from_port=8000,
                                                                           to_port=8080,
                                                                           protocol='tcp'))
        return collection

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_create_node_without_namespace_without_script(self, _disk_struct, connection):
        collection = self._example_collection()
        node = collection.nodes['webapp']
        self.cloud_driver.create_node(node)
        connection.create_node.assert_any_call(name='webapp',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_create_node_without_namespace_with_script(self, _disk_struct, connection):
        collection = self._example_collection()
        node = collection.nodes['webapp2']
        self.cloud_driver.create_node(node)
        connection.create_node.assert_any_call(name='webapp2',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_metadata={'items': [{'key': 'startup-script',
                                                                       'value': '#!/bin/bash\necho hello\n'}]},
                                               ex_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_create_node_with_namespace_no_script(self, _disk_struct, connection):
        self.cloud_driver.namespace = 'testns'
        collection = self._example_collection()
        node = collection.nodes['webapp']
        self.cloud_driver.create_node(node)
        connection.create_node.assert_any_call(name='webapp',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_metadata={'items': [{'key': 'aasemble_namespace',
                                                                       'value': 'testns'}]},
                                               ex_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_create_node_with_namespace_with_script(self, _disk_struct, connection):
        self.cloud_driver.namespace = 'testns'
        collection = self._example_collection()
        node = collection.nodes['webapp2']
        self.cloud_driver.create_node(node)
        connection.create_node.assert_any_call(name='webapp2',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_metadata={'items': [{'key': 'startup-script',
                                                                       'value': '#!/bin/bash\necho hello\n'},
                                                                      {'key': 'aasemble_namespace',
                                                                       'value': 'testns'}]},
                                               ex_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_create_node_no_namespace(self, _disk_struct, connection):
        collection = self._example_collection()
        node = collection.nodes['webapp2']
        self.cloud_driver.create_node(node)
        connection.create_node.assert_any_call(name='webapp2',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_metadata={'items': [{'key': 'startup-script',
                                                                       'value': '#!/bin/bash\necho hello\n'}]},
                                               ex_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_apply_resources(self, _disk_struct, connection):
        collection = self._example_collection()
        self.cloud_driver.apply_resources(collection)
        connection.create_node.assert_any_call(name='webapp',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_tags=['webapp'])
        connection.create_node.assert_any_call(name='webapp2',
                                               size='n1-standard-2',
                                               image=None,
                                               ex_disks_gce_struct=_disk_struct.return_value,
                                               ex_tags=['webapp'],
                                               ex_metadata={'items': [{'key': 'startup-script',
                                                                       'value': '#!/bin/bash\necho hello\n'}]})

        connection.ex_create_firewall.assert_any_call(name='webapp-tcp-443-443',
                                                      allowed=[{'IPProtocol': 'tcp',
                                                                'ports': ['443']}],
                                                      source_ranges=None,
                                                      target_tags=['webapp'])
        connection.ex_create_firewall.assert_any_call(name='webapp-tcp-8000-8080',
                                                      allowed=[{'IPProtocol': 'tcp',
                                                                'ports': ['8000-8080']}],
                                                      source_ranges=['212.10.10.10/32'],
                                                      target_tags=['webapp'])

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_clean_resources(self, connection):
        collection = self._example_collection()
        self.cloud_driver.clean_resources(collection)
        connection.destroy_node.assert_any_call(mock.sentinel.webapp1priv)
        connection.destroy_node.assert_any_call(mock.sentinel.webapp2priv)

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._get_disk_type')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.apply_mappings')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._resolve_image_name')
    def test_disk_struct(self, _resolve_image_name, apply_mappings, _get_disk_type, connection):
        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[])

        apply_mappings.return_value = 'mappedtrusty'
        _get_disk_type.return_value = 'http://disktypelink'
        _resolve_image_name.return_value = 'http://mappedtrusty'
        self.assertEqual(self.cloud_driver._disk_struct(node), [{'boot': True,
                                                                 'autoDelete': True,
                                                                 'initializeParams': {
                                                                     'sourceImage': 'http://mappedtrusty',
                                                                     'diskType': 'http://disktypelink',
                                                                     'diskSizeGb': 37}}])
        _resolve_image_name.assert_called_with('mappedtrusty')
        apply_mappings.assert_called_with('images', 'trusty')

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_resolve_image_name(self, connection):
        class NodeImage(mock.MagicMock):
            pass

        img1 = NodeImage()
        img1.name = 'ubuntu-14-04-12345667v'
        img1.extra = {'selfLink': 'http://somelink1'}

        img2 = NodeImage()
        img2.name = 'redhat-14-04-12345667v'
        img2.extra = {'selfLink': 'http://somelink2'}
        connection.list_images.return_value = [img1, img2]

        self.assertEqual(self.cloud_driver._resolve_image_name('ubuntu-14-04-12345667v'),
                         'http://somelink1')

    def test_parse_port_spec_single_port(self):
        self.assertEqual(self.cloud_driver._parse_port_spec({'ports': ['443']}), (443, 443))

    def test_parse_port_spec_port_range(self):
        self.assertEqual(self.cloud_driver._parse_port_spec({'ports': ['8000-8080']}), (8000, 8080))

    def test_parse_port_spec_no_ports(self):
        self.assertEqual(self.cloud_driver._parse_port_spec({}), (0, 65535))

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_get_disk_type(self, connection):
        class DiskType(mock.MagicMock):
            pass

        ssd = DiskType()
        ssd.name = 'pd-ssd'
        ssd.extra = {'selfLink': 'http://ssdlink'}
        hdd = DiskType()
        hdd.name = 'pd-hdd'
        hdd.extra = {'selfLink': 'http://hddlink'}
        connection.ex_list_disktypes.return_value = [ssd, hdd]

        self.assertEqual(self.cloud_driver._get_disk_type('pd-hdd'),
                         'http://hddlink')

    def _test_get_namespace(self, metadata, expected_rv):
        class GCENode(mock.MagicMock):
            pass

        node = GCENode()
        node.extra = {}

        if metadata:
            node.extra['metadata'] = metadata

        self.assertEqual(gce.get_namespace(node), expected_rv)

    def test_get_namespace(self):
        self._test_get_namespace({'fingerprint': 'WppLmdldALY=',
                                  'items': [{'key': 'startup-script',
                                             'value': '#!/bin/bash\necho hello\n'},
                                            {'key': 'aasemble_namespace', 'value': 'foobar'}],
                                  'kind': 'compute#metadata'}, 'foobar')

    def test_get_namespace_no_metadata(self):
        self._test_get_namespace(None, None)

    def test_get_namespace_no_items_in_metadata(self):
        self._test_get_namespace({'fingerprint': 'WppLmdldALY=',
                                  'kind': 'compute#metadata'}, None)

    def test_get_namespace_no_namespace_in_metadata(self):
        self._test_get_namespace({'fingerprint': 'WppLmdldALY=',
                                  'items': [{'key': 'startup-script',
                                             'value': '#!/bin/bash\necho hello\n'}],
                                  'kind': 'compute#metadata'}, None)

    def test_expand_path(self):
        os.environ['USER'] = 'someuser'
        os.environ['HOME'] = '/home/someuser'
        self.assertEquals(self.cloud_driver.expand_path('~/foo/bar.baz'), '/home/someuser/foo/bar.baz')

    def test_format_ssh_metadata(self):
        self.assertEquals(self.cloud_driver._format_ssh_metadata('soren', 'ssh-rsa AAAAA21341451352345 foo@bar'),
                          'soren:ssh-rsa AAAAA21341451352345 foo@bar')

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.expand_path')
    def test_ssh_metadata(self, expand_path):
        self.cloud_driver.ssh_key_file = '~/somepath'
        self.cloud_driver.username = 'someuser'
        expand_path.return_value = os.path.join(os.path.dirname(__file__), '..', 'test_data', 'public.key')
        self.assertEqual(self.cloud_driver._ssh_metadata(),
                         'someuser:ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDT7UcaDrA8FVbepVxD+HuhXDDzE'
                         'yy2pKGZcv2PstGVEW0ltspt7glmxNRHHBUuPsgvMQjVnLHvmxUE79DotCsMFg2o2lQM8uRlIAi'
                         'X3tSeN5pgxbt1MhpmAV7AyCkDLsUeTWhfVeUgTO2amM5aKuJzGqxbNgf1tNKEdyspCm/c06L2r'
                         'MQZ2MWhqHLPC4C4O3mGbuTeWthIU4PgWK8hGcqxm4QwACwpMT7iTfH8mALCmeCw0PQdE6Mz5rp'
                         'FftvwOPpNwU0W/dfqjZ/zTa+n5wIzTL7d6qD3E2ihSIsP8YCObiICWBJFzidtbLxMNu5nZqPK7'
                         'wPL7VzQS89FNQNSD4if soren')
        expand_path.assert_called_with('~/somepath')
