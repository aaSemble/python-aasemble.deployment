import unittest

import aasemble.deployment.cloud.models as cloud_models


class DiffTestCase(unittest.TestCase):
    def setUp(self):
        self.sg1 = cloud_models.SecurityGroup(name='sg1')
        self.sgr1 = cloud_models.SecurityGroupRule(security_group=self.sg1,
                                                   from_port=443,
                                                   to_port=443,
                                                   source_ip='0.0.0.0/0',
                                                   protocol='tcp')
        self.sgr2 = cloud_models.SecurityGroupRule(security_group=self.sg1,
                                                   from_port=80,
                                                   to_port=80,
                                                   source_ip='0.0.0.0/0',
                                                   protocol='tcp')
        self.node1 = cloud_models.Node(name='node1',
                                       image='image',
                                       flavor='image',
                                       networks=[],
                                       disk=10,
                                       export=True,
                                       security_groups=set([self.sg1]))
        self.current = cloud_models.Collection()
        self.desired = cloud_models.Collection()

    def test_nothing_missing(self):
        self.current.nodes.add(self.node1)
        self.current.security_groups.add(self.sg1)
        self.current.security_group_rules.add(self.sgr1)
        self.current.security_group_rules.add(self.sgr2)
        self.desired.nodes.add(self.node1)
        self.desired.security_groups.add(self.sg1)
        self.desired.security_group_rules.add(self.sgr1)
        self.desired.security_group_rules.add(self.sgr2)

        difference = self.desired - self.current

        self.assertEquals(difference.nodes, set())
        self.assertEquals(difference.security_groups, set())
        self.assertEquals(difference.security_group_rules, set())

    def test_node_missing(self):
        self.current.security_groups.add(self.sg1)
        self.current.security_group_rules.add(self.sgr1)
        self.current.security_group_rules.add(self.sgr2)
        self.desired.nodes.add(self.node1)
        self.desired.security_groups.add(self.sg1)
        self.desired.security_group_rules.add(self.sgr1)
        self.desired.security_group_rules.add(self.sgr2)

        difference = self.desired - self.current

        self.assertEquals(difference.nodes, set([self.node1]))
        self.assertEquals(difference.security_groups, set())
        self.assertEquals(difference.security_group_rules, set())

    def test_security_group_rule_missing(self):
        self.current.nodes.add(self.node1)
        self.current.security_groups.add(self.sg1)
        self.current.security_group_rules.add(self.sgr1)
        self.desired.nodes.add(self.node1)
        self.desired.security_groups.add(self.sg1)
        self.desired.security_group_rules.add(self.sgr1)
        self.desired.security_group_rules.add(self.sgr2)

        difference = self.desired - self.current

        self.assertEquals(difference.nodes, set())
        self.assertEquals(difference.security_groups, set())
        self.assertEquals(difference.security_group_rules, set([self.sgr2]))
