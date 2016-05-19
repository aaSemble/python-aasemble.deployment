import json
import logging
import threading

from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider

from aasemble.deployment.cloud.base import CloudDriver
import aasemble.deployment.cloud.models as cloud_models

LOG = logging.getLogger(__name__)


class GCEDriver(CloudDriver):
    provider = Provider.GCE

    def __init__(self, *args, **kwargs):
        self.gce_key_file = kwargs.pop('gce_key_file')
        self.location = kwargs.pop('location')
        super(GCEDriver, self).__init__(*args, **kwargs)
        self.locals = threading.local()

    @classmethod
    def get_kwargs_from_cloud_config(cls, cfgparser):
        return {'gce_key_file': cfgparser.get('connection', 'key_file'),
                'location': cfgparser.get('connection', 'location')}

    @property
    def connection(self):
        if not hasattr(self.locals, '_connection'):
            driver = get_driver(self.provider)
            driver_args, driver_kwargs = self._get_driver_args_and_kwargs()
            LOG.info('Connecting to Google Compute Engine')
            self.locals._connection = driver(*driver_args, **driver_kwargs)

        return self.locals._connection

    def _get_driver_args_and_kwargs(self):
        with open(self.gce_key_file, 'r') as fp:
            key_data = json.load(fp)
        return ((key_data['client_email'], self.gce_key_file),
                {'project': key_data['project_id'],
                 'datacenter': self.location})

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

    def detect_nodes(self):
        nodes = set()
        volume_sizes = self._get_volume_size_map()

        for gcenode in self.connection.list_nodes():
            node = cloud_models.Node(name=gcenode.name,
                                     flavor=gcenode.size,
                                     image=gcenode.image,
                                     disk=volume_sizes[gcenode.extra['disks'][0]['source']],
                                     networks=[])
            node.security_group_names = set(gcenode.extra['tags'])
            nodes.add(node)
            LOG.info('Detected node: %s' % node.name)

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
            LOG.info('Detected security group: %s' % security_group_name)
            security_group = cloud_models.SecurityGroup(name=security_group_name)
            security_groups[security_group_name] = security_group
            security_group_set.add(security_group)

        for firewall in firewalls:
            for tag in (firewall.target_tags or ['global']):
                for allowed in firewall.allowed:
                    from_port, to_port = self._parse_port_spec(allowed)
                    protocol = allowed['IPProtocol']
                    security_group_rule = cloud_models.SecurityGroupRule(security_group=security_groups[tag],
                                                                         source_ip='0.0.0.0/0',
                                                                         from_port=from_port,
                                                                         to_port=to_port,
                                                                         protocol=protocol)
                    LOG.info('Detected security group rule for security group %s: %s: %d-%d' % (tag, protocol, from_port, to_port))
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

    def _parse_port_spec(self, allowed):
        if 'ports' in allowed:
            port_spec = allowed['ports'][0]
            if '-' in port_spec:
                from_port, to_port = port_spec.split('-')
                from_port, to_port = int(from_port), int(to_port)
            else:
                from_port = to_port = int(port_spec)
            return from_port, to_port
        else:
            return 0, 65535

    def create_node(self, node):
        LOG.info('Launching node: %s' % (node.name))

        kwargs = {'name': node.name,
                  'size': self.apply_mappings('flavors', node.flavor),
                  'image': None,
                  'ex_disks_gce_struct': self._disk_struct(node),
                  'ex_tags': [sg.name for sg in node.security_groups]}

        if node.script is not None:
            kwargs['ex_metadata'] = {'items': [{'key': 'startup-script',
                                                'value': node.script}]}
        self.connection.create_node(**kwargs)

        LOG.info('Launced node: %s' % (node.name))

    def create_security_group_rule(self, security_group_rule):
        name = '%s-%s-%s-%s' % (security_group_rule.security_group.name,
                                security_group_rule.protocol,
                                security_group_rule.from_port,
                                security_group_rule.to_port)
        LOG.info('Creating firewall rule: %s' % (name))
        self.connection.ex_create_firewall(name=name,
                                           allowed=[{'IPProtocol': security_group_rule.protocol,
                                                     'ports': [self._format_ports(security_group_rule)]}],
                                           source_ranges=self._source_ranges(security_group_rule),
                                           target_tags=[security_group_rule.security_group.name])

    def apply_resources(self, collection):
        self.pool.map(self.create_node, collection.nodes)

        self.pool.map(self.create_security_group_rule, collection.security_group_rules)

    def _disk_struct(self, node):
        return [{'boot': True,
                 'autoDelete': True,
                 'initializeParams': {
                     'sourceImage': self._resolve_image_name(self.apply_mappings('images', node.image)),
                     'diskType': self._get_disk_type('pd-ssd'),
                     'diskSizeGb': node.disk}}]

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

    def _resolve_image_name(self, name):
        for image in self.connection.list_images():
            if image.name == name:
                return image.extra['selfLink']

    def _get_disk_type(self, name):
        for disktype in self.connection.ex_list_disktypes(self.location):
            if disktype.name == name:
                return disktype.extra['selfLink']
