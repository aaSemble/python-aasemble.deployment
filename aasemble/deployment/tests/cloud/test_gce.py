import os.path
import unittest

from libcloud.compute.types import Provider
import mock

import aasemble.deployment.cloud.models as cloud_models
import aasemble.deployment.cloud.gce as gce

class GCEDriverTestCase(unittest.TestCase):
    def setUp(self):
        super(GCEDriverTestCase, self).setUp()
        self.record_resource = mock.MagicMock()
        self.gce_key_file = os.path.join(os.path.dirname(__file__), 'test_key.json')
        self.cloud_driver = gce.GCEDriver(gce_key_file=self.gce_key_file,
                                          record_resource=self.record_resource)

    @mock.patch('aasemble.deployment.cloud.gce.get_driver')
    def test_connection(self, get_driver):
        self.assertEquals(self.cloud_driver.connection, get_driver.return_value.return_value)
        get_driver.assert_called_with(Provider.GCE)
        get_driver(Provider.GCE).assert_called_with('foobar@a-project-id.iam.gserviceaccount.com',
                                                    self.gce_key_file,
                                                    project='a-project-id')

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    def test_detect_resources(self, connection):
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
        node1.extra = {'disks': [{'source': vol1.extra['selfLink']}]}

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
                                        export=True,
                                        networks=[]),
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
        self.assertEquals(len(collection.nodes), 1)
        self.assertEquals(len(collection.security_groups), 3)
        self.assertEquals(len(collection.security_group_rules), 4)

    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver.connection')
    @mock.patch('aasemble.deployment.cloud.gce.GCEDriver._disk_struct')
    def test_apply_resources(self, _disk_struct, connection):
        collection = cloud_models.Collection()
        collection.nodes.add(cloud_models.Node(name='webapp',
                                               image='trusty',
                                               flavor='n1-standard-2',
                                               disk=37,
                                               networks=[],
                                               export=True))
        webappsg = cloud_models.SecurityGroup(name='webapp')
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
        connection.create_node.assert_called_with(name='webapp',
                                                  size='n1-standard-2',
                                                  image=None,
                                                  ex_disks_gce_struct=_disk_struct.return_value)

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

    def test_disk_struct(self):
        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[],
                                 export=True)
        self.assertEquals(self.cloud_driver._disk_struct(node), [{'boot': True,
                                                                  'autoDelete': True,
                                                                  'initializeParams': {
                                                                      'sourceImage': 'trusty',
                                                                      'diskType': 'pd-ssd',
                                                                      'diskSizeGb': 37}
                                                                  }])
