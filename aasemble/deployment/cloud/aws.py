import logging

from libcloud.common.exceptions import BaseHTTPError
from libcloud.compute.types import Provider

import aasemble.deployment.cloud.models as cloud_models
from aasemble.deployment.cloud.base import CloudDriver

LOG = logging.getLogger(__name__)


class AWSDriver(CloudDriver):
    provider = Provider.EC2
    name = 'Amazon EC2'

    def __init__(self, *args, **kwargs):
        self.region = kwargs.pop('region')
        self.access_key = kwargs.pop('access_key')
        self.secret_key = kwargs.pop('secret_key')
        self.ssh_key_file = kwargs.pop('ssh_key_file', None)
        self._sg_name_to_id = {}
        self._sg_id_to_name = {}
        self._volume_size_map = None
        super(AWSDriver, self).__init__(*args, **kwargs)

    @classmethod
    def get_kwargs_from_cloud_config(cls, cfgparser):
        kwargs = {'access_key': cfgparser.get('connection', 'access_key'),
                  'secret_key': cfgparser.get('connection', 'secret_key'),
                  'region': cfgparser.get('connection', 'region')}

        if cfgparser.has_option('connection', 'sshkey'):
            kwargs['ssh_key_file'] = cfgparser.get('connection', 'sshkey')

        return kwargs

    def _get_driver_args_and_kwargs(self):
        return ((self.access_key, self.secret_key),
                {'region': self.region})

    @property
    def volume_size_map(self):
        if self._volume_size_map is None:
            self._volume_size_map = {}
            for volume in self.connection.list_volumes():
                self._volume_size_map[volume.id] = volume.size
        return self._volume_size_map

    def _refresh_sg_name_id_map(self):
        self._sg_id_to_name = {}
        self._sg_name_to_id_map = {}
        for sg in self.connection.ex_get_security_groups():
            self._sg_id_to_name[sg.id] = sg.name
            self._sg_name_to_id[sg.name] = sg.id

    def sg_id_to_name(self, id):
        try:
            return self._sg_id_to_name[id]
        except KeyError:
            self._refresh_sg_name_id_map()
            return self._sg_id_to_name[id]

    def sg_name_to_id(self, name):
        try:
            return self._sg_name_to_id[name]
        except KeyError:
            self._refresh_sg_name_id_map()
            return self._sg_name_to_id[name]

    def get_namespace(self, node):
        if 'tags' not in node.private.extra:
            return None

        if 'aasemble_namespace' in node.private.extra['tags']:
            return node.private.extra['tags']['aasemble_namespace']

    def _is_node_relevant(self, node):
        if node.state in ('terminated', 'shutting-down', 'unknown'):
            return False
        return super(AWSDriver, self)._is_node_relevant(node)

    def _aasemble_node_from_provider_node(self, ec2node):
        node = cloud_models.Node(name=ec2node.name,
                                 flavor=ec2node.size,
                                 image=ec2node.image,
                                 disk=self.volume_size_map[ec2node.extra['block_device_mapping'][0]['ebs']['volume_id']],
                                 networks=[],
                                 private=ec2node)
        node.security_group_names = set((v['group_name'] for v in ec2node.extra['groups']))
        return node

    def detect_firewalls(self):
        security_group_set = set()
        security_group_rule_set = set()

        for security_group in self.connection.ex_get_security_groups():
            sg = cloud_models.SecurityGroup(name=security_group.name)
            security_group_set.add(sg)

            for rule in security_group.ingress_rules:
                kwargs = {'security_group': sg,
                          'from_port': rule['from_port'] and int(rule['from_port']),
                          'to_port': rule['to_port'] and int(rule['to_port']),
                          'protocol': rule['protocol']}

                if 'cidr_ips' in rule and rule['cidr_ips']:
                    kwargs['source_ip'] = rule['cidr_ips'][0]
                else:
                    kwargs['source_group'] = self.sg_id_to_name(rule['group_pairs'][0]['group_id'])

                sgr = cloud_models.SecurityGroupRule(**kwargs)
                security_group_rule_set.add(sgr)

        return security_group_set, security_group_rule_set

    def _get_image(self, image):
        return self.connection.get_image(self.apply_mappings('images', image))

    def _get_size_real(self, size_name):
        return [s for s in self.connection.list_sizes() if s.id == size_name][0]

    def _get_size(self, flavor):
        return self._get_size_real(self.apply_mappings('flavors', flavor))

    def create_node(self, node):
        LOG.info('Launching node: %s' % (node.name))

        image = self._get_image(node.image)
        size = self._get_size(node.flavor)

        kwargs = {'name': node.name,
                  'size': size,
                  'image': image,
                  'ex_security_groups': [sg.name for sg in node.security_groups],
                  'ex_blockdevicemappings': [self._block_device_mappings(node)]}

        self._add_key_pair_info(kwargs)
        self._add_script_info(node, kwargs)
        self._add_namespace_info(kwargs)

        node.private = self.connection.create_node(**kwargs)

        LOG.info('Launced node: %s %r' % (node.name, kwargs))

    def _add_key_pair_info(self, kwargs):
        if self.ssh_key_file:
            with open(self.expand_path(self.ssh_key_file), 'r') as fp:
                kwargs['ex_keyname'] = self.connection.ex_find_or_import_keypair_by_key_material(fp.read().rstrip())['keyName']

    def _add_script_info(self, node, kwargs):
        if node.script is not None:
            kwargs['ex_userdata'] = node.script

    def _add_namespace_info(self, kwargs):
        if self.namespace is not None:
            kwargs['ex_metadata'] = {'aasemble_namespace': self.namespace}

    def create_security_group(self, security_group):
        LOG.info('Creating security group: %s' % (security_group))
        try:
            security_group.private = self.connection.ex_create_security_group(security_group.name, 'some description')
        except BaseHTTPError as e:
            if not e.message.startswith('InvalidGroup.Duplicate'):
                raise

    def create_security_group_rule(self, security_group_rule):
        LOG.info('Creating firewall rule: %s' % (security_group_rule))

        kwargs = {'id': self.sg_name_to_id(security_group_rule.security_group.name),
                  'from_port': security_group_rule.from_port,
                  'to_port': security_group_rule.to_port,
                  'protocol': security_group_rule.protocol}

        if security_group_rule.source_group is not None:
            kwargs['group_pairs'] = [{'group_name': security_group_rule.source_group}]
        else:
            kwargs['cidr_ips'] = [security_group_rule.source_ip]

        self.connection.ex_authorize_security_group_ingress(**kwargs)

    def _block_device_mappings(self, node):
        return {'DeviceName': '/dev/sda1', 'Ebs.VolumeSize': node.disk}

    def cluster_data(self, collection):
        data = {}
        proxyconf = {}
        domains = {}
        backends = set()

        if collection.original_collection:
            collection = collection.original_collection

        for url in collection.urls:
            if url.hostname not in domains:
                domains[url.hostname] = {}

            if type(url) == cloud_models.URLConfBackend:
                domains[url.hostname][url.path] = {'type': 'backend',
                                                   'destination': url.destination}
                backends.add(url.destination.split('/')[0])

        proxyconf['domains'] = domains
        proxyconf['backends'] = list(backends)
        data['proxyconf'] = proxyconf
        return data
