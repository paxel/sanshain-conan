"""The require ETag is kept per output directory, and a lost output file is fetched again."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from sanshainconan.cache import SanshainCache
from sanshainconan.cli import main


class TestKeys(unittest.TestCase):
    def test_the_output_directory_is_part_of_the_key(self):
        self.assertEqual(SanshainCache.require_key("u", "1.0.0", "GET", "/x"), "u|1.0.0|GET|/x")
        self.assertEqual(
            SanshainCache.require_key("u", "1.0.0", "GET", "/x", "openapi", "gen/a"),
            "u|1.0.0|GET|/x|format=openapi|out=gen/a",
        )
        self.assertEqual(SanshainCache.require_bundle_key("u", "1.0.0", None, "gen/b"), "u|1.0.0|bundle|out=gen/b")

    def test_two_spellings_of_one_directory_share_a_key_two_directories_do_not(self):
        def key(directory):
            return SanshainCache.require_key("u", "1.0.0", "GET", "/x", None, directory)

        self.assertEqual(key("./gen//a/"), key("gen/a"))
        self.assertEqual(key("gen\\a"), key("gen/a"))
        self.assertNotEqual(key("gen/a"), key("gen/b"))


class TestCliRequireCache(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.cwd = os.getcwd()
        os.chdir(self.folder)  # keep the .sanshain-cache inside the temp dir
        self.addCleanup(os.chdir, self.cwd)
        self.config_file = os.path.join(self.folder, "sanshain.yaml")

    def write(self, *directories):
        entries = [
            {
                "serviceName": "users",
                "version": "1.0.0",
                "outputDirectory": directory,
                "endpoints": [{"method": "GET", "path": "/users"}],
            }
            for directory in directories
        ]
        with open(self.config_file, "w") as f:
            yaml.dump({"sanshainUrl": "http://localhost:3000", "serviceName": "svc", "requires": entries}, f)

    def run_cli(self):
        # A 304 whenever an ETag is sent, as the service answers an unchanged spec.
        def require(*args, **kwargs):
            if args[6]:
                return {"not_modified": True, "content": None, "etag": None}
            return {"not_modified": False, "content": "paths: {}", "body": b"paths: {}", "etag": '"e1"'}

        client = mock.Mock()
        client.require.side_effect = require
        out = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
                with mock.patch("sys.argv", ["sanshainconan", "--config", self.config_file, "require"]):
                    with contextlib.redirect_stdout(out):
                        main()
        return client, out.getvalue()

    def read(self, *parts):
        with open(os.path.join(self.folder, *parts), "rb") as f:
            return f.read()

    def test_the_same_endpoint_required_into_two_directories_is_written_to_both(self):
        self.write("gen/a", "gen/b")
        self.run_cli()
        self.assertEqual(self.read("gen", "a", "users.yaml"), b"paths: {}")
        self.assertEqual(self.read("gen", "b", "users.yaml"), b"paths: {}")
        with open(os.path.join(self.folder, ".sanshain-cache", "state.json")) as f:
            self.assertEqual(
                list(json.load(f)["requires"]), ["users|1.0.0|GET|/users|out=gen/a", "users|1.0.0|GET|/users|out=gen/b"]
            )

    def test_a_deleted_output_file_is_fetched_again(self):
        self.write("gen")
        self.run_cli()
        os.remove(os.path.join(self.folder, "gen", "users.yaml"))
        client, _ = self.run_cli()
        self.assertIsNone(client.require.call_args.args[6])
        self.assertEqual(self.read("gen", "users.yaml"), b"paths: {}")

    def test_a_present_output_file_still_sends_the_stored_etag(self):
        self.write("gen")
        self.run_cli()
        client, out = self.run_cli()
        self.assertEqual(client.require.call_args.args[6], '"e1"')
        self.assertIn("unchanged (304)", out)


if __name__ == "__main__":
    unittest.main()
