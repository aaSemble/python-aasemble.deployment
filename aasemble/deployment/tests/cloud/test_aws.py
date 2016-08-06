import os.path
import unittest

import libcloud.common.exceptions

import mock

from six.moves import configparser

import aasemble.deployment.cloud.aws as aws
import aasemble.deployment.cloud.models as cloud_models


test_access_key = 'lewirhtqlrhflwdjfhalsf'
test_secret_key = 'l34thl3witton-ehcowoqwiycrowqeyrcowieucfwhicfhaeniuc',


class FakeThreadPool(object):
    def map(self, func, iterable):
        return list(map(func, iterable))


class AWSDriverTests(unittest.TestCase):
    def setUp(self):
        super(AWSDriverTests, self).setUp()
        self.cloud_driver = aws.AWSDriver(access_key=test_access_key,
                                          secret_key=test_secret_key,
                                          region='us-east-1',
                                          pool=FakeThreadPool())

    def _get_base_config(self):
        cp = configparser.ConfigParser()
        cp.add_section('connection')
        cp.set('connection', 'access_key', 'exampleaccesskey')
        cp.set('connection', 'secret_key', 'examplesecretkey')
        cp.set('connection', 'region', 'us-east-1')
        return cp

    def test_get_kwargs_from_cloud_config(self):
        cp = self._get_base_config()
        self.assertEqual(aws.AWSDriver.get_kwargs_from_cloud_config(cp),
                         {'region': 'us-east-1',
                          'access_key': 'exampleaccesskey',
                          'secret_key': 'examplesecretkey'})

    def test_get_kwargs_from_cloud_config_with_ssh_key(self):
        cp = self._get_base_config()
        cp.set('connection', 'sshkey', 'some.key')
        self.assertEqual(aws.AWSDriver.get_kwargs_from_cloud_config(cp),
                         {'region': 'us-east-1',
                          'ssh_key_file': 'some.key',
                          'access_key': 'exampleaccesskey',
                          'secret_key': 'examplesecretkey'})

    def test_get_driver_args_and_kwargs(self):
        self.assertEqual(self.cloud_driver._get_driver_args_and_kwargs(),
                         ((test_access_key, test_secret_key),
                          {'region': 'us-east-1'}))

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_volume_size_map(self, connection):
        class AWSVolume(object):
            def __init__(self, id, size):
                self.id = id
                self.size = size

        connection.list_volumes.return_value = [AWSVolume('vol-126375124', 100), AWSVolume('vol-1ad63253', 200)]

        self.assertEqual(self.cloud_driver.volume_size_map, {'vol-126375124': 100,
                                                             'vol-1ad63253': 200})

    def _sg_list(self):
        class AWSSecurityGroup(object):
            def __init__(self, name, id):
                self.name = name
                self.id = id

        return [AWSSecurityGroup('default', 'sg-541234'),
                AWSSecurityGroup('www', 'sg-64445555')]

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_refresh_sg_name_id_map(self, connection):
        connection.ex_get_security_groups.return_value = self._sg_list()

        self.cloud_driver._refresh_sg_name_id_map()
        self.assertEqual(self.cloud_driver._sg_id_to_name, {'sg-541234': 'default',
                                                            'sg-64445555': 'www'})
        self.assertEqual(self.cloud_driver._sg_name_to_id, {'default': 'sg-541234',
                                                            'www': 'sg-64445555'})

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_sg_name_to_id(self, connection):
        connection.ex_get_security_groups.return_value = self._sg_list()

        self.assertEqual(self.cloud_driver.sg_name_to_id('default'), 'sg-541234')

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_sg_name_to_id_invalid_name(self, connection):
        connection.ex_get_security_groups.return_value = self._sg_list()

        self.assertRaises(KeyError, self.cloud_driver.sg_name_to_id, 'blah')

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_sg_id_to_name(self, connection):
        connection.ex_get_security_groups.return_value = self._sg_list()

        self.assertEqual(self.cloud_driver.sg_id_to_name('sg-541234'), 'default')

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_sg_id_to_name_invalid_id(self, connection):
        connection.ex_get_security_groups.return_value = self._sg_list()

        self.assertRaises(KeyError, self.cloud_driver.sg_id_to_name, 'sg-125371')

    def _test_get_namespace(self, extra, expected_rv):
        class AWSNode(object):
            def __init__(self, extra):
                if extra is not None:
                    self.extra = extra

        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[])
        node.private = AWSNode(extra)
        self.assertEqual(self.cloud_driver.get_namespace(node), expected_rv)

    def test_get_namespace(self):
        self._test_get_namespace({'tags': {'Name': 'lb', 'aasemble_namespace': 'foobar'}}, 'foobar')

    def test_get_namespace_no_tags(self):
        self._test_get_namespace({'other': {}}, None)

    def test_get_namespace_empty_tags(self):
        self._test_get_namespace({'tags': {}}, None)

    def _test_is_node_relevant(self, state, relevant):
        class AWSNode(object):
            def __init__(self, state):
                self.state = state

        self.assertEqual(self.cloud_driver._is_node_relevant(AWSNode(state)), relevant)

    def test_is_node_relevant_when_terminated(self):
        self._test_is_node_relevant('terminated', False)

    def test_is_node_relevant_when_unknown(self):
        self._test_is_node_relevant('unknown', False)

    def test_is_node_relevant_when_shutting_down(self):
        self._test_is_node_relevant('shutting-down', False)

    def test_is_node_relevant_when_running(self):
        self._test_is_node_relevant('running', True)

    def test_aasemble_node_from_provider_node(self):
        class AWSNode(object):
            def __init__(self, name, size, image, vol_id):
                self.name = name
                self.size = size
                self.image = image
                self.extra = {'block_device_mapping': [{'ebs': {'volume_id': vol_id}}],
                              'groups': [{'group_name': 'sg1'}, {'group_name': 'sg2'}]}

        awsnode = AWSNode(name='testnode1', size='m4.large', image='ami-987654abc', vol_id='vol-1234567')
        self.cloud_driver._volume_size_map = {'vol-1234567': 100}
        node = self.cloud_driver._aasemble_node_from_provider_node(awsnode)
        self.assertEqual(node.name, 'testnode1')
        self.assertEqual(node.flavor, 'm4.large')
        self.assertEqual(node.image, 'ami-987654abc')
        self.assertEqual(node.disk, 100)
        self.assertEqual(node.security_group_names, set(['sg1', 'sg2']))
        self.assertEqual(node.private, awsnode)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_detect_firewalls(self, connection):
        class AWSSecurityGroup(object):
            def __init__(self, id, name, ingress_rules):
                self.id = id
                self.name = name
                self.ingress_rules = ingress_rules

        sg1 = AWSSecurityGroup(id='sg-1234567', name='default',
                               ingress_rules=[{'from_port': '80',
                                               'to_port': '81',
                                               'protocol': 'tcp',
                                               'cidr_ips': ['1.2.3.4/32']},
                                              {'from_port': '8080',
                                               'to_port': '8081',
                                               'protocol': 'udp',
                                               'group_pairs': [{'group_id': 'sg-7654321'}]}])

        sg2 = AWSSecurityGroup(id='sg-7654321', name='www', ingress_rules=[])

        connection.ex_get_security_groups.return_value = [sg1, sg2]

        sg1_ = cloud_models.SecurityGroup(name='default')
        sg2_ = cloud_models.SecurityGroup(name='www')

        expected_sgs = set([sg1_, sg2_])
        expected_sgrs = set([cloud_models.SecurityGroupRule(security_group=sg1_,
                                                            from_port=80,
                                                            to_port=81,
                                                            protocol='tcp',
                                                            source_ip='1.2.3.4/32'),
                             cloud_models.SecurityGroupRule(security_group=sg1_,
                                                            from_port=8080,
                                                            to_port=8081,
                                                            protocol='udp',
                                                            source_group='www')])

        self.assertEqual(self.cloud_driver.detect_firewalls(),
                         (expected_sgs, expected_sgrs))

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.apply_mappings')
    def test_get_image(self, apply_mappings, connection):
        self.assertEqual(self.cloud_driver._get_image('ami-1234567'),
                         connection.get_image.return_value)
        apply_mappings.assert_called_with('images', 'ami-1234567')
        connection.get_image.assert_called_with(apply_mappings.return_value)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.apply_mappings')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._get_size_real')
    def test_get_size(self, _get_size_real, apply_mappings):
        self.assertEqual(self.cloud_driver._get_size('m4.xlarge'), _get_size_real.return_value)
        apply_mappings.assert_called_with('flavors', 'm4.xlarge')
        _get_size_real.assert_called_with(apply_mappings.return_value)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_get_size_real(self, connection):
        class Size(object):
            def __init__(self, id):
                self.id = id

        size1 = Size('m4.large')
        size2 = Size('m4.xlarge')
        size3 = Size('m4.2xlarge')

        connection.list_sizes.return_value = [size1, size2, size3]

        self.assertEqual(self.cloud_driver._get_size_real('m4.xlarge'), size2)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._get_size')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._get_image')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._block_device_mappings')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._add_key_pair_info')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._add_script_info')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver._add_namespace_info')
    def test_create_node(self, _add_namespace_info, _add_script_info, _add_key_pair_info, _block_device_mappings, _get_image, _get_size, connection):
        node = cloud_models.Node(name='web1',
                                 image='ami-1234567',
                                 flavor='t2.small',
                                 networks=[],
                                 disk=27)

        def _add_key_pair_info_side_effect(kwargs):
            kwargs['added_key_pair_info'] = True

        def _add_script_info_side_effect(node, kwargs):
            kwargs['added_script_info'] = True

        def _add_namespace_info_side_effect(kwargs):
            kwargs['added_namespace_info'] = True

        _add_key_pair_info.side_effect = _add_key_pair_info_side_effect
        _add_script_info.side_effect = _add_script_info_side_effect
        _add_namespace_info.side_effect = _add_namespace_info_side_effect

        self.cloud_driver.create_node(node)

        _get_image.assert_called_with('ami-1234567')
        _get_size.assert_called_with('t2.small')

        connection.create_node.assert_called_with(name='web1',
                                                  image=_get_image.return_value,
                                                  size=_get_size.return_value,
                                                  ex_security_groups=[],
                                                  ex_blockdevicemappings=[_block_device_mappings.return_value],
                                                  added_key_pair_info=True,
                                                  added_script_info=True,
                                                  added_namespace_info=True)

    def test_add_key_pair_info_no_keypair(self):
        kwargs = {}
        self.cloud_driver._add_key_pair_info(kwargs)
        self.assertEqual(kwargs, {})

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.expand_path')
    def test_add_keypair_info(self, expand_path, connection):
        kwargs = {}
        self.cloud_driver.ssh_key_file = 'foo'

        expand_path.return_value = os.path.join(os.path.dirname(__file__), 'fakepubkey')
        connection.ex_find_or_import_keypair_by_key_material.return_value = {'keyName': 'thekeyname'}

        self.cloud_driver._add_key_pair_info(kwargs)

        expand_path.assert_called_with('foo')
        connection.ex_find_or_import_keypair_by_key_material.assert_called_with('this is not a real key')
        self.assertEqual(kwargs, {'ex_keyname': 'thekeyname'})

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
        self.assertEqual(kwargs, {'ex_userdata': 'foobar'})

    def test_add_namespace_info_no_namespace(self):
        kwargs = {}
        self.cloud_driver._add_namespace_info(kwargs)
        self.assertEqual(kwargs, {})

    def test_add_namespace_info(self):
        kwargs = {}
        self.cloud_driver.namespace = 'foo'
        self.cloud_driver._add_namespace_info(kwargs)

        self.assertEqual(kwargs, {'ex_metadata': {'aasemble_namespace': 'foo'}})

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_add_security_group(self, connection):
        sg = cloud_models.SecurityGroup(name='sg1')
        self.cloud_driver.create_security_group(sg)
        connection.ex_create_security_group.assert_called_with('sg1', 'some description')

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_add_security_group_duplicate_does_not_reaise(self, connection):
        sg = cloud_models.SecurityGroup(name='sg1')
        connection.ex_create_security_group.side_effect = libcloud.common.exceptions.BaseHTTPError(400, 'InvalidGroup.Duplicate: we already have that one')
        self.cloud_driver.create_security_group(sg)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    def test_add_security_group_other_error_raises(self, connection):
        sg = cloud_models.SecurityGroup(name='sg1')
        connection.ex_create_security_group.side_effect = libcloud.common.exceptions.BaseHTTPError(400, 'NotInvalidGroup.NotDuplicate: another error')
        self.assertRaises(libcloud.common.exceptions.BaseHTTPError, self.cloud_driver.create_security_group, sg)

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.sg_name_to_id')
    def test_add_security_group_rule(self, sg_name_to_id, connection):
        sg = cloud_models.SecurityGroup(name='sg')
        sgr = cloud_models.SecurityGroupRule(security_group=sg,
                                             from_port=123,
                                             to_port=234,
                                             source_ip='2.3.4.5',
                                             protocol='tcp')
        self.cloud_driver.create_security_group_rule(sgr)
        connection.ex_authorize_security_group_ingress.assert_called_with(id=sg_name_to_id.return_value,
                                                                          from_port=123,
                                                                          to_port=234,
                                                                          protocol='tcp',
                                                                          cidr_ips=['2.3.4.5'])

    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.connection')
    @mock.patch('aasemble.deployment.cloud.aws.AWSDriver.sg_name_to_id')
    def test_add_security_group_rule_with_source_group(self, sg_name_to_id, connection):
        sg = cloud_models.SecurityGroup(name='sg')
        sgr = cloud_models.SecurityGroupRule(security_group=sg,
                                             from_port=123,
                                             to_port=234,
                                             source_group='www',
                                             protocol='tcp')
        self.cloud_driver.create_security_group_rule(sgr)
        connection.ex_authorize_security_group_ingress.assert_called_with(id=sg_name_to_id.return_value,
                                                                          from_port=123,
                                                                          to_port=234,
                                                                          protocol='tcp',
                                                                          group_pairs=[{'group_name': 'www'}])

    def test_block_device_mappings(self):
        node = cloud_models.Node(name='webapp',
                                 image='trusty',
                                 flavor='n1-standard-2',
                                 disk=37,
                                 networks=[],
                                 script='foobar')
        self.assertEqual(self.cloud_driver._block_device_mappings(node), {'DeviceName': '/dev/sda1', 'Ebs.VolumeSize': 37})

    def test_cluster_data(self):
        collection = cloud_models.Collection()

        collection.urls.append(cloud_models.URLConfStatic(hostname='example.com', path='/foo/bar', local_path='/data'))
        collection.urls.append(cloud_models.URLConfBackend(hostname='example.com', path='/foo/bar', destination='somebackend/somepath'))
        self.assertEqual(self.cloud_driver.cluster_data(collection),
                         {'containers': [],
                          'proxyconf': {'backends': ['somebackend'],
                                        'domains': {'example.com': {'/foo/bar': {'destination': 'somebackend/somepath',
                                                                                 'type': 'backend'}}}}})
