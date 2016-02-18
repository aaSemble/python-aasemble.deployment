import json

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from aasemble.deployment.cloud.base import CloudDriver
import aasemble.deployment.cloud.models as cloud_models


class GCEDriver(CloudDriver):
    provider = Provider.GCE

    def __init__(self, *args, **kwargs):
        self.gce_key_file = kwargs.pop('gce_key_file')
        super(GCEDriver, self).__init__(*args, **kwargs)
        self._connection = None

    @property
    def connection(self):
        if self._connection is None:
            driver = get_driver(self.provider)
            driver_args, driver_kwargs = self._get_driver_args_and_kwargs()
            self._connection = driver(*driver_args, **driver_kwargs)

        return self._connection

    def _get_driver_args_and_kwargs(self):
        with open(self.gce_key_file, 'r') as fp:
            key_data = json.load(fp)
        return ((key_data['client_email'], self.gce_key_file),
                {'project': key_data['project_id']})

    def detect_resources(self):
        collection = cloud_models.Collection()
        collection.nodes = self.detect_nodes()
        collection.security_groups, collection.security_group_rules = self.detect_firewalls()
        return collection

    def detect_nodes(self):
        nodes = set()
        volume_sizes = self._get_volume_size_map()

        for node in self.connection.list_nodes():
            node = cloud_models.Node(name=node.name,
                                     flavor=node.size,
                                     image=node.image,
                                     disk=volume_sizes[node.extra['disks'][0]['source']],
                                     export=True,
                                     networks=[])
            nodes.add(node)

        return nodes

    def _get_volume_size_map(self):
        volume_sizes = {}
        for volume in self.connection.list_volumes():
            volume_sizes[volume.extra['selfLink']] = volume.size
        return volume_sizes

    def detect_firewalls(self):
        security_group_set = set()
        security_group_rule_set = set()

        firewalls = self.connection.ex_list_firewalls()

        security_group_names = self._get_all_security_group_names(firewalls)

        security_groups = {}
        for security_group_name in security_group_names:
            security_group = cloud_models.SecurityGroup(name=security_group_name)
            security_groups[security_group_name] = security_group
            security_group_set.add(security_group)
       
        for firewall in firewalls:
            for tag in (firewall.target_tags or ['global']):
                port_spec = firewall.allowed[0]['ports'][0]
                from_port, to_port = self._parse_port_spec(port_spec)
                protocol = firewall.allowed[0]['IPProtocol']
                security_group_rule = cloud_models.SecurityGroupRule(security_group=security_groups[tag],
                                                                     source_ip='0.0.0.0/0',
                                                                     from_port=from_port,
                                                                     to_port=to_port,
                                                                     protocol=protocol)
                security_group_rule_set.add(security_group_rule)

        return security_group_set, security_group_rule_set

    def _get_all_security_group_names(self, firewalls):
        security_group_names = set()
        for firewall in firewalls:
            if not firewall.target_tags:
                security_group_names.add('global')
            else:
                security_group_names |= set(firewall.target_tags)
        return security_group_names

    def _parse_port_spec(self, port_spec):
        if '-' in port_spec:
            from_port, to_port = port_spec.split('-')
            from_port, to_port = int(from_port), int(to_port)
        else:
            from_port = to_port = int(port_spec)
        return from_port, to_port

    def apply_resources(self, collection):
        for node in collection.nodes:
            self.connection.create_node(name=node.name,
                                        size=node.flavor,
                                        image=None,
                                        ex_disks_gce_struct=self._disk_struct(node))

        for security_group_rule in collection.security_group_rules:
            name = '%s-%s-%s-%s' % (security_group_rule.security_group.name,
                                    security_group_rule.protocol,
                                    security_group_rule.from_port,
                                    security_group_rule.to_port) 
            self.connection.ex_create_firewall(name=name,
                                               allowed=[{'IPProtocol': security_group_rule.protocol,
                                                         'ports': [self._format_ports(security_group_rule)]}],
                                               source_ranges=self._source_ranges(security_group_rule),
                                               target_tags=[security_group_rule.security_group.name])


    def _disk_struct(self, node):
        return [{'boot': True,
                 'autoDelete': True,
                 'initializeParams': {
                     'sourceImage': 'trusty',
                     'diskType': 'pd-ssd',
                     'diskSizeGb': 37}
                }]

    def _format_ports(self, security_group_rule):
        if security_group_rule.from_port == security_group_rule.to_port:
            return str(security_group_rule.from_port)
        else:
            return '%d-%d' % (security_group_rule.from_port, security_group_rule.to_port)

    def _source_ranges(self, security_group_rule):
        if security_group_rule.source_ip == '0.0.0.0/0':
            return None
        else:
            return [security_group_rule.source_ip]
