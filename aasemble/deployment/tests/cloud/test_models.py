import unittest

import mock

from aasemble.deployment.cloud import models


class NamedItem(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class NamedSetTests(unittest.TestCase):
    def test_new_is_empty(self):
        s = models.NamedSet()
        self.assertEquals(list(s), [])

    def test_add(self):
        s = models.NamedSet()
        item = NamedItem('thename')
        s.add(item)
        self.assertIn(item, s)

    def test_remove_by_name(self):
        s = models.NamedSet()
        item = NamedItem('thename')
        s.add(item)
        s.remove(name='thename')
        self.assertNotIn(item, s)

    def test_remove_by_item(self):
        s = models.NamedSet()
        item = NamedItem('thename')
        s.add(item)
        s.remove(item)
        self.assertNotIn(item, s)

    def test_remove_no_args(self):
        s = models.NamedSet()
        self.assertRaises(TypeError, s.remove)

    def test_subtract(self):
        s1 = models.NamedSet()
        s2 = models.NamedSet()
        item1 = NamedItem('thename1')
        item2 = NamedItem('thename2')
        item3 = NamedItem('thename3')

        s1.add(item1)
        s2.add(item1)

        s1.add(item2)

        s2.add(item3)

        s_diff = s1 - s2

        self.assertIn(item1, s1, 's1 was modified')
        self.assertIn(item2, s1, 's1 was modified')
        self.assertNotIn(item3, s1, 's1 was modified')

        self.assertIn(item1, s2, 's2 was modified')
        self.assertNotIn(item2, s2, 's2 was modified')
        self.assertIn(item3, s2, 's2 was modified')

        self.assertNotIn(item1, s_diff, 'item1 was not removed')
        self.assertIn(item2, s_diff, 'item2 was wrongfully removed')
        self.assertNotIn(item3, s_diff, 'item3 appeared out of nowhere')

    def test_eq(self):
        s1 = models.NamedSet()
        s2 = models.NamedSet()
        item1 = NamedItem('thename1')
        item2 = NamedItem('thename2')

        s1.add(item1)
        s2.add(item1)
        s1.add(item2)
        s2.add(item2)

        self.assertEquals(s1, s2)

    def test_not_eq(self):
        s1 = models.NamedSet()
        s2 = models.NamedSet()
        item1 = NamedItem('thename1')
        item2 = NamedItem('thename2')

        s1.add(item1)
        s2.add(item2)

        self.assertNotEquals(s1, s2)

    def test_iter(self):
        s = models.NamedSet()
        item1 = NamedItem('thename1')
        item2 = NamedItem('thename2')
        s.add(item1)
        s.add(item2)

        s_ = set([item1, item2])

        for x in s:
            s_.remove(x)

        self.assertEquals(s_, set())


class CollectionTests(unittest.TestCase):
    def test_init(self):
        c = models.Collection()
        self.assertEquals(models.NamedSet(), c.nodes)
        self.assertEquals(models.NamedSet(), c.security_groups)
        self.assertEquals(models.NamedSet(), c.security_group_rules)

    def test_init_with_args(self):
        c = models.Collection(nodes=mock.sentinel.nodes,
                              security_groups=mock.sentinel.security_groups,
                              security_group_rules=mock.sentinel.security_group_rules)
        self.assertEquals(mock.sentinel.nodes, c.nodes)
        self.assertEquals(mock.sentinel.security_groups, c.security_groups)
        self.assertEquals(mock.sentinel.security_group_rules, c.security_group_rules)

    def test_sub(self):
        c1 = models.Collection()
        c2 = models.Collection()

        n1 = NamedItem('node1')
        n2 = NamedItem('node2')
        n3 = NamedItem('node3')
        sg1 = NamedItem('securitygroup1')
        sg2 = NamedItem('securitygroup2')
        sg3 = NamedItem('securitygroup3')
        sgr1 = NamedItem('securitygrouprule1')
        sgr2 = NamedItem('securitygrouprule2')
        sgr3 = NamedItem('securitygrouprule3')

        c1.nodes.add(n1)
        c2.nodes.add(n1)
        c2.nodes.add(n2)
        c2.nodes.add(n3)

        c1.security_groups.add(sg1)
        c2.security_groups.add(sg1)
        c2.security_groups.add(sg2)
        c2.security_groups.add(sg3)

        c1.security_group_rules.add(sgr1)
        c2.security_group_rules.add(sgr1)
        c2.security_group_rules.add(sgr2)
        c2.security_group_rules.add(sgr3)

        c_diff = c2 - c1

        c_expected = models.Collection()
        c_expected.nodes.add(n2)
        c_expected.nodes.add(n3)
        c_expected.security_groups.add(sg2)
        c_expected.security_groups.add(sg3)
        c_expected.security_group_rules.add(sgr2)
        c_expected.security_group_rules.add(sgr3)

        self.assertEquals(c_expected, c_diff)

    def test_connect(self):
        c = models.Collection()

        n = models.Node('node1', 'flavor', 'image', [], 10, True)
        n.security_group_names = ['securitygroup1', 'securitygroup2']
        sg1 = NamedItem('securitygroup1')
        sg2 = NamedItem('securitygroup2')
        sg3 = NamedItem('securitygroup3')

        c.nodes.add(n)
        c.security_groups.add(sg1)
        c.security_groups.add(sg2)
        c.security_groups.add(sg3)

        c.connect()

        self.assertIn(sg1, n.security_groups)
        self.assertIn(sg2, n.security_groups)


class CloudModelTests(unittest.TestCase):
    class TestClass(models.CloudModel):
        id_attrs = ['attr1', 'attr2']

        def __init__(self, attr1, attr2, attr3):
            self.attr1 = attr1
            self.attr2 = attr2
            self.attr3 = attr3

    def test_eq(self):
        tc1 = self.TestClass(mock.sentinel.attr1, mock.sentinel.attr2, mock.sentinel.attr3)
        tc2 = self.TestClass(mock.sentinel.attr1, mock.sentinel.attr2, mock.sentinel.not_attr3)
        self.assertEquals(tc1, tc2)

    def test_not_eq(self):
        tc1 = self.TestClass(mock.sentinel.attr1, mock.sentinel.attr2, mock.sentinel.attr3)
        tc2 = self.TestClass(mock.sentinel.attr1, mock.sentinel.not_attr2, mock.sentinel.attr3)
        self.assertNotEquals(tc1, tc2)
