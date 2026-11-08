"""A require with apiType grpc is saved as .proto, by the CLI and the conanfile helper."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml

from sanshainconan.cli import main
from sanshainconan.integration import Sanshain

PROTO = b'syntax = "proto3";\n'


class TestGrpcRequire(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.cwd = os.getcwd()
        os.chdir(self.folder)  # keep the .sanshain-cache inside the temp dir
        self.addCleanup(os.chdir, self.cwd)
        self.config_file = os.path.join(self.folder, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(
                {
                    "sanshainUrl": "http://localhost:3000",
                    "serviceName": "my-service",
                    "requires": [
                        {
                            "serviceName": "payments",
                            "apiType": "grpc",
                            "version": "1.0.0",
                            "outputDirectory": "gen",
                            "endpoints": [{"path": "pay.Payments/Charge", "method": "RPC"}],
                        }
                    ],
                },
                f,
            )
        self.client = mock.Mock()
        self.client.require.return_value = {
            "not_modified": False,
            "content": PROTO.decode(),
            "body": PROTO,
            "etag": None,
        }

    def assert_saved_as_proto(self):
        self.assertEqual(self.client.require.call_args.args[5], "grpc")
        with open(os.path.join(self.folder, "gen", "payments.proto"), "rb") as f:
            self.assertEqual(f.read(), PROTO)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "gen", "payments.yaml")))

    def test_the_cli_saves_it_as_proto(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=self.client):
                with mock.patch("sys.argv", ["sanshainconan", "--config", self.config_file, "require"]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()
        self.assert_saved_as_proto()

    def test_the_helper_saves_it_as_proto(self):
        conanfile = SimpleNamespace(export_sources_folder=self.folder, recipe_folder=self.folder, output=mock.Mock())
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(conanfile)
        sanshain.client = self.client
        sanshain.require()
        self.assert_saved_as_proto()


if __name__ == "__main__":
    unittest.main()
