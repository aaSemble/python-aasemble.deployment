import logging

import aasemble.deployment.cloud.models as cloud_models
from aasemble.deployment.runner import load_yaml

LOG = logging.getLogger(__name__)


def load(fpath):
    data = load_yaml(fpath)
    collection = cloud_models.Collection()

    for node in build_nodes(data):
        collection.nodes.add(node)

    security_groups, security_group_rules = build_security_groups_and_rules(data)

    for security_group in security_groups:
        collection.security_groups.add(security_group)

    for security_group_rule in security_group_rules:
        collection.security_group_rules.add(security_group_rule)

    collection.connect()
    return collection


def build_nodes(data):
    collection = set()
    for name in data.get('nodes', {}):
        node_info = data['nodes'][name]
        if 'count' in node_info:
            names = ['%s%d' % (name, idx) for idx in range(1, node_info['count'] + 1)]
        else:
            names = [name]

        for name in names:
            LOG.info('Loaded node %s from stack' % name)
            node = cloud_models.Node(name=name,
                                     flavor=node_info['flavor'],
                                     image=node_info['image'],
                                     disk=node_info['disk'],
                                     export=node_info['export'],
                                     networks=node_info.get('networks', []))
            node.security_group_names = node_info.get('security_groups', [])
            collection.add(node)
    return collection


def build_security_groups_and_rules(data):
    security_groups = set()
    security_group_rules = set()
    for name in data.get('security_groups', {}):
        LOG.info('Loaded security group %s from stack' % name)
        security_group_info = data['security_groups'][name]
        security_group = cloud_models.SecurityGroup(name=name)
        security_groups.add(security_group)
        for rule in security_group_info:
            LOG.info('Loaded security group rule from stack: %s: %d-%d' % (rule['protocol'], rule['from_port'], rule['to_port']))
            security_group_rule = cloud_models.SecurityGroupRule(security_group=security_group,
                                                                 source_ip=rule['cidr'],
                                                                 from_port=rule['from_port'],
                                                                 to_port=rule['to_port'],
                                                                 protocol=rule['protocol'])
            security_group_rules.add(security_group_rule)
    return security_groups, security_group_rules
