import os.path
import unittest

import aasemble.deployment.cloud.models as cloud_models
import aasemble.deployment.loader as loader

class ParserTestCase(unittest.TestCase):
    def _get_full_path_for_test_data(self, filename):
        return os.path.join(os.path.dirname(__file__), 'test_data', filename)

    def test_simple(self):
        collection = loader.load(self._get_full_path_for_test_data('simple.yaml'))
        self.assertIn(cloud_models.Node(name='webapp', flavor='webapp', image='trusty', disk=10, export=True, networks=[]), collection)
        self.assertEquals(len(collection), 1)

    def test_plurality(self):
        collection = loader.load(self._get_full_path_for_test_data('plurality.yaml'))
        self.assertIn(cloud_models.Node(name='webapp1', flavor='webapp', image='trusty', disk=10, export=True, networks=[]), collection)
        self.assertIn(cloud_models.Node(name='webapp2', flavor='webapp', image='trusty', disk=10, export=True, networks=[]), collection)
        self.assertEquals(len(collection), 2)

    def test_with_security_groups(self):
        collection = loader.load(self._get_full_path_for_test_data('with_security_groups.yaml'))
        self.assertIn(cloud_models.Node(name='webapp1', flavor='webapp', image='trusty', disk=10, export=True, networks=[]), collection)
        self.assertIn(cloud_models.Node(name='webapp2', flavor='webapp', image='trusty', disk=10, export=True, networks=[]), collection)
        sg = cloud_models.SecurityGroup(name='webapp')
        self.assertIn(sg, collection)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=sg, source_ip='0.0.0.0/0', from_port=443, to_port=443, protocol='tcp'), collection)
        self.assertEquals(len(collection), 4)
