"""The graph never fails a build: Sanshain-Warning headers, strict, local trunk+tag, catalog recorded: false."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml
from urllib3 import HTTPHeaderDict

from sanshainconan.cli import main
from sanshainconan.client import SanshainClient, SanshainError, StrictError, warning_lines
from sanshainconan.integration import Sanshain

UNKNOWN_TAG = "no sanshain-branch 'R' - this build was not recorded in a release graph"
BOTH = "trunk and tag are mutually exclusive - this build was recorded in neither"
LOCAL_BOTH = "trunk and tag are mutually exclusive - this build is recorded in neither"
# A warning containing a comma must never be split into two.
WITH_COMMA = "catalog-info.yaml: no Component named 'orders', found 'billing'"
CATALOG = "apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata:\n  name: orders-service\n"
PROVIDE_OK = {"version": "1.0.0", "stability": "snapshot", "changes": {"inserts": 1, "updates": 0, "deletes": 0}}


def make_response(status_code=200, json_data=None, text="", warnings=()):
    """A response whose headers look like requests' over urllib3: the raw
    headers keep every line, `headers` holds the comma-joined merge."""
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode()
    raw = HTTPHeaderDict()
    for line in warnings:
        raw.add("Sanshain-Warning", line)
    resp.raw.headers = raw
    resp.headers = {"Sanshain-Warning": ", ".join(warnings)} if warnings else {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


class TestWarningLines(unittest.TestCase):
    def test_each_header_line_is_one_warning(self):
        resp = make_response(warnings=(UNKNOWN_TAG, WITH_COMMA))
        self.assertEqual(warning_lines(resp), [UNKNOWN_TAG, WITH_COMMA])

    def test_no_header_is_no_warning(self):
        self.assertEqual(warning_lines(make_response()), [])

    def test_merged_value_is_the_fallback_and_never_split(self):
        resp = mock.Mock()
        resp.raw = None
        resp.headers = {"Sanshain-Warning": WITH_COMMA}
        self.assertEqual(warning_lines(resp), [WITH_COMMA])


class TestClientWarnings(unittest.TestCase):
    def client(self, strict=False):
        self.printed = []
        return SanshainClient("http://x", on_warning=self.printed.append, strict=strict)

    @mock.patch("requests.post")
    def test_every_header_line_is_reported_in_order(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG, WITH_COMMA))
        result = self.client().provide("svc", "openapi: 3.0.0", "snapshot", tag="R")
        self.assertEqual(self.printed, [UNKNOWN_TAG, WITH_COMMA])
        self.assertEqual(result["version"], "1.0.0")

    @mock.patch("requests.post")
    def test_strict_fails_after_the_call_with_the_first_warning(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG, WITH_COMMA))
        with self.assertRaises(StrictError) as ctx:
            self.client(strict=True).provide("svc", "openapi: 3.0.0", "snapshot", tag="R")
        self.assertEqual(str(ctx.exception), f"strict: Sanshain warned: {UNKNOWN_TAG}")
        self.assertIsNone(ctx.exception.error)
        self.assertEqual(self.printed, [UNKNOWN_TAG, WITH_COMMA])

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_a_failed_call_still_reports_its_warning(self, mock_post, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.4.0"})
        mock_post.return_value = make_response(500, text="boom", warnings=(BOTH,))
        with self.assertRaisesRegex(SanshainError, "status 500"):
            self.client().provide("svc", "openapi: 3.0.0", "snapshot")
        self.assertEqual(self.printed, [BOTH])

        with self.assertRaises(StrictError) as ctx:
            self.client(strict=True).provide("svc", "openapi: 3.0.0", "snapshot")
        self.assertEqual(str(ctx.exception), f"strict: Sanshain warned: {BOTH}")
        self.assertIn("status 500", str(ctx.exception.error))

    @mock.patch("requests.post")
    def test_retire_reports_warnings(self, mock_post):
        mock_post.return_value = make_response(202, {"trunk_pins_closed": 0}, warnings=(WITH_COMMA,))
        self.client().retire("svc")
        self.assertEqual(self.printed, [WITH_COMMA])

    @mock.patch("requests.get")
    def test_require_reports_warnings_also_on_304(self, mock_get):
        mock_get.return_value = make_response(200, text="paths: {}", warnings=(UNKNOWN_TAG,))
        self.client().require("c", "p", "1.0.0", "/x", "GET", tag="R")
        mock_get.return_value = make_response(304, warnings=(UNKNOWN_TAG,))
        self.assertTrue(self.client().require("c", "p", "1.0.0", "/x", "GET", tag="R")["not_modified"])
        self.assertEqual(self.printed, [UNKNOWN_TAG])

    @mock.patch("requests.post")
    def test_bundle_reports_warnings_and_strict_fails(self, mock_post):
        mock_post.return_value = make_response(200, text="paths: {}", warnings=(UNKNOWN_TAG,))
        endpoints = [{"path": "/x", "method": "GET"}, {"path": "/y", "method": "GET"}]
        with self.assertRaisesRegex(StrictError, "strict: Sanshain warned: no sanshain-branch 'R'"):
            self.client(strict=True).require_bundle("c", "p", "1.0.0", endpoints, tag="R")
        self.assertEqual(self.printed, [UNKNOWN_TAG])

    @mock.patch("requests.put")
    def test_catalog_not_recorded_is_a_warning(self, mock_put):
        body = {"system": "s", "trunk": False, "resources": [], "recorded": False}
        mock_put.return_value = make_response(200, body, warnings=(WITH_COMMA,))
        self.assertEqual(self.client().push_catalog("s", CATALOG, file_label="/p/c.yaml"), body)
        self.assertEqual(self.printed, [WITH_COMMA])

    @mock.patch("requests.put")
    def test_catalog_not_recorded_without_header_names_the_file(self, mock_put):
        body = {"system": "s", "trunk": False, "resources": [], "recorded": False}
        mock_put.return_value = make_response(200, body)
        self.client().push_catalog("s", CATALOG, file_label="/p/c.yaml")
        self.assertEqual(self.printed, ["Sanshain did not record /p/c.yaml"])
        with self.assertRaisesRegex(StrictError, "^strict: Sanshain did not record /p/c.yaml$"):
            self.client(strict=True).push_catalog("s", CATALOG, file_label="/p/c.yaml")

    @mock.patch("requests.put")
    def test_catalog_without_recorded_counts_as_recorded(self, mock_put):
        mock_put.return_value = make_response(200, {"system": "s", "trunk": False, "resources": []})
        self.client(strict=True).push_catalog("s", CATALOG)
        self.assertEqual(self.printed, [])

    @mock.patch("requests.get")
    @mock.patch("requests.put")
    def test_catalog_400_from_an_old_service_uses_the_normal_mapping(self, mock_put, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.4.0"})
        mock_put.return_value = make_response(400, text="bad")
        with self.assertRaisesRegex(SanshainError, r"Request failed with status 400: bad"):
            self.client().push_catalog("s", CATALOG)


class Project(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.dir)  # the CLI's ETag cache lands here
        with open(os.path.join(self.dir, "api.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 1.0.0\n")
        with open(os.path.join(self.dir, "catalog-info.yaml"), "w") as f:
            f.write(CATALOG)
        self.write_config()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir)

    def write_config(self, **extra):
        self.config_file = os.path.join(self.dir, "sanshain.yaml")
        config = {
            "sanshainUrl": "http://localhost:8080",
            "serviceName": "orders-service",
            "provide": {"file": "api.yaml"},
            "requires": [
                {
                    "serviceName": "p",
                    "version": "1.0.0",
                    "outputDirectory": "out",
                    "endpoints": [{"path": "/x", "method": "GET"}],
                }
            ],
            "catalogInfo": "catalog-info.yaml",
            **extra,
        }
        with open(self.config_file, "w") as f:
            yaml.dump(config, f)


class TestCliWarnings(Project):
    def run_cli(self, command, *extra, env=None, post=None, put=None, get=None):
        argv = ["sanshain-conan", "--config", self.config_file, *extra, command]
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}, clear=True):
            with mock.patch("requests.post", return_value=post or make_response(202, PROVIDE_OK)) as mock_post:
                with mock.patch("requests.put", return_value=put) as mock_put:
                    with mock.patch("requests.get", return_value=get or make_response(200, {"version": "2.4.0"})):
                        with mock.patch("sys.argv", argv):
                            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                                try:
                                    main()
                                except SystemExit as e:
                                    code = e.code
        self.mock_post, self.mock_put = mock_post, mock_put
        return code, out.getvalue()

    def test_a_single_warning_is_printed_and_the_build_passes(self):
        code, out = self.run_cli("provide", "--tag", "R", post=make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG,)))
        self.assertEqual(code, 0)
        self.assertIn(f"⚠ {UNKNOWN_TAG}\n", out)
        self.assertIn("Successfully provided.", out)

    def test_every_warning_is_printed_once(self):
        code, out = self.run_cli("provide", post=make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG, WITH_COMMA)))
        self.assertEqual(code, 0)
        self.assertEqual(out.count(f"⚠ {UNKNOWN_TAG}\n"), 1)
        self.assertEqual(out.count(f"⚠ {WITH_COMMA}\n"), 1)

    def test_strict_fails_on_a_warning_also_with_best_effort(self):
        self.write_config(strict=True)
        for extra in ((), ("--best-effort",)):
            with self.subTest(extra=extra):
                code, out = self.run_cli(
                    "provide", *extra, post=make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG, WITH_COMMA))
                )
                self.assertEqual(code, 1)
                self.assertIn(f"⚠ {WITH_COMMA}\n", out)
                self.assertTrue(out.endswith(f"✗ strict: Sanshain warned: {UNKNOWN_TAG}\n"), out)
                self.assertNotIn("Successfully provided.", out)

    def test_strict_require_fails_also_with_best_effort(self):
        self.write_config(strict=True, bestEffort=True)
        get = make_response(200, text="paths: {}", warnings=(UNKNOWN_TAG,))
        with mock.patch("requests.get", return_value=get), mock.patch.dict(os.environ, {}, clear=True):
            argv = ["sanshain-conan", "--config", self.config_file, "require"]
            out = io.StringIO()
            with mock.patch("sys.argv", argv), contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit) as ctx:
                    main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(f"✗ strict: Sanshain warned: {UNKNOWN_TAG}", out.getvalue())
        self.assertNotIn("Continuing (best effort)", out.getvalue())

    def test_a_failed_call_prints_the_error_then_the_strict_failure(self):
        self.write_config(strict=True)
        code, out = self.run_cli("provide", post=make_response(500, text="boom", warnings=(BOTH,)))
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(
            lines[-3:], [f"⚠ {BOTH}", "✗ Request failed with status 500: boom", f"✗ strict: Sanshain warned: {BOTH}"]
        )

    def test_local_trunk_and_tag_warn_and_send_neither(self):
        code, out = self.run_cli("provide", "--trunk", "--tag", "R")
        self.assertEqual(code, 0)
        self.assertIn(f"⚠ {LOCAL_BOTH}\n", out)
        payload = self.mock_post.call_args[1]["json"]
        self.assertNotIn("trunk", payload)
        self.assertNotIn("tag", payload)

        code, out = self.run_cli("provide", env={"SANSHAIN_TRUNK": "true", "SANSHAIN_TAG": "R"})
        self.assertEqual(code, 0)
        self.assertIn(f"⚠ {LOCAL_BOTH}\n", out)

    def test_local_trunk_and_tag_under_strict_fail_before_any_request(self):
        self.write_config(strict=True)
        for extra in (("--trunk", "--tag", "R"), ("--trunk", "--tag", "R", "--best-effort")):
            with self.subTest(extra=extra):
                code, out = self.run_cli("provide", *extra)
                self.assertEqual(code, 1)
                self.assertEqual(out, f"✗ strict: {LOCAL_BOTH}\n")
                self.mock_post.assert_not_called()

    def test_catalog_not_recorded_warns_and_passes(self):
        body = {"system": "orders-service", "trunk": False, "resources": [], "recorded": False}
        code, out = self.run_cli("catalog", put=make_response(200, body, warnings=(WITH_COMMA,)))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"⚠ {WITH_COMMA}\n")

    def test_catalog_not_recorded_without_header_names_the_file(self):
        body = {"system": "orders-service", "trunk": False, "resources": [], "recorded": False}
        code, out = self.run_cli("catalog", put=make_response(200, body))
        self.assertEqual(code, 0)
        self.assertEqual(out, f"⚠ Sanshain did not record {os.path.join(self.dir, 'catalog-info.yaml')}\n")

    def test_catalog_not_recorded_under_strict_fails(self):
        self.write_config(strict=True)
        body = {"system": "orders-service", "trunk": False, "resources": [], "recorded": False}
        code, out = self.run_cli("catalog", "--best-effort", put=make_response(200, body, warnings=(WITH_COMMA,)))
        self.assertEqual(code, 1)
        self.assertEqual(out, f"⚠ {WITH_COMMA}\n✗ strict: Sanshain warned: {WITH_COMMA}\n")

    def test_catalog_failure_is_still_softened_by_best_effort(self):
        code, out = self.run_cli("catalog", "--best-effort", put=make_response(500, text="boom"))
        self.assertEqual(code, 0)
        self.assertIn("⚠ Request failed with status 500: boom", out)
        self.assertIn("Continuing (best effort)", out)


class TestHelperWarnings(Project):
    def helper(self, env=None):
        conanfile = SimpleNamespace(
            export_sources_folder=self.dir, recipe_folder=self.dir, base_folder=self.dir, output=mock.Mock()
        )
        with mock.patch.dict(os.environ, env or {}, clear=True):
            return Sanshain(conanfile, config_path=self.config_file)

    def warnings(self, sanshain):
        return [c.args[0] for c in sanshain.conanfile.output.warning.call_args_list]

    def errors(self, sanshain):
        return [c.args[0] for c in sanshain.conanfile.output.error.call_args_list]

    @mock.patch("requests.post")
    def test_every_warning_goes_to_output_warning(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG, WITH_COMMA))
        sanshain = self.helper()
        sanshain.provide()
        self.assertEqual(self.warnings(sanshain), [f"Sanshain: {UNKNOWN_TAG}", f"Sanshain: {WITH_COMMA}"])

    @mock.patch("requests.post")
    def test_strict_raises_on_a_warning_also_with_best_effort(self, mock_post):
        self.write_config(strict=True, bestEffort=True)
        mock_post.return_value = make_response(202, PROVIDE_OK, warnings=(UNKNOWN_TAG,))
        sanshain = self.helper()
        with self.assertRaisesRegex(StrictError, f"^strict: Sanshain warned: {UNKNOWN_TAG}$"):
            sanshain.provide()
        self.assertEqual(self.errors(sanshain), [f"Sanshain: strict: Sanshain warned: {UNKNOWN_TAG}"])

    @mock.patch("requests.get")
    def test_strict_require_is_not_softened_by_best_effort(self, mock_get):
        self.write_config(strict=True, bestEffort=True)
        mock_get.return_value = make_response(200, text="paths: {}", warnings=(UNKNOWN_TAG,))
        sanshain = self.helper()
        with self.assertRaises(StrictError):
            sanshain.require()
        self.assertEqual(self.warnings(sanshain), [f"Sanshain: {UNKNOWN_TAG}"])

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_a_failed_call_logs_the_error_then_the_strict_failure(self, mock_post, mock_get):
        self.write_config(strict=True)
        mock_get.return_value = make_response(200, {"version": "2.4.0"})
        mock_post.return_value = make_response(500, text="boom", warnings=(BOTH,))
        sanshain = self.helper()
        with self.assertRaises(StrictError):
            sanshain.provide()
        self.assertEqual(
            self.errors(sanshain),
            ["Sanshain: Request failed with status 500: boom", f"Sanshain: strict: Sanshain warned: {BOTH}"],
        )

    @mock.patch("requests.post")
    def test_local_trunk_and_tag_warn_and_send_neither(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)
        sanshain = self.helper(env={"SANSHAIN_TRUNK": "true", "SANSHAIN_TAG": "R"})
        self.assertEqual(self.warnings(sanshain), [f"Sanshain: {LOCAL_BOTH}"])
        sanshain.provide()
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("trunk", payload)
        self.assertNotIn("tag", payload)

    def test_local_trunk_and_tag_under_strict_raise(self):
        self.write_config(strict=True)
        with self.assertRaisesRegex(StrictError, f"^strict: {LOCAL_BOTH}$"):
            self.helper(env={"SANSHAIN_TRUNK": "true", "SANSHAIN_TAG": "R"})

    @mock.patch("requests.put")
    def test_catalog_not_recorded_warns(self, mock_put):
        body = {"system": "orders-service", "trunk": False, "resources": [], "recorded": False}
        mock_put.return_value = make_response(200, body, warnings=(WITH_COMMA,))
        sanshain = self.helper()
        sanshain.catalog()
        self.assertEqual(self.warnings(sanshain), [f"Sanshain: {WITH_COMMA}"])
        sanshain.conanfile.output.info.assert_not_called()

        self.write_config(strict=True)
        with self.assertRaisesRegex(StrictError, "strict: Sanshain warned"):
            self.helper().catalog()

    @mock.patch("requests.get")
    @mock.patch("requests.put")
    def test_catalog_failure_raises_unless_best_effort(self, mock_put, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.4.0"})
        mock_put.return_value = make_response(500, text="boom")
        with self.assertRaisesRegex(SanshainError, "status 500"):
            self.helper().catalog()

        self.write_config(bestEffort=True)
        sanshain = self.helper()
        sanshain.catalog()
        self.assertEqual(
            self.warnings(sanshain),
            ["Sanshain: Request failed with status 500: boom", "Sanshain: Continuing (best effort)"],
        )


if __name__ == "__main__":
    unittest.main()
