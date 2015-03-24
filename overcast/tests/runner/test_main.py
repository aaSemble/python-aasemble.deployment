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
import mock
import os.path
import unittest
from StringIO import StringIO
import yaml

import overcast.runner

yaml_data = '''---
foo:
  - bar
  - baz:
      wibble: []
'''

class MainTests(unittest.TestCase):
    def test_load_yaml(self):
        with mock.patch('__builtin__.open') as m:
            m.return_value.__enter__.return_value = StringIO(yaml_data)
            self.assertEquals(overcast.runner.load_yaml(),
                              {'foo': ['bar', {'baz': {'wibble': []}}]})
            m.assert_called_once_with('.overcast.yaml', 'r')

    def test_find_weak_refs(self):
        example_file = os.path.join(os.path.dirname(__file__),
                                    'examplestack1.yaml')
        stack = overcast.runner.load_yaml(example_file)
        self.assertEquals(overcast.runner.find_weak_refs(stack),
                          (set(['trusty']),
                           set(['bootstrap']),
                           set(['default'])))

    def test_shell_step(self):
        details = {'cmd': 'true'}
        overcast.runner.shell_step(details, {})

    def test_shell_step_timeout(self):
        details = {'cmd': 'sleep 5',
                   'retry-for': '1s'}
        self.assertRaises(overcast.exceptions.CommandTimedOutException,
                          overcast.runner.shell_step, details, {})

    def test_shell_step_does_not_timeout(self):
        details = {'cmd': 'sleep 1',
                   'retry-for': '3s'}
        overcast.runner.shell_step(details, {})

    def test_shell_step_retries(self):
        details = {'cmd': 'sleep 1;exit 1',
                   'retry-for': '3s'}

        self.assertRaises(overcast.exceptions.CommandTimedOutException,
                          overcast.runner.shell_step, details, {})
