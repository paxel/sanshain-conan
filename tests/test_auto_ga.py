"""autoGa: a provide is GA whenever the build declares a stream, unless the ga flag or SANSHAIN_GA decides."""

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
from sanshainconan.client import resolve_stability, stream_declared
from sanshainconan.config import ConfigError, SanshainConfig, find_unknown_fields
from sanshainconan.integration import Sanshain


def make_response(status_code=202, json_data=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = ""
    resp.headers = {}
    resp.json.return_value = json_data or {"version": "1.0.0", "stability": "snapshot", "changes": {}}
    return resp


# (autoGa, CLI stream flags, --ga, SANSHAIN_GA, expected stability). None is "not set".
# The --ga flag only says ga (it is presence-only), so the spec's `--ga=false` row has no CLI form.
TABLE = [
    (True, ["--trunk"], False, None, "ga"),
    (True, ["--tag", "release-1"], False, None, "ga"),
    (True, [], False, None, "snapshot"),
    (True, ["--trunk"], False, "false", "snapshot"),
    (False, ["--trunk"], False, None, "snapshot"),
    (None, [], False, "true", "ga"),
    (True, [], True, "false", "ga"),
]


class Project(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(os.path.join(self.dir, "api.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 1.0.0\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write_config(self, auto_ga, **extra):
        config = {"sanshainUrl": "http://localhost:8080", "serviceName": "svc", "provide": {"file": "api.yaml"}}
        if auto_ga is not None:
            config["autoGa"] = auto_ga
        config.update(extra)
        self.config_file = os.path.join(self.dir, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(config, f)


class TestResolveStability(unittest.TestCase):
    def test_the_table(self):
        for auto_ga, stream, ga_flag, env_ga, expected in TABLE:
            env = {} if env_ga is None else {"SANSHAIN_GA": env_ga}
            with self.subTest(auto_ga=auto_ga, stream=stream, ga=ga_flag, env=env_ga):
                with mock.patch.dict(os.environ, env, clear=True):
                    declared = stream_declared("--trunk" in stream, stream[1] if "--tag" in stream else None)
                    self.assertEqual(resolve_stability(ga_flag, auto_ga is True, declared), expected)

    def test_blank_sanshain_ga_is_unset(self):
        for value in ("", "  "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"SANSHAIN_GA": value}, clear=True):
                self.assertEqual(resolve_stability(False, True, True), "ga")

    def test_any_other_sanshain_ga_value_is_set_and_off(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_GA": "yes"}, clear=True):
            self.assertEqual(resolve_stability(False, True, True), "snapshot")


class TestStreamDeclared(unittest.TestCase):
    def test_flags_and_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(stream_declared())
            self.assertFalse(stream_declared(False, "  "))
            self.assertTrue(stream_declared(True))
            self.assertTrue(stream_declared(False, "release-1"))
        with mock.patch.dict(os.environ, {"SANSHAIN_TRUNK": "true"}, clear=True):
            self.assertTrue(stream_declared())
        with mock.patch.dict(os.environ, {"SANSHAIN_TAG": "release-1"}, clear=True):
            self.assertTrue(stream_declared())

    def test_trunk_and_tag_together_still_declare_a_stream(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_TAG": "release-1"}, clear=True):
            self.assertTrue(stream_declared(True))


class TestCliAutoGa(Project):
    def run_provide(self, *extra, env=None):
        argv = ["sanshain-conan", "--config", self.config_file, *extra, "provide"]
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=True):
            with mock.patch("requests.post", return_value=make_response()) as mock_post:
                with mock.patch("sys.argv", argv), contextlib.redirect_stdout(out):
                    main()
        self.mock_post = mock_post
        return out.getvalue()

    def test_the_table_on_the_wire(self):
        for auto_ga, stream, ga_flag, env_ga, expected in TABLE:
            with self.subTest(auto_ga=auto_ga, stream=stream, ga=ga_flag, env=env_ga):
                self.write_config(auto_ga)
                flags = (["--ga"] if ga_flag else []) + stream
                env = {} if env_ga is None else {"SANSHAIN_GA": env_ga}
                out = self.run_provide(*flags, env=env)
                self.assertEqual(self.mock_post.call_args[1]["json"]["stability"], expected)
                self.assertIn(f"(stability: {expected})", out)

    def test_the_stream_from_the_environment_counts(self):
        self.write_config(True)
        for env in ({"SANSHAIN_TRUNK": "true"}, {"SANSHAIN_TAG": "release-1"}):
            with self.subTest(env=env):
                self.run_provide(env=env)
                self.assertEqual(self.mock_post.call_args[1]["json"]["stability"], "ga")

    def test_trunk_and_tag_together_make_ga_and_send_neither(self):
        self.write_config(True)
        self.run_provide("--trunk", "--tag", "release-1")
        payload = self.mock_post.call_args[1]["json"]
        self.assertEqual(payload["stability"], "ga")
        self.assertNotIn("trunk", payload)
        self.assertNotIn("tag", payload)

    def test_retire_with_auto_ga_on_trunk_sends_no_stability(self):
        self.write_config(True, provide={"apiType": "asyncapi", "retired": True})
        self.run_provide("--trunk")
        self.mock_post.assert_called_once()
        self.assertEqual(self.mock_post.call_args[0][0], "http://localhost:8080/provide/asyncapi")
        self.assertEqual(self.mock_post.call_args[1]["json"], {"producername": "svc", "retired": True})


class TestHelperAutoGa(Project):
    def helper(self, env):
        conanfile = SimpleNamespace(
            export_sources_folder=self.dir, recipe_folder=self.dir, source_folder=self.dir, output=mock.Mock()
        )
        with mock.patch.dict(os.environ, env, clear=True):
            return Sanshain(conanfile)

    def test_the_environment_rows(self):
        rows = [
            (True, {"SANSHAIN_TRUNK": "true"}, "ga"),
            (True, {"SANSHAIN_TAG": "release-1"}, "ga"),
            (True, {}, "snapshot"),
            (True, {"SANSHAIN_TRUNK": "true", "SANSHAIN_GA": "false"}, "snapshot"),
            (False, {"SANSHAIN_TRUNK": "true"}, "snapshot"),
            (None, {"SANSHAIN_GA": "true"}, "ga"),
        ]
        for auto_ga, env, expected in rows:
            with self.subTest(auto_ga=auto_ga, env=env):
                self.write_config(auto_ga)
                self.assertEqual(self.helper(env).stability, expected)

    def test_retire_with_auto_ga_on_trunk_sends_no_stability(self):
        self.write_config(True, provide={"apiType": "openapi", "retired": True})
        sanshain = self.helper({"SANSHAIN_TRUNK": "true"})
        self.assertEqual(sanshain.stability, "ga")
        with mock.patch("requests.post", return_value=make_response()) as mock_post:
            sanshain.provide()
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args[1]["json"], {"producername": "svc", "retired": True})


class TestAutoGaConfig(unittest.TestCase):
    def test_is_a_known_field(self):
        self.assertEqual(find_unknown_fields({"sanshainUrl": "x", "autoGa": True}), [])

    def test_defaults_to_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(SanshainConfig({"sanshainUrl": "x"}).auto_ga)
            self.assertFalse(SanshainConfig({"sanshainUrl": "x", "autoGa": None}).auto_ga)
            self.assertTrue(SanshainConfig({"sanshainUrl": "x", "autoGa": True}).auto_ga)

    def test_a_value_other_than_true_or_false_is_an_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                SanshainConfig({"sanshainUrl": "x", "autoGa": "yes"})
        self.assertEqual(str(ctx.exception), "autoGa must be true or false, not 'yes'")


if __name__ == "__main__":
    unittest.main()
