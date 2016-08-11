import logging

import aasemble.deployment.cloud.models as cloud_models
from aasemble.deployment.exceptions import UnknownURLType
from aasemble.deployment.utils import interpolate, load_yaml

LOG = logging.getLogger(__name__)


def load(fpath, substitutions=None):
    data = load_yaml(fpath)[0]
    collection = cloud_models.Collection()

    for urlconf in build_urls(data, substitutions):
        collection.urls.append(urlconf)

    for node in build_nodes(data, substitutions):
        collection.nodes.add(node)

    collection.containers = data.get('containers', [])

    security_groups, security_group_rules = build_security_groups_and_rules(data)

    for security_group in security_groups:
        collection.security_groups.add(security_group)

    for security_group_rule in security_group_rules:
        collection.security_group_rules.add(security_group_rule)

    collection.connect()
    return collection


def build_urls(data, substitutions=None):
    urls = []
    for url in data.get('urls', []):
        if url['type'] == 'static':
            urls.append(cloud_models.URLConfStatic(hostname=interpolate(url['hostname'], substitutions),
                                                   path=url['path'],
                                                   local_path=url['local_path']))
            LOG.debug('Loaded static URL %s%s from stack' % (url['hostname'], url['path']))
        elif url['type'] == 'backend':
            urls.append(cloud_models.URLConfBackend(hostname=interpolate(url['hostname'], substitutions),
                                                    path=url['path'],
                                                    destination=url['destination']))
            LOG.debug('Loaded backend URL %s%s from stack' % (url['hostname'], url['path']))
        else:
            raise UnknownURLType(url['type'])

    return urls


def build_nodes(data, substitutions=None):
    collection = set()
    for name in data.get('nodes', {}):
        node_info = data['nodes'][name]
        if 'count' in node_info:
            names = ['%s%d' % (name, idx) for idx in range(1, node_info['count'] + 1)]
        else:
            names = [name]

        for name in names:
            LOG.debug('Loaded node %s from stack' % name)
            node = cloud_models.Node(name=name,
                                     flavor=node_info['flavor'],
                                     image=node_info['image'],
                                     disk=node_info['disk'],
                                     networks=node_info.get('networks', []),
                                     script=interpolate(node_info.get('script', None), substitutions))
            node.security_group_names = node_info.get('security_groups', [])
            collection.add(node)
    return collection


def build_security_groups_and_rules(data):
    security_groups = set()
    security_group_rules = set()
    for name in data.get('security_groups', {}):
        LOG.debug('Loaded security group %s from stack' % name)
        security_group_info = data['security_groups'][name]
        security_group = cloud_models.SecurityGroup(name=name)
        security_groups.add(security_group)
        for rule in security_group_info:
            LOG.debug('Loaded security group rule from stack: %s: %d-%d' % (rule['protocol'], rule['from_port'], rule['to_port']))
            kwargs = {'security_group': security_group,
                      'from_port': rule['from_port'],
                      'to_port': rule['to_port'],
                      'protocol': rule['protocol']}

            if 'cidr' in rule:
                kwargs['source_ip'] = rule['cidr']
            elif 'source_group' in rule:
                kwargs['source_group'] = rule['source_group']

            security_group_rule = cloud_models.SecurityGroupRule(**kwargs)

            security_group_rules.add(security_group_rule)
    return security_groups, security_group_rules
