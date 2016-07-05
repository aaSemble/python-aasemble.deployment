import requests


class AasembleClient(object):
    def __init__(self, key=None, url='https://aasemble.com/api/devel/'):
        self.url = url
        self.key = key
        self.clusters = ClusterManager(self)


class ClusterManager(object):
    def __init__(self, client):
        self.client = client

    def create(self):
        return Cluster(requests.post(self.client.url + 'clusters/').json()['self'])


class Cluster(object):
    def __init__(self, url):
        self.url = url

    def update(self, **kwargs):
        requests.patch(self.url, kwargs)
