import logging

from libcloud.compute.types import Provider
from libcloud.utils.publickey import get_pubkey_openssh_fingerprint

import aasemble.deployment.cloud.models as cloud_models
from aasemble.deployment.cloud.base import CloudDriver

LOG = logging.getLogger(__name__)


class DigitalOceanDriver(CloudDriver):
    provider = Provider.DIGITAL_OCEAN
    name = 'Digital Ocean'

    def __init__(self, *args, **kwargs):
        self.location = kwargs.pop('location')
        self.api_key = kwargs.pop('api_key')
        self.ssh_key_file = kwargs.pop('ssh_key_file', None)
        self._size_cache = {}
        super(DigitalOceanDriver, self).__init__(*args, **kwargs)

    @classmethod
    def get_kwargs_from_cloud_config(cls, cfgparser):
        kwargs = {'api_key': cfgparser.get('connection', 'api_key'),
                  'location': cfgparser.get('connection', 'location')}

        if cfgparser.has_option('connection', 'sshkey'):
            kwargs['ssh_key_file'] = cfgparser.get('connection', 'sshkey')

        return kwargs

    def _get_driver_args_and_kwargs(self):
        return ((self.api_key,), {'api_version': 'v2'})

    def get_namespace(self, node):  # pragma: nocover
        return None

    def _is_node_relevant(self, node):
        if node.state in ('off',):
            return False
        return super(DigitalOceanDriver, self)._is_node_relevant(node)

    def get_size(self, size_name):
        if size_name not in self._size_cache:
            self._size_cache[size_name] = self._get_resource_by_attr(self.connection.list_sizes, 'name', size_name)
        return self._size_cache[size_name]

    def _aasemble_node_from_provider_node(self, donode):
        node = cloud_models.Node(name=donode.name,
                                 flavor=donode.extra['size_slug'],
                                 image=donode.extra['image']['id'],
                                 disk=self.get_size(donode.extra['size_slug']).disk,
                                 networks=[],
                                 private=donode)
        node.security_group_names = set()
        return node

    def detect_firewalls(self):
        return set(), set()

    def _get_image(self, image):
        return self.connection.get_image(self.apply_mappings('images', image))

    def _get_size(self, flavor):
        return self.get_size(self.apply_mappings('flavors', flavor))

    def _get_location(self, location_name):
        return self._get_resource_by_attr(self.connection.list_locations, 'id', location_name)

    def create_node(self, node):
        LOG.info('Launching node: %s' % (node.name))

        image = self._get_image(node.image)
        size = self._get_size(node.flavor)
        location = self._get_location(self.location)

        kwargs = {'name': node.name,
                  'size': size,
                  'location': location,
                  'image': image}

        self._add_key_pair_info(kwargs)
        self._add_script_info(node, kwargs)

        node.private = self.connection.create_node(**kwargs)

        LOG.info('Launched node: %s' % (node.name,))

    def _add_key_pair_info(self, kwargs):
        if self.ssh_key_file:
            with open(self.expand_path(self.ssh_key_file), 'r') as fp:
                if 'ex_create_attr' not in kwargs:
                    kwargs['ex_create_attr'] = {}
                kwargs['ex_create_attr']['ssh_keys'] = [self.find_or_import_keypair_by_key_material(fp.read().rstrip())['keyFingerprint']]

    def _add_script_info(self, node, kwargs):
        if node.script is not None:
            kwargs['ex_user_data'] = node.script

    def create_security_group(self, security_group):  # pragma: nocover
        pass

    def create_security_group_rule(self, security_group_rule):  # pragma: nocover
        pass

    def get_fingerprint(self, pubkey):
        return get_pubkey_openssh_fingerprint(pubkey)

    def default_containers(self, collection):
        return [{'image': 'aasemble/fwmanager',
                 'name': 'fwmanager',
                 'privileged': True,
                 'host_network': True,
                 'nodes': '.*'}]

    def cluster_data(self, collection):
        data = super(DigitalOceanDriver, self).cluster_data(collection)
        proxyconf = {}
        fwconf = {'security_groups': {}}
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

        for node in collection.nodes:
            for sg in node.security_groups:
                if sg.name not in fwconf['security_groups']:
                    fwconf['security_groups'][sg.name] = {'nodes': [],
                                                          'rules': []}
                fwconf['security_groups'][sg.name]['nodes'].append(node.name)

        for sgr in collection.security_group_rules:
            rule = {}

            if sgr.source_ip:
                rule['source_ip'] = sgr.source_ip
            elif sgr.source_group:
                rule['source_group'] = sgr.source_group

            if sgr.from_port and sgr.to_port:
                rule['from_port'] = sgr.from_port
                rule['to_port'] = sgr.to_port

            if sgr.protocol:
                rule['protocol'] = sgr.protocol

            fwconf['security_groups'][sgr.security_group.name]['rules'].append(rule)

        for sg in fwconf['security_groups']:
            fwconf['security_groups'][sg]['nodes'].sort()
            fwconf['security_groups'][sg]['rules'].sort()

        proxyconf['domains'] = domains
        proxyconf['backends'] = list(backends)
        data['proxyconf'] = proxyconf
        data['fwconf'] = fwconf
        return data
