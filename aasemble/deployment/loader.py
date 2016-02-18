import aasemble.deployment.cloud.models as cloud_models
from aasemble.deployment.runner import load_yaml

def load(fpath):
    data = load_yaml(fpath)
    collection = set()

    collection |= build_nodes(data)
    collection |= build_security_groups_and_rules(data)
    return collection


def build_nodes(data):
    collection = set()
    for name in data.get('nodes', {}):
        node_info = data['nodes'][name]
        if 'count' in node_info:
            names = ['%s%d' % (name, idx) for idx in range(1, node_info['count']+1)]
        else:
            names = [name]

        for name in names:
            node = cloud_models.Node(name=name,
                                     flavor=node_info['flavor'],
                                     image=node_info['image'],
                                     disk=node_info['disk'],
                                     export=node_info['export'],
                                     networks=node_info.get('networks', []))
            collection.add(node)
    return collection


def build_security_groups_and_rules(data):
    collection = set()
    for name in data.get('security_groups', {}):
        security_group_info = data['security_groups'][name]
        security_group = cloud_models.SecurityGroup(name=name)
        collection.add(security_group)
        for rule in data['security_groups'][name]:
            security_group_rule = cloud_models.SecurityGroupRule(security_group=security_group,
                                                                 source_ip=rule['cidr'],
                                                                 from_port=rule['from_port'],
                                                                 to_port=rule['to_port'],
                                                                 protocol=rule['protocol'])
            collection.add(security_group_rule)
    return collection
