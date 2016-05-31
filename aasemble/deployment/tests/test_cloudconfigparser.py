import os.path
import unittest

from aasemble.deployment.cloud.gce import GCEDriver
from aasemble.deployment.cloudconfigparser import load_cloud_config


class CloudConfigParserTestCase(unittest.TestCase):
    def test_load_cloud_config(self):
        driver_class, driver_kwargs, mappings = load_cloud_config(os.path.join(os.path.dirname(__file__), 'test_data', 'cloud.ini'))
        self.assertEqual(driver_class, GCEDriver)
        self.assertEqual(driver_kwargs, {'gce_key_file': '/path/to/key.json',
                                         'location': 'location1'})
        self.assertEqual(mappings, {'images': {'trusty': 'ubuntu1404'},
                                    'flavors': {'webapp': 'n1-standard-2'}})
