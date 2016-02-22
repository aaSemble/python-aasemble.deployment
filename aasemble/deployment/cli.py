import argparse
import logging
import sys

from multiprocessing.pool import ThreadPool

from aasemble.deployment import loader
from aasemble.deployment.cloudconfigparser import load_cloud_config
from aasemble.deployment.runner import FakeResourceRecorder


def deploy(options):
    resources = loader.load(options.stack)
    cloud_driver_class, cloud_driver_kwargs, mappings = load_cloud_config(options.cloud)
    resource_recorder = FakeResourceRecorder()
    pool = ThreadPool()
    cloud_driver = cloud_driver_class(record_resource=resource_recorder.record,
                                      mappings=mappings,
                                      pool=pool,
                                      **cloud_driver_kwargs)

    if not options.assume_empty:
        current_resources = cloud_driver.detect_resources()
        resources = resources - current_resources

    cloud_driver.apply_resources(resources)


def detect(options):
    cloud_driver_class, cloud_driver_kwargs, mappings = load_cloud_config(options.cloud)
    resource_recorder = FakeResourceRecorder()
    cloud_driver = cloud_driver_class(record_resource=resource_recorder.record,
                                      mappings=mappings,
                                      **cloud_driver_kwargs)
    cloud_driver.detect_resources()


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s %(message)s')

    subparsers = parser.add_subparsers(help='Subcommand help')
    deploy_parser = subparsers.add_parser('apply', help='Apply (launch/update) stack')
    deploy_parser.set_defaults(func=deploy)
    deploy_parser.add_argument('--assume-empty', action='store_true', help='Ignore current resources')
    deploy_parser.add_argument('stack', help='Stack description (yaml format)')
    deploy_parser.add_argument('cloud', help='Cloud config')

    detect_parser = subparsers.add_parser('detect', help='Detect current resources')
    detect_parser.set_defaults(func=detect)
    detect_parser.add_argument('cloud', help='Cloud config')

    options = parser.parse_args(args)
    options.func(options)


if __name__ == '__main__':
    main()
