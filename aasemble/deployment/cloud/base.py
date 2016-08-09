import json
import logging
import os.path
import re
import shlex
import threading
from multiprocessing.pool import ThreadPool

from libcloud.compute.providers import get_driver
from libcloud.utils.publickey import get_pubkey_comment

import aasemble.client
import aasemble.deployment.cloud.models as cloud_models

LOG = logging.getLogger(__name__)
THREADS = 10  # These are really, really lightweight


class CloudDriver(object):
    def __init__(self, namespace=None, mappings=None, pool=None, cluster=None):
        self.mappings = mappings or {}
        self.pool = pool or ThreadPool(THREADS)
        self.secgroups = {}
        self.namespace = namespace
        self.cluster = cluster and aasemble.client.Cluster(cluster) or None
        self.locals = threading.local()

    @property
    def connection(self):
        if not hasattr(self.locals, '_connection'):
            driver = get_driver(self.provider)
            driver_args, driver_kwargs = self._get_driver_args_and_kwargs()
            LOG.info('Connecting to {}'.format(self.name))
            self.locals._connection = driver(*driver_args, **driver_kwargs)

        return self.locals._connection

    def _is_node_relevant(self, node):
        return self.namespace is None or self.get_namespace(node) == self.namespace

    def detect_nodes(self):
        nodes = set()

        for node in self._get_relevant_nodes():
            aasemble_node = self._aasemble_node_from_provider_node(node)
            nodes.add(aasemble_node)
            LOG.info('Detected node: %s' % aasemble_node.name)

        return nodes

    def _get_relevant_nodes(self):
        for node in self.connection.list_nodes():
            if self._is_node_relevant(node):
                yield node

    def detect_resources(self):
        collection = cloud_models.Collection()

        LOG.info('Detecting nodes')
        for node in self.detect_nodes():
            collection.nodes.add(node)

        LOG.info('Detecting security groups and security group rules')

        security_groups, security_group_rules = self.detect_firewalls()

        for security_group in security_groups:
            collection.security_groups.add(security_group)

        for security_group_rule in security_group_rules:
            collection.security_group_rules.add(security_group_rule)

        collection.connect()

        return collection

    def apply_mappings(self, obj_type, name):
        return self.mappings.get(obj_type, {}).get(name, name)

    def update_cluster(self, collection):
        if self.cluster:
            self.cluster.update(json=self.cluster_json(collection))

    def apply_resources(self, collection):
        self.update_cluster(collection)
        self.pool.map(self.create_security_group, collection.security_groups)
        self.pool.map(self.create_node, collection.nodes)
        self.pool.map(self.create_security_group_rule, collection.security_group_rules)

    def delete_node(self, node):
        self.connection.destroy_node(node.private)

    def delete_security_group(self, security_group):
        pass

    def delete_security_group_rule(self, security_group_rule):
        pass

    def clean_resources(self, collection):
        self.pool.map(self.delete_node, collection.nodes)
        self.pool.map(self.delete_security_group_rule, collection.security_group_rules)
        self.pool.map(self.delete_security_group, collection.security_groups)

    def expand_path(self, path):
        return os.path.expanduser(path)

    def _get_resource_by_attr(self, f, attr, match):
        return [x for x in f() if getattr(x, attr) == match][0]

    def find_key_pair_by_fingerprint(self, fingerprint):
        return self._get_resource_by_attr(self.connection.list_key_pairs, 'fingerprint', fingerprint)

    def find_or_import_keypair_by_key_material(self, pubkey):
        key_fingerprint = self.get_fingerprint(pubkey)
        key_comment = get_pubkey_comment(pubkey, default='unnamed')
        key_name = '%s-%s' % (key_comment, key_fingerprint)

        try:
            kp = self.find_key_pair_by_fingerprint(key_fingerprint)
        except IndexError:
            kp = self.connection.create_key_pair(key_name, pubkey)

        result = {'keyName': kp.name,
                  'keyFingerprint': kp.fingerprint}

        return result

    def cluster_json(self, collection):
        return json.dumps(self.cluster_data(collection))

    def default_containers(self, collection):
        return []

    def cluster_data(self, collection):
        collection = collection.original_collection or collection

        data = {}
        data['containers'] = self.default_containers(collection)
        data['containers'] += collection.containers

        return data  # pragma: nocover

    def get_matcher_factory(self, **kwargs):
        def get_matcher(imagespec):
            rules = shlex.split(imagespec, ' ')
            matchers = []

            def build_matcher(regex, f):
                def matcher(image):
                    return bool(re.compile(regex).match(f(image)))
                return matcher

            for rule in rules:
                key, value = rule.split(':', 1)
                if key in kwargs:
                    matchers += [build_matcher(value, kwargs[key])]

            return lambda i: all(map(lambda f: f(i), matchers))
        return get_matcher
