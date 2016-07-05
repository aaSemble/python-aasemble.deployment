#
#   Copyright 2015 Reliance Jio Infocomm, Ltd.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import datetime
import os.path
import unittest

from aasemble.deployment import exceptions, utils


class UtilsTests(unittest.TestCase):
    def test_parse_time_explicit_seconds(self):
        self.assertEqual(utils.parse_time('10s'), 10)

    def test_parse_time_implicit_seconds(self):
        self.assertEqual(utils.parse_time('10'), 10)

    def test_parse_time_minutes(self):
        self.assertEqual(utils.parse_time('10m'), 600)

    def test_parse_time_hours(self):
        self.assertEqual(utils.parse_time('1h'), 3600)
        self.assertEqual(utils.parse_time('2h'), 7200)

    def test_parse_time_zero(self):
        self.assertEqual(utils.parse_time('0'), 0)

    def test_parse_time_invalid_unit(self):
        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '2x')

    def test_parse_time_negative(self):
        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '-10')

    def test_parse_time_negative_with_unit(self):
        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '-10m')

    def test_load_yaml(self):
        self.assertEqual(utils.load_yaml(os.path.join(os.path.dirname(__file__),
                                                      'example.yaml')),
                         [{'Time': datetime.datetime(2001, 11, 23, 20, 1, 42),
                           'User': 'ed',
                           'Warning': 'This is an error message for the log file'},
                          {'Time': datetime.datetime(2001, 11, 23, 20, 2, 31),
                           'User': 'ed',
                           'Warning': 'A slightly different error message.'},
                          {'Date': datetime.datetime(2001, 11, 23, 20, 3, 17),
                           'Fatal': 'Unknown variable "bar"',
                           'Stack': [{'code': 'x = MoreObject("345\\n")\n',
                                      'file': 'TopClass.py',
                                      'line': 23},
                                     {'code': 'foo = bar', 'file': 'MoreClass.py', 'line': 58}],
                           'User': 'ed'}])

    def test_interpolate(self):
        self.assertEqual(utils.interpolate('Hello, $who!', {'who': 'world'}), "Hello, world!")

    def test_interpolate_with_braces(self):
        self.assertEqual(utils.interpolate('Hello, ${who}!', {'who': 'world'}), "Hello, world!")

    def test_interpolate_escape(self):
        self.assertEqual(utils.interpolate('Hello, $$who!', {'who': 'world'}), "Hello, $who!")

    def test_interpolate_replaces_unset_variable_with_empty_string(self):
        self.assertEquals(utils.interpolate('Hello, $who!', {}), 'Hello, !')

    def test_interpolate_replaces_unset_variable_with_a_default_with_that_default(self):
        self.assertEquals(utils.interpolate('Hello, ${who:-someone}!', {}), 'Hello, someone!')

    def test_interpolate_replaces_variable_with_a_default_with_that_replacement(self):
        self.assertEquals(utils.interpolate('Hello, ${who:-someone}!', {'who': 'world'}), 'Hello, world!')

    def test_interpolate_returns_None_when_s_is_None(self):
        self.assertEqual(utils.interpolate(None, {'who': 'world'}), None)

    def test_defaultdict_returns_set_value(self):
        d = utils.defaultdict(lambda: 'defvalue')
        d['foo'] = 'bar'
        self.assertEqual(d['foo'], 'bar')

    def test_defaultdict_returns_set_value_even_when_given_another_default(self):
        d = utils.defaultdict(lambda: 'defvalue')
        d['foo'] = 'bar'
        self.assertEqual(d['foo:-baz'], 'bar')

    def test_defaultdict_returns_default_value(self):
        d = utils.defaultdict(lambda: 'defvalue')
        self.assertEqual(d['foo'], 'defvalue')

    def test_defaultdict_returns_default_specific_value(self):
        d = utils.defaultdict(lambda: 'defvalue')
        self.assertEqual(d['foo:-bar'], 'bar')
