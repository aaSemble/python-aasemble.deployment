from six.moves import configparser

from aasemble.deployment.cloud.gce import GCEDriver


def load_cloud_config(fpath):
    parser = configparser.SafeConfigParser()
    with open(fpath, 'r') as fp:
        parser.readfp(fp)
    driver_name = parser.get('connection', 'driver')
    if driver_name == 'gce':
        driver_class = GCEDriver
    mappings = {'images': {},
                'flavors': {}}

    if parser.has_section('images'):
        mappings['images'] = dict(parser.items('images'))

    if parser.has_section('flavors'):
        mappings['flavors'] = dict(parser.items('flavors'))

    return driver_class, driver_class.get_kwargs_from_cloud_config(parser), mappings
