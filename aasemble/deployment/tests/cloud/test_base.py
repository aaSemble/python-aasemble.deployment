import unittest

import mock

from aasemble.deployment.cloud import base


class CloudDriverTests(unittest.TestCase):
    def setUp(self):
        super(CloudDriverTests, self).setUp()
        self.record_resource = mock.MagicMock()
        self.driver = base.CloudDriver(self.record_resource)

    def test_init(self):
        self.assertEquals(self.driver.record_resource,
                          self.record_resource)

    def test_detect_resources(self):
        self.assertRaises(NotImplementedError,
                          self.driver.detect_resources)

    def test_apply_resources(self):
        self.assertRaises(NotImplementedError,
                          self.driver.apply_resources)
