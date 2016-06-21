import unittest

import mock

import aasemble.client


class AasembleClientTests(unittest.TestCase):
    example_cluster = {'self': 'https://aasemble.com/api/devel/clusters/some-uuid/',
                       'nodes': 'https://aasemble.com/api/devel/clusters/some-uuid/nodes/',
                       'json': None}

    @mock.patch('aasemble.client.requests')
    def test_create_cluster(self, requests):
        requests.post.return_value.json.return_value = self.example_cluster

        client = aasemble.client.AasembleClient()
        cluster = client.clusters.create()
        self.assertEqual(type(cluster), aasemble.client.Cluster)
        self.assertEquals(cluster.url, 'https://aasemble.com/api/devel/clusters/some-uuid/')

    @mock.patch('aasemble.client.requests')
    def test_patch_cluster(self, requests):
        requests.post.return_value.json.return_value = self.example_cluster

        client = aasemble.client.AasembleClient()
        cluster = client.clusters.create()
        cluster.update(json='{"foo": "bar"}')

        requests.patch.assert_called_with('https://aasemble.com/api/devel/clusters/some-uuid/', {'json': '{"foo": "bar"}'})
