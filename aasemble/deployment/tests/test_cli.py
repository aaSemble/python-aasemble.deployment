import unittest

import aasemble.deployment.cli

class CliTestCase(unittest.TestCase):
    def test_no_args(self):
        with self.assertRaises(SystemExit) as exit:
            aasemble.deployment.cli.main(args=[])
        self.assertEqual(exit.exception.code, 2)
