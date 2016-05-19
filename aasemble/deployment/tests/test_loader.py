import os.path
import unittest

from testfixtures import log_capture

import aasemble.deployment.cloud.models as cloud_models
import aasemble.deployment.loader as loader


class ParserTestCase(unittest.TestCase):
    def _get_full_path_for_test_data(self, filename):
        return os.path.join(os.path.dirname(__file__), 'test_data', filename)

    @log_capture()
    def test_simple(self, log):
        collection = loader.load(self._get_full_path_for_test_data('simple.yaml'))
        self.assertIn(cloud_models.Node(name='webapp', flavor='webapp', image='trusty', disk=10, networks=[]), collection.nodes)
        self.assertEqual(len(collection.nodes), 1)
        self.assertEqual(len(collection.security_groups), 0)
        self.assertEqual(len(collection.security_group_rules), 0)
        log.check(('aasemble.deployment.loader', 'INFO', 'Loaded node webapp from stack'))

    @log_capture()
    def test_plurality(self, log):
        collection = loader.load(self._get_full_path_for_test_data('plurality.yaml'))
        self.assertIn(cloud_models.Node(name='webapp1', flavor='webapp', image='trusty', disk=10, networks=[]), collection.nodes)
        self.assertIn(cloud_models.Node(name='webapp2', flavor='webapp', image='trusty', disk=10, networks=[]), collection.nodes)
        self.assertEqual(len(collection.nodes), 2)
        self.assertEqual(len(collection.security_groups), 0)
        self.assertEqual(len(collection.security_group_rules), 0)
        log.check(('aasemble.deployment.loader', 'INFO', 'Loaded node webapp1 from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded node webapp2 from stack'))

    @log_capture()
    def test_with_security_groups(self, log):
        collection = loader.load(self._get_full_path_for_test_data('with_security_groups.yaml'))
        sg = cloud_models.SecurityGroup(name='webapp')

        self.assertIn(cloud_models.Node(name='webapp1', flavor='webapp', image='trusty', disk=10, networks=[], security_groups=set([sg])), collection.nodes)
        self.assertIn(cloud_models.Node(name='webapp2', flavor='webapp', image='trusty', disk=10, networks=[], security_groups=set([sg])), collection.nodes)

        self.assertIn(sg, collection.security_groups)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=sg, source_ip='0.0.0.0/0', from_port=443, to_port=443, protocol='tcp'), collection.security_group_rules)
        self.assertEqual(len(collection.nodes), 2)
        self.assertEqual(len(collection.security_groups), 1)
        self.assertEqual(len(collection.security_group_rules), 1)
        log.check(('aasemble.deployment.loader', 'INFO', 'Loaded node webapp1 from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded node webapp2 from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded security group webapp from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded security group rule from stack: tcp: 443-443'))

    @log_capture()
    def test_with_script(self, log):
        collection = loader.load(self._get_full_path_for_test_data('with_script.yaml'))
        sg = cloud_models.SecurityGroup(name='webapp')

        script = '#!/bin/sh\nadduser --system web\napt-get install python-virtualenv\netc. etc. etc.\n'

        self.assertIn(cloud_models.Node(name='webapp1', flavor='webapp', image='trusty', disk=10, networks=[], security_groups=set([sg]), script=script), collection.nodes)
        self.assertIn(cloud_models.Node(name='webapp2', flavor='webapp', image='trusty', disk=10, networks=[], security_groups=set([sg]), script=script), collection.nodes)

        self.assertIn(sg, collection.security_groups)
        self.assertIn(cloud_models.SecurityGroupRule(security_group=sg, source_ip='0.0.0.0/0', from_port=443, to_port=443, protocol='tcp'), collection.security_group_rules)
        self.assertEqual(len(collection.nodes), 2)
        self.assertEqual(len(collection.security_groups), 1)
        self.assertEqual(len(collection.security_group_rules), 1)
        log.check(('aasemble.deployment.loader', 'INFO', 'Loaded node webapp1 from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded node webapp2 from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded security group webapp from stack'),
                  ('aasemble.deployment.loader', 'INFO', 'Loaded security group rule from stack: tcp: 443-443'))
