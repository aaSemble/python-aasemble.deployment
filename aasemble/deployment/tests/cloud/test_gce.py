import os.path
import unittest

from libcloud.compute.types import Provider

import mock

from testfixtures import log_capture

import aasemble.deployment.cloud.gce as gce
import aasemble.deployment.cloud.models as cloud_models


class FakeThreadPool(object):
    def map(self, func, iterable):
        return list(map(func, iterable))


class GCEDriverTestCase(unittest.TestCase):
    def setUp(self):
        super(GCEDriverTestCase, self).setUp()
        self.record_resource = mock.MagicMock()
        self.gce_key_file = os.path.join(os.path.dirname(__file__), 'test_key.json')
        self.cloud_driver = gce.GCEDriver(gce_key_file=self.gce_key_file,
                                          location='location1',
                                          record_resource=self.record_resource,
                                          pool=FakeThreadPool())

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

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @log_capture()
    def test_detect_resources(self, connection, log):
        class GCENode(mock.MagicMock):
            pass

        class GCEVolume(mock.MagicMock):
            pass

        class GCEFirewall(mock.MagicMock):
            pass

        vol1 = GCEVolume()
        vol1.size = 20
        vol1.extra = {'selfLink': 'https://www.googleapis.com/compute/v1/projects/a-project-id/zones/us-central1-f/disks/node1'}

        node1 = GCENode()
        node1.name = 'node1'
        node1.image = 'ubuntu-1404-trusty-v20151113'
        node1.size = 'n1-standard-2'
        node1.extra = {'disks': [{'source': vol1.extra['selfLink']}],
                       'tags': ['webapp']}

        fw1 = GCEFirewall()
        fw1.allowed = [{'IPProtocol': 'tcp', 'ports': ['22']}]
        fw1.target_tags = None

        fw2 = GCEFirewall()
        fw2.allowed = [{'IPProtocol': 'tcp', 'ports': ['8000-8080']}]
        fw2.target_tags = None

        fw3 = GCEFirewall()
        fw3.allowed = [{'IPProtocol': 'tcp', 'ports': ['443']}]
        fw3.target_tags = ['webapp', 'dev']

        connection.list_volumes.return_value = [vol1]
        connection.list_nodes.return_value = [node1]
        connection.ex_list_firewalls.return_value = [fw1, fw2, fw3]
        collection = self.cloud_driver.detect_resources()

        self.assertIn(cloud_models.Node(name='node1',
                                        image='ubuntu-1404-trusty-v20151113',
                                        flavor='n1-standard-2',
                                        disk=20,
                                        networks=[],
                                        security_groups=set([collection.security_groups['webapp']])),
                      collection.nodes)

        globalsg = cloud_models.SecurityGroup(name='global')
        webappsg = cloud_models.SecurityGroup(name='webapp')
        devsg = cloud_models.SecurityGroup(name='dev')
        self.assertIn(globalsg, collection.security_groups)
        self.assertIn(webappsg, collection.security_groups)
        self.assertIn(devsg, collection.security_groups)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=globalsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=22,
                                                     to_port=22,
                                                     protocol='tcp'), collection.security_group_rules)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=globalsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=8000,
                                                     to_port=8080,
                                                     protocol='tcp'), collection.security_group_rules)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=devsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=443,
                                                     to_port=443,
                                                     protocol='tcp'), collection.security_group_rules)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=webappsg,
                                                     source_ip='0.0.0.0/0',
                                                     from_port=443,
                                                     to_port=443,
                                                     protocol='tcp'), collection.security_group_rules)
        self.assertEqual(len(collection.nodes), 1)
        self.assertEqual(len(collection.security_groups), 3)
        self.assertEqual(len(collection.security_group_rules), 4)

        log_records = list(log.actual())
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detecting nodes'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected node: node1'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detecting security groups and security group rules'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group: webapp'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group: global'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group: dev'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group rule for security group global: tcp: 22-22'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group rule for security group global: tcp: 8000-8080'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group rule for security group dev: tcp: 443-443'), log_records)
        self.assertIn(('aasemble.deployment.cloud.gce', 'INFO', 'Detected security group rule for security group webapp: tcp: 443-443'), log_records)
        self.assertEqual(len(log_records), 10, log_records)

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_apply_resources(self, _disk_struct, connection):
        collection = cloud_models.Collection()
        webappsg = cloud_models.SecurityGroup(name='webapp')
        collection.nodes.add(cloud_models.Node(name='webapp',
                                               image='trusty',
                                               flavor='n1-standard-2',
                                               disk=37,
                                               networks=[],
                                               security_groups=set([webappsg])))
        collection.nodes.add(cloud_models.Node(name='webapp2',
                                               image='trusty',
                                               flavor='n1-standard-2',
                                               disk=37,
                                               networks=[],
                                               security_groups=set([webappsg]),
                                               script='#!/bin/bash\necho hello\n'))
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
