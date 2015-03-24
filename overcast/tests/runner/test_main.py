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

    def test_run_cmd_once_simple(self):
        overcast.runner.run_cmd_once(shell_cmd='bash',
                                     real_cmd='true',
                                     environment={},
                                     deadline=None)

    def test_run_cmd_once_fail(self):
        self.assertRaises(overcast.exceptions.CommandFailedException,
                          overcast.runner.run_cmd_once, shell_cmd='bash',
                                                        real_cmd='false',
                                                        environment={},
                                                        deadline=None)

    def test_run_cmd_once_with_deadline(self):
        deadline = 10
        with mock.patch('overcast.runner.time') as time_mock:
            time_mock.time.return_value = 9
            overcast.runner.run_cmd_once(shell_cmd='bash',
                                         real_cmd='true',
                                         environment={},
                                         deadline=deadline)
            time_mock.time.return_value = 11
            self.assertRaises(overcast.exceptions.CommandTimedOutException,
                              overcast.runner.run_cmd_once, shell_cmd='bash',
                                                            real_cmd='true',
                                                            environment={},
                                                            deadline=deadline)


    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step(self, run_cmd_once):
        details = {'cmd': 'true'}
        overcast.runner.shell_step(details, {})
        run_cmd_once.assert_called_once_with(mock.ANY, 'true', mock.ANY, None)

    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_failed_until_success(self, run_cmd_once):
        details = {'cmd': 'true',
                   'retry-if-fails': True}

        side_effects = [overcast.exceptions.CommandFailedException()]*100 + [True]
        run_cmd_once.side_effect = side_effects
        overcast.runner.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])

    @mock.patch('overcast.runner.time')
    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_failed_until_success_with_delay(self, run_cmd_once, time):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'retry-delay': '5s'}

        curtime = [0]
        def sleep(s, curtime=curtime):
            curtime[0] += s

        time.time.side_effect = lambda:curtime[0]
        time.sleep.side_effect = sleep

        side_effects = [overcast.exceptions.CommandFailedException()]*2 + [True]
        run_cmd_once.side_effect = side_effects
        overcast.runner.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])
        self.assertEquals(curtime[0], 10)

    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_timedout_until_success(self, run_cmd_once):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'timeout': '10s'}

        side_effects = [overcast.exceptions.CommandTimedOutException()]*10 + [True]
        run_cmd_once.side_effect = side_effects
        overcast.runner.shell_step(details, {})
        self.assertEquals(list(run_cmd_once.side_effect), [])


    @mock.patch('overcast.runner.time')
    @mock.patch('overcast.runner.run_cmd_once')
    def test_shell_step_retries_if_timedout_until_total_timeout(self,
                                                                run_cmd_once,
                                                                time):
        details = {'cmd': 'true',
                   'retry-if-fails': True,
                   'total-timeout': '10s'}

        time.time.return_value = 10

        side_effects = [overcast.exceptions.CommandTimedOutException()]*2
        def side_effect(*args, **kwargs):
            if len(side_effects) < 2:
                time.time.return_value = 100

            ret = side_effects.pop(0)
            if isinstance(ret, Exception):
                raise ret
            return ret

        run_cmd_once.side_effect = side_effect
        self.assertRaises(overcast.exceptions.CommandTimedOutException,
                          overcast.runner.shell_step, details, {})
        self.assertEquals(side_effects, [])
