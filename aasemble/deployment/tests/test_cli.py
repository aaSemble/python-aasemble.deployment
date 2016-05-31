import unittest

import mock

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
    def _test_apply(self, assume_empty, loader, load_cloud_config):
        options = mock.MagicMock()
        options.assume_empty = assume_empty

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

    def test_apply_no_assume_empty(self):
        self._test_apply(False)

    def test_apply_assume_empty(self):
        self._test_apply(True)

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    def test_detect(self, load_cloud_config):
        options = mock.MagicMock()
        with mock.patch('aasemble.deployment.cloud.base.CloudDriver.detect_resources') as detect_resources:
            load_cloud_config.return_value = (aasemble.deployment.cloud.base.CloudDriver, {}, {})

            aasemble.deployment.cli.detect(options)

        detect_resources.assert_called_with()

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    @mock.patch('aasemble.deployment.cli.format_collection')
    def test_clean(self, format_collection, load_cloud_config):
        options = mock.MagicMock()
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
