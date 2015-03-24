#!/usr/bin/env python
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

import argparse
import ConfigParser
import select
import subprocess
import sys
import time
import yaml

from overcast import utils
from overcast import exceptions

def load_yaml(f='.overcast.yaml'):
    with open(f, 'r') as fp:
        return yaml.load(fp)

def find_weak_refs(stack):
    images = set()
    flavors = set()
    networks = set()
    for node_name, node in stack['nodes'].items():
        images.add(node['image'])
        flavors.add(node['flavor'])
        networks.update([n['network'] for n in node['nics']])

    dynamic_networks = set()
    for network_name, network in stack.get('networks', {}).items():
        dynamic_networks.add(network_name)

    return images, flavors, networks-dynamic_networks


def list_refs(args, stdout=sys.stdout):
    stack = load_yaml(args.stack)
    images, flavors, networks = find_weak_refs(stack)
    if args.tmpl:
        cfg = ConfigParser.SafeConfigParser()
        cfg.add_section('images')
        cfg.add_section('flavors')
        for image in images:
            cfg.set('images', image, '<missing value>')
        for flavor in flavors:
            cfg.set('flavors', flavor, '<missing value>')
        cfg.write(stdout)
    else:
        sys.stdout.write('Images:\n  ')

        if images:
            sys.stdout.write('  '.join(images))
        else:
            sys.stdout.write('None')

        sys.stdout.write('\n\nFlavors:\n  ')

        if flavors:
            sys.stdout.write('  '.join(flavors))
        else:
            sys.stdout.write('None')

        sys.stdout.write('\n')

def shell_step_cmd(details):
    if details.get('type', None) == 'remote':
         node = self.nodes[details['node']]
         return 'ssh -o StrictHostKeyChecking=no ubuntu@%s bash' % (node)
    else:
         return 'bash'
 
def run_cmd_once(shell_cmd, real_cmd, environment, deadline):
    proc = subprocess.Popen(shell_cmd,
                            env=environment,
                            shell=True,
                            stdin=subprocess.PIPE)
    stdin = real_cmd + '\n'
    while True:
        if stdin:
            _, rfds, xfds = select.select([], [proc.stdin], [proc.stdin], 1)
            if rfds:
                proc.stdin.write(stdin[0])
                stdin = stdin[1:]
                if not stdin:
                    proc.stdin.close()
            if xfds:
                if proc.stdin.feof():
                    stdin = ''

        if proc.poll() is not None:
            if proc.returncode != 0:
                if not deadline:
                    raise exceptions.CommandFailedException(stdin)
            else:
                return True

        if deadline and time.time() > deadline:
            raise exceptions.CommandTimedOutException(stdin)


def shell_step(details, environment):
    cmd = shell_step_cmd(details)
   
    if details.get('retry-for', False):
        deadline = time.time() + utils.parse_time(details['retry-for'])
    else:
        deadline = None

    while True: 
        if run_cmd_once(cmd, details['cmd'], environment, deadline):
            break


def deploy(args, stdout):
    cfg = load_yaml(args.cfg)
    for step in build_info[name]:
        step_type = step.keys()[0]
        details = step[step_type]
        func = locals()['%s_step' % step_type]
        func(details)


def main(argv=sys.argv[1:], stdout=sys.stdout):
    parser = argparse.ArgumentParser(description='Run deployment')

    subparsers = parser.add_subparsers(help='Subcommand help')
    list_refs_parser = subparsers.add_parser('list-refs',
                                             help='List symbolic resources')
    list_refs_parser.set_defaults(func=list_refs)
    list_refs_parser.add_argument('--tmpl', action='store_true',
                                  help='Output template ini file')
    list_refs_parser.add_argument('stack', help='YAML file describing stack')

    deploy_parser = subparsers.add_parser('deploy', help='Perform deployment')
    deploy_parser.set_defaults(func=deploy)
    deploy_parser.add_argument('--cfg', default='.overcast.yaml',
                               help='Deployment config file')

    args = parser.parse_args(argv)

    if args.func:
        args.func(args)

if __name__ == '__main__':
    main()
