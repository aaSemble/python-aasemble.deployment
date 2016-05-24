class CloudDriver(object):
    def __init__(self, record_resource, namespace=None, mappings=None, pool=None):
        self.record_resource = record_resource
        self.mappings = mappings or {}
        self.pool = pool
        self.secgroups = {}
        self.namespace = namespace

    def apply_mappings(self, obj_type, name):
        return self.mappings.get(obj_type, {}).get(name, name)

    def detect_resources(self):
        raise NotImplementedError()

    def apply_resources(self):
        raise NotImplementedError()

    def clean_resources(self):
        raise NotImplementedError()
