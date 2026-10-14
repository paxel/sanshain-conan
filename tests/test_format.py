"""`format: openapi` on an AsyncAPI requires entry."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import requests
import yaml

from sanshainconan.cache import SanshainCache
from sanshainconan.cli import main
from sanshainconan.client import SanshainClient, SanshainError
from sanshainconan.config import ConfigError, SanshainConfig, find_unknown_fields
from sanshainconan.integration import Sanshain

OPENAPI = "openapi: 3.0.3\ninfo:\n  title: events\n  version: 1.0.0\npaths: {}\n"
ASYNCAPI = "asyncapi: 2.6.0\ninfo:\n  title: events\n  version: 1.0.0\nchannels: {}\n"
ONE = [{"method": "PUB", "path": "user/signup"}]
TWO = ONE + [{"method": "PUB", "path": "order/placed"}]


def make_response(status_code=200, json_data=None, text="", headers=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode("utf-8")
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


def entry(**extra):
    return {"serviceName": "events", "version": "1.0.0", "outputDirectory": "gen", "endpoints": ONE, **extra}


class TestFormatConfig(unittest.TestCase):
    def config(self, **extra):
        return SanshainConfig({"sanshainUrl": "http://x", "serviceName": "svc", "requires": [entry(**extra)]})

    def test_asyncapi_with_openapi_is_accepted(self):
        self.assertEqual(self.config(apiType="asyncapi", format="openapi").requires[0]["format"], "openapi")

    def test_format_is_a_known_field(self):
        data = {"sanshainUrl": "x", "requires": [entry(apiType="asyncapi", format="openapi")]}
        self.assertEqual(find_unknown_fields(data), [])

    def test_other_api_types_are_rejected(self):
        for api_type in (None, "openapi", "proto"):
            with self.subTest(api_type=api_type):
                extra = {"format": "openapi"}
                if api_type:
                    extra["apiType"] = api_type
                with self.assertRaises(ConfigError) as ctx:
                    self.config(**extra)
                msg = str(ctx.exception)
                self.assertIn("requires[0] (events)", msg)
                self.assertIn("apiType: asyncapi with format: openapi", msg)

    def test_unknown_values_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, r"requires\[0\] \(events\): format 'html'"):
            self.config(apiType="asyncapi", format="html")


class TestFormatOnTheWire(unittest.TestCase):
    @mock.patch("requests.get")
    def test_single_require_sends_the_query_parameter(self, mock_get):
        mock_get.return_value = make_response(200, text=OPENAPI)
        res = SanshainClient("http://x").require(
            "c", "events", "1.0.0", "user/signup", "PUB", "asyncapi", fmt="openapi"
        )
        self.assertTrue(mock_get.call_args[0][0].endswith("/require/asyncapi"))
        self.assertEqual(mock_get.call_args[1]["params"]["format"], "openapi")
        self.assertEqual(res["content"], OPENAPI)

    @mock.patch("requests.post")
    def test_bundle_sends_the_query_parameter(self, mock_post):
        mock_post.return_value = make_response(200, text=OPENAPI)
        SanshainClient("http://x").require_bundle("c", "events", "1.0.0", TWO, "asyncapi", fmt="openapi")
        self.assertEqual(mock_post.call_args[1]["params"], {"format": "openapi"})
        self.assertNotIn("format", mock_post.call_args[1]["json"])

    @mock.patch("requests.post")
    @mock.patch("requests.get")
    def test_nothing_changes_without_format(self, mock_get, mock_post):
        mock_get.return_value = make_response(200, text=ASYNCAPI)
        mock_post.return_value = make_response(200, text=ASYNCAPI)
        client = SanshainClient("http://x")
        client.require("c", "events", "1.0.0", "user/signup", "PUB", "asyncapi")
        client.require_bundle("c", "events", "1.0.0", TWO, "asyncapi")
        self.assertNotIn("format", mock_get.call_args[1]["params"])
        self.assertIsNone(mock_post.call_args[1]["params"])

    @mock.patch("requests.get")
    def test_a_non_openapi_answer_needs_service_2_4(self, mock_get):
        mock_get.side_effect = [make_response(200, text=ASYNCAPI), make_response(200, {"version": "2.3.0"})]
        with self.assertRaises(SanshainError) as ctx:
            SanshainClient("http://x").require("c", "events", "1.0.0", "p", "PUB", "asyncapi", fmt="openapi")
        self.assertEqual(str(ctx.exception), "format: openapi needs Sanshain Service 2.4.0 or later (server is 2.3.0)")

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_a_non_openapi_bundle_with_unknown_server_version(self, mock_post, mock_get):
        mock_post.return_value = make_response(200, text=ASYNCAPI)
        mock_get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(SanshainError) as ctx:
            SanshainClient("http://x").require_bundle("c", "events", "1.0.0", TWO, "asyncapi", fmt="openapi")
        self.assertEqual(
            str(ctx.exception), "format: openapi needs Sanshain Service 2.4.0 or later (server version unknown)"
        )


class TestEtagPerFormat(unittest.TestCase):
    def test_keys_differ_by_format(self):
        self.assertNotEqual(
            SanshainCache.require_key("e", "1.0.0", "PUB", "p"),
            SanshainCache.require_key("e", "1.0.0", "PUB", "p", "openapi"),
        )
        self.assertNotEqual(
            SanshainCache.require_bundle_key("e", "1.0.0"),
            SanshainCache.require_bundle_key("e", "1.0.0", "openapi"),
        )

    def test_keys_without_format_are_unchanged(self):
        self.assertEqual(SanshainCache.require_key("e", "1.0.0", "GET", "/x"), "e|1.0.0|GET|/x")
        self.assertEqual(SanshainCache.require_bundle_key("e", "1.0.0"), "e|1.0.0|bundle")


class FormatProject(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.folder)  # keep the .sanshain-cache inside the temp dir

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.folder)

    def write_config(self, requires, **extra):
        path = os.path.join(self.folder, "sanshain.yaml")
        with open(path, "w") as f:
            yaml.dump({"sanshainUrl": "http://localhost:8080", "serviceName": "svc", "requires": requires, **extra}, f)
        return path

    def run_cli(self, config_file, *extra, get=None):
        argv = ["sanshain-conan", "--config", config_file, *extra, "require"]
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("requests.get", side_effect=get) as mock_get:
                with mock.patch("sys.argv", argv):
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        try:
                            main()
                        except SystemExit as e:
                            code = e.code
        return code, out.getvalue(), err.getvalue(), mock_get


class TestCliFormat(FormatProject):
    def test_both_formats_side_by_side_with_their_own_etags(self):
        config_file = self.write_config(
            [
                entry(apiType="asyncapi", outputDirectory="async"),
                entry(apiType="asyncapi", format="openapi", outputDirectory="rest"),
            ]
        )
        answers = [
            make_response(200, text=ASYNCAPI, headers={"ETag": '"a"'}),
            make_response(200, text=OPENAPI, headers={"ETag": '"o"'}),
        ]
        code, _, err, mock_get = self.run_cli(config_file, get=answers)
        self.assertEqual(code, 0)
        self.assertNotIn("O_o", err)
        self.assertNotIn("format", mock_get.call_args_list[0][1]["params"])
        self.assertEqual(mock_get.call_args_list[1][1]["params"]["format"], "openapi")
        # Same file name, the output directory tells them apart.
        with open(os.path.join(self.folder, "async", "events.yaml")) as f:
            self.assertEqual(f.read(), ASYNCAPI)
        with open(os.path.join(self.folder, "rest", "events.yaml")) as f:
            self.assertEqual(f.read(), OPENAPI)
        requires = SanshainCache().state["requires"]
        self.assertEqual(requires["events|1.0.0|PUB|user/signup"]["etag"], '"a"')
        self.assertEqual(requires["events|1.0.0|PUB|user/signup|format=openapi"]["etag"], '"o"')

    def test_wrong_api_type_is_rejected_before_any_call(self):
        config_file = self.write_config([entry(format="openapi")])
        code, out, _, mock_get = self.run_cli(config_file)
        self.assertEqual(code, 1)
        self.assertIn("apiType: asyncapi with format: openapi", out)
        mock_get.assert_not_called()

    def test_non_openapi_answer_fails(self):
        config_file = self.write_config([entry(apiType="asyncapi", format="openapi")])
        code, out, _, _ = self.run_cli(
            config_file, get=[make_response(200, text=ASYNCAPI), make_response(200, {"version": "2.3.0"})]
        )
        self.assertEqual(code, 1)
        self.assertIn("format: openapi needs Sanshain Service 2.4.0 or later (server is 2.3.0)", out)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "gen", "events.yaml")))

    def test_best_effort_warns_and_writes_nothing(self):
        config_file = self.write_config([entry(apiType="asyncapi", format="openapi")])
        code, out, _, _ = self.run_cli(
            config_file,
            "--best-effort",
            get=[make_response(200, text=ASYNCAPI), make_response(200, {"version": "2.3.0"})],
        )
        self.assertEqual(code, 0)
        self.assertIn("needs Sanshain Service 2.4.0", out)
        self.assertIn("Continuing (best effort)", out)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "gen", "events.yaml")))
        self.assertEqual(SanshainCache().state["requires"], {})


class TestHelperFormat(FormatProject):
    def helper(self):
        conanfile = SimpleNamespace(
            export_sources_folder=self.folder, recipe_folder=self.folder, base_folder=self.folder, output=mock.Mock()
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            return Sanshain(conanfile)

    @mock.patch("requests.get")
    def test_sends_the_format_and_writes_the_openapi(self, mock_get):
        self.write_config([entry(apiType="asyncapi", format="openapi")])
        mock_get.return_value = make_response(200, text=OPENAPI)
        self.helper().require()
        self.assertEqual(mock_get.call_args[1]["params"]["format"], "openapi")
        with open(os.path.join(self.folder, "gen", "events.yaml")) as f:
            self.assertEqual(f.read(), OPENAPI)

    def test_wrong_api_type_raises(self):
        self.write_config([entry(apiType="proto", format="openapi")])
        with self.assertRaisesRegex(ConfigError, r"requires\[0\] \(events\)"):
            self.helper()

    @mock.patch("requests.get")
    def test_best_effort_warns_on_a_non_openapi_answer(self, mock_get):
        self.write_config([entry(apiType="asyncapi", format="openapi")], bestEffort=True)
        mock_get.side_effect = [make_response(200, text=ASYNCAPI), make_response(200, {"version": "2.3.0"})]
        sanshain = self.helper()
        sanshain.require()
        errors = [c.args[0] for c in sanshain.conanfile.output.error.call_args_list]
        self.assertIn("needs Sanshain Service 2.4.0 or later (server is 2.3.0)", errors[0])
        self.assertFalse(os.path.exists(os.path.join(self.folder, "gen", "events.yaml")))


if __name__ == "__main__":
    unittest.main()
