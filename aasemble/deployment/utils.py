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
import logging
import re
import string

import yaml

from aasemble.deployment import exceptions

LOG = logging.getLogger(__name__)


class FakeResourceRecorder(object):  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass

    def record(self, *args, **kwargs):
        pass


def load_yaml(f='.aasemble.yaml'):
    with open(f, 'r') as fp:
        return list(yaml.safe_load_all(fp))


def parse_time(time_string):
    matches = re.match('^(\d+)(\w?)', time_string)
    if not matches:
        raise exceptions.InvalidTimeException()

    count, unit = matches.groups()
    count = int(count)
    multipliers = {'s': 1,
                   '': 1,
                   'm': 60,
                   'h': 60 * 60}
    try:
        multiplier = multipliers[unit]
    except KeyError:
        raise exceptions.InvalidTimeException()
    return count * multiplier


class TemplateWithDefaults(string.Template):
    idpattern = '[_a-z][_a-z0-9]*(:-[^}]*)?'


class defaultdict(dict):
    def __init__(self, default=None, *args):
        self.default = default
        super(defaultdict, self).__init__(*args)

    def __getitem__(self, key):
        if ':-' in key:
            key, default = key.split(':-', 1)
        else:
            default = self.default()

        return super(defaultdict, self).get(key, default)


def interpolate(s, d):
    if s is None:
        return None
    if d is None:
        d = {}
    return TemplateWithDefaults(s).substitute(defaultdict(str, d))
