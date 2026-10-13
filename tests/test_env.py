"""SANSHAIN_* switches and SANSHAIN_URL, read the same way by every Sanshain client."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml

from sanshainconan.cli import main, resolve_stability
from sanshainconan.client import resolve_stream
from sanshainconan.config import SanshainConfig, env_flag
from sanshainconan.integration import Sanshain

ON = ["true", "1", "TRUE", " true ", "True", " 1\n"]
OFF = ["yes", "false", "0", "", "on", "truee"]


class TestEnvFlag(unittest.TestCase):
    def test_true_and_1_are_on_trimmed_and_case_insensitive(self):
        for value in ON:
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_X": value}, clear=True):
                self.assertTrue(env_flag("SANSHAIN_X"))

    def test_anything_else_is_off(self):
        for value in OFF:
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_X": value}, clear=True):
                self.assertFalse(env_flag("SANSHAIN_X"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(env_flag("SANSHAIN_X"))

    def test_ga_switch(self):
        for value in ("1", "TRUE", " true "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_GA": value}, clear=True):
                self.assertEqual(resolve_stability(), "ga")
        with mock.patch.dict(os.environ, {"SANSHAIN_GA": "yes"}, clear=True):
            self.assertEqual(resolve_stability(), "snapshot")

    def test_trunk_switch(self):
        for value in ("1", "TRUE", " true "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_TRUNK": value}, clear=True):
                self.assertEqual(resolve_stream(), (True, None))
        with mock.patch.dict(os.environ, {"SANSHAIN_TRUNK": "yes"}, clear=True):
            self.assertEqual(resolve_stream(), (False, None))

    def test_helper_ga_switch(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        with open(os.path.join(folder, "sanshain.yaml"), "w") as f:
            yaml.dump({"sanshainUrl": "http://localhost:8080", "serviceName": "svc"}, f)
        conanfile = SimpleNamespace(
            export_sources_folder=folder, recipe_folder=folder, base_folder=folder, output=mock.Mock()
        )
        for value, expected in (("1", "ga"), (" TRUE ", "ga"), ("yes", "snapshot")):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_GA": value}, clear=True):
                self.assertEqual(Sanshain(conanfile).stability, expected)


class TestBestEffortSwitch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.config_file = os.path.join(self.folder, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(
                {"sanshainUrl": "http://localhost:8080", "serviceName": "svc", "provide": {"file": "missing.yaml"}}, f
            )

    def tearDown(self):
        shutil.rmtree(self.folder)

    def _run(self, value):
        argv = ["sanshain-conan", "--config", self.config_file, "provide"]
        with mock.patch.dict(os.environ, {"SANSHAIN_BEST_EFFORT": value}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=mock.Mock()):
                with mock.patch("sys.argv", argv):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()

    def test_on_values_continue(self):
        for value in ("1", "TRUE", " true "):
            with self.subTest(value=value):
                self._run(value)  # no SystemExit

    def test_yes_is_off(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run("yes")
        self.assertEqual(ctx.exception.code, 1)


class TestSanshainUrl(unittest.TestCase):
    def test_env_beats_yaml(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_URL": "https://env.example"}, clear=True):
            config = SanshainConfig({"sanshainUrl": "https://yaml.example"})
        self.assertEqual(config.sanshain_url, "https://env.example")

    def test_yaml_is_the_fallback(self):
        for env in ({}, {"SANSHAIN_URL": "  "}):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True):
                config = SanshainConfig({"sanshainUrl": "https://yaml.example"})
            self.assertEqual(config.sanshain_url, "https://yaml.example")

    def test_env_alone_is_enough(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_URL": " https://env.example "}, clear=True):
            config = SanshainConfig({"serviceName": "svc"})
        self.assertEqual(config.sanshain_url, "https://env.example")

    def test_cli_client_gets_the_env_url(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        config_file = os.path.join(folder, "sanshain.yaml")
        with open(config_file, "w") as f:
            yaml.dump({"sanshainUrl": "https://yaml.example", "serviceName": "svc"}, f)
        argv = ["sanshain-conan", "--config", config_file, "provide"]
        with mock.patch.dict(os.environ, {"SANSHAIN_URL": "https://env.example"}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient") as client_cls:
                with mock.patch("sys.argv", argv):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()
        self.assertEqual(client_cls.call_args[0][0], "https://env.example")


if __name__ == "__main__":
    unittest.main()
