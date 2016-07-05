import unittest

import mock

import aasemble.client
import aasemble.deployment.cli
import aasemble.deployment.cloud.base
import aasemble.deployment.cloud.models as cloud_models


class CliTestCase(unittest.TestCase):
    def test_no_args(self):
        with self.assertRaises(SystemExit) as exit:
            aasemble.deployment.cli.main(args=[])
        self.assertEqual(exit.exception.code, 2)

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    @mock.patch('aasemble.deployment.cli.loader')
    @mock.patch('aasemble.deployment.cli.handle_cluster_opts')
    @mock.patch('aasemble.client')
    def _test_apply(self, assume_empty, client, handle_cluster_opts, loader, load_cloud_config):
        client.AasembleClient.side_effect = Exception('should not invoke the aaSemble client')

        options = mock.MagicMock()
        options.assume_empty = assume_empty
        options.new_cluster = False
        options.cluster = False
        options.threads = 1

        resources = loader.load.return_value

        with mock.patch.multiple('aasemble.deployment.cloud.base.CloudDriver',
                                 detect_resources=mock.DEFAULT,
                                 apply_resources=mock.DEFAULT) as values:
            detect_resources = values['detect_resources']
            apply_resources = values['apply_resources']

            load_cloud_config.return_value = (aasemble.deployment.cloud.base.CloudDriver, {}, {})

            aasemble.deployment.cli.apply(options)

        loader.load.assert_called_with(options.stack, {})

        if assume_empty:
            detect_resources.assert_not_called()
            expected_resources = resources
        else:
            detect_resources.assert_called_with()
            expected_resources = resources - detect_resources.return_value

        apply_resources.assert_called_with(expected_resources)
        handle_cluster_opts.assert_called_with(options, {})

    def test_apply_no_assume_empty(self):
        self._test_apply(False)

    def test_apply_assume_empty(self):
        self._test_apply(True)

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    def test_detect(self, load_cloud_config):
        options = mock.MagicMock()
        options.threads = 1
        with mock.patch('aasemble.deployment.cloud.base.CloudDriver.detect_resources') as detect_resources:
            load_cloud_config.return_value = (aasemble.deployment.cloud.base.CloudDriver, {}, {})

            aasemble.deployment.cli.detect(options)

        detect_resources.assert_called_with()

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    @mock.patch('aasemble.deployment.cli.format_collection')
    def test_clean(self, format_collection, load_cloud_config):
        options = mock.MagicMock()
        options.threads = 1
        with mock.patch.multiple('aasemble.deployment.cloud.base.CloudDriver',
                                 clean_resources=mock.DEFAULT,
                                 detect_resources=mock.DEFAULT) as values:
            values['detect_resources'].return_value = mock.sentinel.resources
            load_cloud_config.return_value = (aasemble.deployment.cloud.base.CloudDriver, {}, {})

            aasemble.deployment.cli.clean(options)

        values['detect_resources'].assert_called_with()
        values['clean_resources'].assert_called_with(mock.sentinel.resources)

    @mock.patch('aasemble.deployment.cli.detect')
    def test_main_calls_detect(self, detect):
        aasemble.deployment.cli.main(['detect', 'cloud.ini'])
        self.assertEqual(len(detect.call_args_list), 1)
        options = detect.call_args_list[0][0][0]
        self.assertEqual(options.cloud, 'cloud.ini')

    def test_extract_substitutions(self):
        extract_substitutions = aasemble.deployment.cli.extract_substitutions
        self.assertEqual(extract_substitutions([]), {})
        self.assertEqual(extract_substitutions(['foo=bar']), {'foo': 'bar'})
        self.assertEqual(extract_substitutions(['foo=bar=baz']), {'foo': 'bar=baz'})
        self.assertEqual(extract_substitutions(['foo=bar', 'bar=baz']), {'foo': 'bar', 'bar': 'baz'})
        self.assertEqual(extract_substitutions(['foo=bar', 'foo=baz']), {'foo': 'baz'})

    def test_format_collection(self):
        collection = cloud_models.Collection()

        class GCENode(object):
            def __init__(self, ip):
                self.public_ips = [ip]

        collection.nodes.add(cloud_models.Node(name='testnode', flavor='n1-standard-1',
                                               image='someimage', networks=[], disk=10,
                                               private=GCENode('10.0.0.1')))
        self.assertEquals(aasemble.deployment.cli.format_collection(collection), "Nodes:\n  testnode: ['10.0.0.1']\n")

    def test_handle_cluster_opts_no_args(self):
        options = mock.MagicMock()
        options.new_cluster = None
        options.cluster = None
        substitutions = {}
        cluster = aasemble.deployment.cli.handle_cluster_opts(options, substitutions)
        self.assertEqual(cluster, None)
        self.assertEqual(substitutions, {})

    @mock.patch('aasemble.deployment.cli.client')
    def test_handle_cluster_opts_new_cluster(self, client):
        url = 'https://example.com/api/v4/clusters/8c45f2a1-02ef-4225-9e27-d5f796431b84/'
        client.AasembleClient().clusters.create.return_value = aasemble.client.Cluster(url=url)

        options = mock.MagicMock()
        options.new_cluster = True
        options.cluster = None
        substitutions = {}
        cluster = aasemble.deployment.cli.handle_cluster_opts(options, substitutions)
        self.assertEqual(cluster, url)
        self.assertEqual(substitutions, {'cluster': url})

    def test_handle_cluster_opts_cluster_url(self):
        url = 'https://example.com/api/v4/clusters/8c45f2a1-02ef-4225-9e27-d5f796431b83/'
        options = mock.MagicMock()
        options.new_cluster = False
        options.cluster = url
        substitutions = {}

        cluster = aasemble.deployment.cli.handle_cluster_opts(options, substitutions)

        self.assertEqual(cluster, url)
        self.assertEqual(substitutions, {'cluster': url})
