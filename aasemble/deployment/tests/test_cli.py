import unittest

import mock

import aasemble.deployment.cli


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

        load_cloud_config.return_value = (mock.MagicMock(name='cloud_driver_class'),
                                          mock.MagicMock(name='cloud_driver_kwargs'),
                                          mock.MagicMock(name='mappings'))

        cloud_driver = load_cloud_config.return_value[0]()
        aasemble.deployment.cli.apply(options)

        loader.load.assert_called_with(options.stack)

        if assume_empty:
            cloud_driver.detect_resources.assert_not_called()
            expected_resources = resources
        else:
            cloud_driver.detect_resources.assert_called_with()
            expected_resources = resources - cloud_driver.detect_resources.return_value

        cloud_driver.apply_resources.assert_called_with(expected_resources)

    def test_apply_no_assume_empty(self):
        self._test_apply(False)

    def test_apply_assume_empty(self):
        self._test_apply(True)

    @mock.patch('aasemble.deployment.cli.load_cloud_config')
    def test_detect(self, load_cloud_config):
        options = mock.MagicMock()
        load_cloud_config.return_value = (mock.MagicMock(name='cloud_driver_class'),
                                          mock.MagicMock(name='cloud_driver_kwargs'),
                                          mock.MagicMock(name='mappings'))
        cloud_driver = load_cloud_config.return_value[0]()

        aasemble.deployment.cli.detect(options)

        cloud_driver.detect_resources.assert_called_with()

    @mock.patch('aasemble.deployment.cli.detect')
    def test_main_calls_detect(self, detect):
        aasemble.deployment.cli.main(['detect', 'cloud.ini'])
        self.assertEqual(len(detect.call_args_list), 1)
        options = detect.call_args_list[0][0][0]
        self.assertEqual(options.cloud, 'cloud.ini')
