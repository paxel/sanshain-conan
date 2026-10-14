"""Relative paths in sanshain.yaml resolve against the folder holding it, never the working directory."""

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


def write_config(folder, data):
    path = os.path.join(folder, "sanshain.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def fake_conanfile(folder):
    return SimpleNamespace(
        export_sources_folder=folder,
        recipe_folder=folder,
        base_folder=folder,
        output=mock.Mock(),
    )


class PathsTestCase(unittest.TestCase):
    def setUp(self):
        # Three unrelated folders: the config lives in one, the recipe in
        # another and the process runs in a third.
        self.config_dir = tempfile.mkdtemp()
        self.recipe_dir = tempfile.mkdtemp()
        self.work_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.work_dir)
        with open(os.path.join(self.config_dir, "api.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 1.2.0\n")
        self.config_file = write_config(
            self.config_dir,
            {
                "sanshainUrl": "http://localhost:8080",
                "serviceName": "my-service",
                "provide": {"file": "api.yaml"},
                "requires": [
                    {
                        "serviceName": "other-service",
                        "version": "1.2.0",
                        "outputDirectory": "gen",
                        "endpoints": [{"path": "/foo", "method": "GET"}],
                    }
                ],
            },
        )

    def tearDown(self):
        os.chdir(self.cwd)
        for d in (self.config_dir, self.recipe_dir, self.work_dir):
            shutil.rmtree(d)

    def client(self):
        client = mock.Mock()
        client.provide.return_value = {"version": "1.2.0", "stability": "snapshot", "changes": {}}
        client.require.return_value = {
            "not_modified": False,
            "content": "openapi: 3.0.0",
            "body": b"openapi: 3.0.0",
            "etag": None,
        }
        return client


class TestCliPaths(PathsTestCase):
    def _run(self, command, client):
        argv = ["sanshain-conan", "--config", self.config_file, command]
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
                with mock.patch("sys.argv", argv):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()

    def test_provide_reads_the_spec_next_to_the_config(self):
        client = self.client()
        self._run("provide", client)
        args, _ = client.provide.call_args
        self.assertIn("version: 1.2.0", args[1])

    def test_require_writes_next_to_the_config(self):
        self._run("require", self.client())
        self.assertTrue(os.path.exists(os.path.join(self.config_dir, "gen", "other-service.yaml")))
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, "gen")))

    def test_absolute_paths_stay_absolute(self):
        elsewhere = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, elsewhere)
        with open(os.path.join(elsewhere, "abs.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 9.9.9\n")
        out_dir = os.path.join(elsewhere, "out")
        write_config(
            self.config_dir,
            {
                "sanshainUrl": "http://localhost:8080",
                "serviceName": "my-service",
                "provide": {"file": os.path.join(elsewhere, "abs.yaml")},
                "requires": [
                    {
                        "serviceName": "other-service",
                        "version": "1.2.0",
                        "outputDirectory": out_dir,
                        "endpoints": [{"path": "/foo", "method": "GET"}],
                    }
                ],
            },
        )
        client = self.client()
        self._run("provide", client)
        self._run("require", client)
        self.assertIn("version: 9.9.9", client.provide.call_args[0][1])
        self.assertTrue(os.path.exists(os.path.join(out_dir, "other-service.yaml")))


class TestHelperPaths(PathsTestCase):
    def _helper(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(fake_conanfile(self.recipe_dir), config_path=self.config_file)
        sanshain.client = self.client()
        return sanshain

    def test_provide_reads_the_spec_next_to_the_config(self):
        sanshain = self._helper()
        sanshain.provide()
        args, _ = sanshain.client.provide.call_args
        self.assertIn("version: 1.2.0", args[1])

    def test_require_writes_next_to_the_config(self):
        sanshain = self._helper()
        sanshain.require()
        self.assertTrue(os.path.exists(os.path.join(self.config_dir, "gen", "other-service.yaml")))
        self.assertFalse(os.path.exists(os.path.join(self.recipe_dir, "gen")))
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, "gen")))

    def test_default_config_is_found_in_the_project_root(self):
        # Without config_path the helper loads <export_sources_folder>/sanshain.yaml
        # and resolves against that same folder.
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(fake_conanfile(self.config_dir))
        self.assertEqual(sanshain.base_path, os.path.abspath(self.config_dir))


if __name__ == "__main__":
    unittest.main()
