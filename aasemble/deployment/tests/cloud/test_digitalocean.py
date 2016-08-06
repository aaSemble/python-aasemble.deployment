import os.path
import unittest

import mock

from six.moves import configparser

import aasemble.deployment.cloud.digitalocean as digitalocean
import aasemble.deployment.cloud.models as cloud_models


test_api_key = 'kht3hkl34kjl5h25lkjh33'


class FakeThreadPool(object):
    def map(self, func, iterable):
        return list(map(func, iterable))


class DigitalOceanDriverTests(unittest.TestCase):
    def setUp(self):
        super(DigitalOceanDriverTests, self).setUp()
        self.cloud_driver = digitalocean.DigitalOceanDriver(api_key=test_api_key,
                                                            location='fra1',
                                                            pool=FakeThreadPool())

    def _get_base_config(self):
        cp = configparser.ConfigParser()
        cp.add_section('connection')
        cp.set('connection', 'api_key', 'exampleapikey')
        cp.set('connection', 'location', 'ams1')
        return cp

    def test_get_kwargs_from_cloud_config(self):
        cp = self._get_base_config()
        self.assertEqual(digitalocean.DigitalOceanDriver.get_kwargs_from_cloud_config(cp),
                         {'location': 'ams1',
                          'api_key': 'exampleapikey'})

    def test_get_kwargs_from_cloud_config_with_ssh_key(self):
        cp = self._get_base_config()
        cp.set('connection', 'sshkey', 'some.key')
        self.assertEqual(digitalocean.DigitalOceanDriver.get_kwargs_from_cloud_config(cp),
                         {'location': 'ams1',
                          'ssh_key_file': 'some.key',
                          'api_key': 'exampleapikey'})

    def test_get_driver_args_and_kwargs(self):
        self.assertEqual(self.cloud_driver._get_driver_args_and_kwargs(),
                         ((test_api_key,),
                          {'api_version': 'v2'}))

    def _test_is_node_relevant(self, state, relevant):
        class AWSNode(object):
            def __init__(self, state):
                self.state = state

        self.assertEqual(self.cloud_driver._is_node_relevant(AWSNode(state)), relevant)

    def test_is_node_relevant_when_off(self):
        self._test_is_node_relevant('off', False)

    def test_is_node_relevant_when_running(self):
        self._test_is_node_relevant('active', True)

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.get_size')
    def test_aasemble_node_from_provider_node(self, get_size):
        class DOSize(object):
            def __init__(self, disk):
                self.disk = disk

        get_size.return_value = DOSize(20)

        class DONode(object):
            def __init__(self, name, size, image):
                self.name = name
                self.extra = {'size_slug': size,
                              'image': {'id': image}}

        donode = DONode(name='testnode1', size='512mb', image='127237412')
        node = self.cloud_driver._aasemble_node_from_provider_node(donode)
        self.assertEqual(node.name, 'testnode1')
        self.assertEqual(node.flavor, '512mb')
        self.assertEqual(node.image, '127237412')
        self.assertEqual(node.disk, 20)
        self.assertEqual(node.security_group_names, set())
        self.assertEqual(node.private, donode)

    def test_detect_firewalls(self):
        self.assertEqual(self.cloud_driver.detect_firewalls(), (set(), set()))

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.connection')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.apply_mappings')
    def test_get_image(self, apply_mappings, connection):
        self.assertEqual(self.cloud_driver._get_image('trusty'),
                         connection.get_image.return_value)
        apply_mappings.assert_called_with('images', 'trusty')
        connection.get_image.assert_called_with(apply_mappings.return_value)

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.apply_mappings')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.get_size')
    def test__get_size(self, get_size, apply_mappings):
        self.assertEqual(self.cloud_driver._get_size('large'), get_size.return_value)
        apply_mappings.assert_called_with('flavors', 'large')
        get_size.assert_called_with(apply_mappings.return_value)

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.connection')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._get_resource_by_attr')
    def test_get_size(self, _get_resource_by_attr, connection):
        self.assertEqual(self.cloud_driver.get_size('512mb'), _get_resource_by_attr.return_value)
        _get_resource_by_attr.assert_called_with(connection.list_sizes, 'name', '512mb')

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.connection')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._get_resource_by_attr')
    def test_get_location(self, _get_resource_by_attr, connection):
        self.assertEqual(self.cloud_driver._get_location('fra1'), _get_resource_by_attr.return_value)
        _get_resource_by_attr.assert_called_with(connection.list_locations, 'id', 'fra1')

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.connection')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._get_size')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._get_image')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._get_location')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._add_key_pair_info')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver._add_script_info')
    def test_create_node(self, _add_script_info, _add_key_pair_info, _get_location, _get_image, _get_size, connection):
        node = cloud_models.Node(name='web1',
                                 image='127237412',
                                 flavor='512mb',
                                 networks=[],
                                 disk=27)

        def _add_key_pair_info_side_effect(kwargs):
            kwargs['added_key_pair_info'] = True

        def _add_script_info_side_effect(node, kwargs):
            kwargs['added_script_info'] = True

        _add_key_pair_info.side_effect = _add_key_pair_info_side_effect
        _add_script_info.side_effect = _add_script_info_side_effect

        self.cloud_driver.create_node(node)

        _get_image.assert_called_with('127237412')
        _get_size.assert_called_with('512mb')

        connection.create_node.assert_called_with(name='web1',
                                                  image=_get_image.return_value,
                                                  size=_get_size.return_value,
                                                  location=_get_location.return_value,
                                                  added_key_pair_info=True,
                                                  added_script_info=True)

    def test_add_key_pair_info_no_keypair(self):
        kwargs = {}
        self.cloud_driver._add_key_pair_info(kwargs)
        self.assertEqual(kwargs, {})

    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.find_or_import_keypair_by_key_material')
    @mock.patch('aasemble.deployment.cloud.digitalocean.DigitalOceanDriver.expand_path')
    def test_add_keypair_info(self, expand_path, find_or_import_keypair_by_key_material):
        kwargs = {}
        self.cloud_driver.ssh_key_file = 'foo'

        expand_path.return_value = os.path.join(os.path.dirname(__file__), 'fakepubkey')
        find_or_import_keypair_by_key_material.return_value = {'keyName': 'thekeyname',
                                                               'keyFingerprint': 'thefingerprint'}

        self.cloud_driver._add_key_pair_info(kwargs)

        expand_path.assert_called_with('foo')
        find_or_import_keypair_by_key_material.assert_called_with('this is not a real key')
        self.assertEqual(kwargs, {'ex_create_attr': {'ssh_keys': ['thefingerprint']}})

    def test_add_script_info_no_script(self):
        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[])

        kwargs = {}
        self.cloud_driver._add_script_info(node, kwargs)
        self.assertEqual(kwargs, {})

    def test_add_script_info(self):
        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[],
                                 script='foobar')

        kwargs = {}
        self.cloud_driver._add_script_info(node, kwargs)
        self.assertEqual(kwargs, {'ex_user_data': 'foobar'})

    @mock.patch('aasemble.deployment.cloud.digitalocean.get_pubkey_openssh_fingerprint')
    def test_get_fingerprint(self, get_pubkey_openssh_fingerprint):
        rv = self.cloud_driver.get_fingerprint('pubkey')
        get_pubkey_openssh_fingerprint.assert_called_with('pubkey')
        self.assertEqual(rv, get_pubkey_openssh_fingerprint.return_value)

    def test_cluster_data(self):
        collection = cloud_models.Collection()

        lb = cloud_models.Node(name='lb', image='trusty', flavor='512mb', disk=27, networks=[])
        web1 = cloud_models.Node(name='web1', image='trusty', flavor='512mb', disk=27, networks=[])
        web2 = cloud_models.Node(name='web2', image='trusty', flavor='512mb', disk=27, networks=[])
        db = cloud_models.Node(name='db', image='trusty', flavor='512mb', disk=27, networks=[])

        frontend_sg = cloud_models.SecurityGroup(name='frontend')
        frontend_http_sgr = cloud_models.SecurityGroupRule(security_group=frontend_sg, source_ip='0.0.0.0/0', from_port=80, to_port=80, protocol='tcp')
        frontend_https_sgr = cloud_models.SecurityGroupRule(security_group=frontend_sg, source_ip='0.0.0.0/0', from_port=443, to_port=443, protocol='tcp')
        lb.security_groups.add(frontend_sg)

        backend_sg = cloud_models.SecurityGroup(name='backend')
        backend_http_sgr = cloud_models.SecurityGroupRule(security_group=backend_sg, source_group='frontend', from_port=80, to_port=80, protocol='tcp')
        web1.security_groups.add(backend_sg)
        web2.security_groups.add(backend_sg)

        db_sg = cloud_models.SecurityGroup(name='mysql')
        mysql_sgr = cloud_models.SecurityGroupRule(security_group=db_sg, source_group='backend', from_port=3306, to_port=3306, protocol='tcp')
        db.security_groups.add(db_sg)

        collection.nodes.add(lb)
        collection.nodes.add(web1)
        collection.nodes.add(web2)
        collection.nodes.add(db)
        collection.nodes.add(db)
        collection.security_groups.add(frontend_sg)
        collection.security_groups.add(backend_sg)
        collection.security_groups.add(db_sg)
        collection.security_group_rules.add(frontend_http_sgr)
        collection.security_group_rules.add(frontend_https_sgr)
        collection.security_group_rules.add(backend_http_sgr)
        collection.security_group_rules.add(mysql_sgr)

        collection.urls.append(cloud_models.URLConfStatic(hostname='example.com', path='/foo/bar', local_path='/data'))
        collection.urls.append(cloud_models.URLConfBackend(hostname='example.com', path='/foo/bar', destination='somebackend/somepath'))
        self.maxDiff = None
        self.assertEqual(self.cloud_driver.cluster_data(collection),
                         {'containers': [{'host_network': True,
                                          'image': 'aasemble/fwmanager',
                                          'name': 'fwmanager',
                                          'nodes': '.*',
                                          'privileged': True}],
                          'proxyconf': {'backends': ['somebackend'],
                                        'domains': {'example.com': {'/foo/bar': {'destination': 'somebackend/somepath',
                                                                                 'type': 'backend'}}}},
                          'fwconf': {'security_groups': {'backend': {'nodes': ['web1', 'web2'],
                                                                     'rules': [{'from_port': 80,
                                                                                'protocol': 'tcp',
                                                                                'source_group': 'frontend',
                                                                                'to_port': 80}]},
                                                         'frontend': {'nodes': ['lb'],
                                                                      'rules': [{'from_port': 80,
                                                                                 'protocol': 'tcp',
                                                                                 'source_ip': '0.0.0.0/0',
                                                                                 'to_port': 80},
                                                                                {'from_port': 443,
                                                                                 'protocol': 'tcp',
                                                                                 'source_ip': '0.0.0.0/0',
                                                                                 'to_port': 443}]},
                                                         'mysql': {'nodes': ['db'],
                                                                   'rules': [{'from_port': 3306,
                                                                              'protocol': 'tcp',
                                                                              'source_group': 'backend',
                                                                              'to_port': 3306}]}}}})
