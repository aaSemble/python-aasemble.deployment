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
import unittest

from overcast import utils
from overcast import exceptions

class UtilsTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEquals(utils.parse_time('10s'), 10)
        self.assertEquals(utils.parse_time('10'), 10)
        self.assertEquals(utils.parse_time('10m'), 600)
        self.assertEquals(utils.parse_time('1h'), 3600)
        self.assertEquals(utils.parse_time('2h'), 7200)
        self.assertEquals(utils.parse_time('0'), 0)

        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '2x')
        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '-10')
        self.assertRaises(exceptions.InvalidTimeException, utils.parse_time, '-10m')
