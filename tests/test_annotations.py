"""Annotations: read from sanshain.yaml, placeholders filled, sent where each call may carry them."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml

from sanshainconan.annotations import fill_annotations, parse_set
from sanshainconan.cli import main
from sanshainconan.client import ANNOTATIONS_DROPPED_WARNING, ORIGIN_DROPPED_WARNING, SanshainClient, SanshainError
from sanshainconan.config import ConfigError, SanshainConfig, find_unknown_fields
from sanshainconan.integration import Sanshain

PROVIDE_OK = {"version": "1.0.0", "stability": "snapshot", "content_hash": "sha256:abc", "changes": {}}

VERSION = {"scope": "version", "name": "requirements", "value": "http://solar.system/id-7/requirements/42"}
SYSTEM = {"scope": "system", "name": "jenkins", "value": "https://jenkins.corp/job/payments"}
BOTH = [VERSION, SYSTEM]

# What a 2.9-2.12 service answers: the refused field, then every field it knows.
PROVIDE_REFUSES_ANNOTATIONS = (
    "Failed to deserialize the JSON body into the target type: unknown field `annotations`, expected one of "
    "`producername`, `openapi_yaml`, `stability`, `dry_run`, `trunk`, `tag`, `retired`, `build_url`, "
    "`change_url`, `tickets`, `note` at line 1 column 212"
)
# A 2.8 service knows neither the origin nor annotations.
OLD_REFUSES_ORIGIN = (
    "Failed to deserialize the JSON body into the target type: unknown field `build_url`, expected one of "
    "`producername`, `openapi_yaml`, `stability`, `dry_run`, `trunk`, `tag`, `retired` at line 1 column 80"
)
OLD_REFUSES_ANNOTATIONS = (
    "Failed to deserialize the JSON body into the target type: unknown field `annotations`, expected one of "
    "`producername`, `openapi_yaml`, `stability`, `dry_run`, `trunk`, `tag`, `retired` at line 1 column 90"
)
REQUIRE_REFUSES_ANNOTATIONS = (
    "Failed to deserialize query string: unknown field `annotations`, expected one of `consumername`, "
    "`producername`, `version`, `path`, `method`, `dry_run`, `trunk`, `tag`, `format`"
)
BUNDLE_REFUSES_ANNOTATIONS = (
    "Failed to deserialize the JSON body into the target type: unknown field `annotations`, expected one of "
    "`consumername`, `producername`, `version`, `endpoints`, `api_type`, `dry_run`, `trunk`, `tag`"
)
CATALOG_REFUSES_ANNOTATIONS = (
    "Failed to deserialize the JSON body into the target type: unknown field `annotations`, expected one of "
    "`catalog_info_yaml`, `trunk`"
)


def make_response(status_code=200, json_data=None, text="", headers=None, content=b""):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


def entry(value, name="e", scope="system"):
    return {"scope": scope, "name": name, "value": value}


def filled(value, sets=None, env=None):
    annotations, warnings = fill_annotations([entry(value)], sets, env=env or {})
    return (annotations[0]["value"] if annotations else None), warnings


class TestFillAnnotations(unittest.TestCase):
    def test_1_flag_and_environment_fill_their_placeholders(self):
        self.assertEqual(filled("x-{{A}}-{{B}}", {"A": "1"}, {"SANSHAIN_SET_B": "2"}), ("x-1-2", []))

    def test_2_the_flag_wins(self):
        self.assertEqual(filled("{{A}}", {"A": "f"}, {"SANSHAIN_SET_A": "e"}), ("f", []))

    def test_3_a_placeholder_repeats(self):
        self.assertEqual(filled("{{A}}/{{A}}", {"A": "7"}), ("7/7", []))

    def test_4_an_unfilled_entry_is_left_out_and_named(self):
        declared = [entry("{{MISSING}}", name="requirements"), SYSTEM]
        annotations, warnings = fill_annotations(declared, {}, env={})
        self.assertEqual(annotations, [SYSTEM])
        self.assertEqual(
            warnings,
            ["annotation 'requirements' left out: {{MISSING}} is not set (--set MISSING=… or SANSHAIN_SET_MISSING)"],
        )

    def test_4_the_warning_names_the_first_unfilled_placeholder(self):
        _, warnings = fill_annotations([entry("{{A}}{{B}}{{C}}", name="n")], {"A": "1"}, env={})
        self.assertEqual(warnings, ["annotation 'n' left out: {{B}} is not set (--set B=… or SANSHAIN_SET_B)"])

    def test_6_an_empty_flag_is_unfilled_and_does_not_fall_through(self):
        self.assertEqual(filled("{{A}}", {"A": ""})[0], None)
        value, warnings = filled("{{A}}", {"A": ""}, {"SANSHAIN_SET_A": "e"})
        self.assertIsNone(value)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(filled("{{A}}", {}, {"SANSHAIN_SET_A": ""})[0], None)

    def test_7_a_plain_value_is_unchanged(self):
        self.assertEqual(filled("plain value"), ("plain value", []))

    def test_8_other_braces_are_literal(self):
        for value in ("{{ A }}", "{{a-b}}", "{{}}"):
            with self.subTest(value=value):
                self.assertEqual(filled(value, {"A": "1", "a-b": "2"}, {"SANSHAIN_SET_A": "3"}), (value, []))

    def test_9_set_splits_at_the_first_equals(self):
        self.assertEqual(parse_set("A=x=y"), ("A", "x=y"))
        self.assertEqual(parse_set("A="), ("A", ""))
        for bad in ("A", "=x", ""):
            with self.subTest(arg=bad), self.assertRaises(ValueError):
                parse_set(bad)

    def test_the_variable_name_is_exact_case(self):
        self.assertEqual(filled("{{Id}}", {}, {"SANSHAIN_SET_ID": "1", "SANSHAIN_SET_Id": "2"}), ("2", []))
        self.assertIsNone(filled("{{id}}", {}, {"SANSHAIN_SET_ID": "1"})[0])

    def test_the_process_environment_is_the_default(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_SET_ID": "9"}, clear=True):
            annotations, _ = fill_annotations([entry("{{ID}}")])
        self.assertEqual(annotations[0]["value"], "9")

    def test_without_the_flag_hint_only_the_variable_is_named(self):
        _, warnings = fill_annotations([entry("{{ID}}", name="r")], env={}, flag_hint=False)
        self.assertEqual(warnings, ["annotation 'r' left out: {{ID}} is not set (SANSHAIN_SET_ID)"])

    def test_only_the_three_fields_are_sent(self):
        annotations, _ = fill_annotations([{**SYSTEM, "extra": 1}], env={})
        self.assertEqual(annotations, [SYSTEM])

    def test_nothing_declared_is_nothing(self):
        self.assertEqual(fill_annotations(None, env={}), ([], []))
        self.assertEqual(fill_annotations([], env={}), ([], []))


class TestAnnotationsConfig(unittest.TestCase):
    def config(self, annotations):
        with mock.patch.dict(os.environ, {}, clear=True):
            return SanshainConfig({"sanshainUrl": "x", "annotations": annotations})

    def error(self, annotations):
        with self.assertRaises(ConfigError) as ctx:
            self.config(annotations)
        return str(ctx.exception)

    def test_entries_are_kept_as_written(self):
        declared = [entry("{{ID}}", scope="version"), SYSTEM]
        self.assertEqual(self.config(declared).annotations, declared)
        self.assertEqual(self.config(None).annotations, [])

    def test_is_a_known_field_and_an_extra_key_is_unknown(self):
        self.assertEqual(find_unknown_fields({"sanshainUrl": "x", "annotations": [SYSTEM]}), [])
        self.assertEqual(
            find_unknown_fields({"sanshainUrl": "x", "annotations": [SYSTEM, {**VERSION, "scop": "x"}]}),
            ["annotations[1].scop"],
        )
        self.assertEqual(self.config([{**SYSTEM, "extra": "x"}]).unknown_fields, ["annotations[0].extra"])

    def test_an_extra_key_under_strict_fails(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                SanshainConfig({"sanshainUrl": "x", "strict": True, "annotations": [{**SYSTEM, "extra": "x"}]})
        self.assertTrue(ctx.exception.strict)
        self.assertEqual(ctx.exception.unknown_fields, ["annotations[0].extra"])

    def test_a_missing_field_names_the_entry(self):
        self.assertEqual(
            self.error([{"scope": "system", "name": "jenkins"}]), "annotations[0] (jenkins): missing 'value'"
        )
        self.assertEqual(self.error([SYSTEM, {"scope": "system", "value": "v"}]), "annotations[1]: missing 'name'")
        self.assertEqual(self.error([{"name": "n", "value": "v"}]), "annotations[0] (n): missing 'scope'")

    def test_a_wrong_type_is_an_error_not_converted(self):
        self.assertEqual(
            self.error([{"scope": "system", "name": "jenkins", "value": 42}]),
            "annotations[0] (jenkins): 'value' must be a string, not 42",
        )
        self.assertEqual(
            self.error([{"scope": "system", "name": 7, "value": "v"}]), "annotations[0]: 'name' must be a string, not 7"
        )

    def test_another_scope_is_an_error(self):
        self.assertEqual(
            self.error([{"scope": "producer", "name": "n", "value": "v"}]),
            "annotations[0] (n): scope 'producer' is not supported — use version or system",
        )

    def test_not_a_list_of_entries_is_an_error(self):
        self.assertEqual(self.error({"name": "n"}), "annotations must be a list of entries with scope, name and value")
        self.assertEqual(self.error(["x"]), "annotations[0]: must be an entry with scope, name and value")


class TestAnnotationsOnTheWire(unittest.TestCase):
    def client(self, strict=False):
        return SanshainClient("http://localhost:8080", strict=strict)

    @mock.patch("requests.post")
    def test_every_provide_carries_both_scopes(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)
        client = self.client()
        for call in (client.provide, client.provide_asyncapi, client.provide_proto):
            with self.subTest(call=call.__name__):
                call("svc", "x", "snapshot", annotations=BOTH)
                self.assertEqual(mock_post.call_args[1]["json"]["annotations"], BOTH)

    @mock.patch("requests.post")
    def test_no_annotations_no_field(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)
        self.client().provide("svc", "x", "snapshot", annotations=[])
        self.assertNotIn("annotations", mock_post.call_args[1]["json"])
        self.client().require_bundle("c", "p", "1.0.0", [{"method": "GET", "path": "/a"}], annotations=[VERSION])
        self.assertNotIn("annotations", mock_post.call_args[1]["json"])

    @mock.patch("requests.get")
    def test_require_carries_the_system_ones_as_a_json_query_parameter(self, mock_get):
        mock_get.return_value = make_response(200, text="paths: {}", content=b"paths: {}")
        client = self.client()
        client.require("c", "p", "1.0.0", "/a", "GET", annotations=BOTH)
        params = mock_get.call_args[1]["params"]
        self.assertEqual(json.loads(params["annotations"]), [SYSTEM])
        for api_type in ("asyncapi", "grpc"):
            with self.subTest(api_type=api_type):
                client.require("c", "p", "1.0.0", "/a", "GET", api_type=api_type, annotations=BOTH)
                self.assertEqual(json.loads(mock_get.call_args[1]["params"]["annotations"]), [SYSTEM])
        client.require("c", "p", "1.0.0", "/a", "GET", annotations=[VERSION])
        self.assertNotIn("annotations", mock_get.call_args[1]["params"])

    @mock.patch("requests.post")
    def test_bundle_carries_the_system_ones_in_the_body(self, mock_post):
        mock_post.return_value = make_response(200, text="paths: {}", content=b"paths: {}")
        self.client().require_bundle("c", "p", "1.0.0", [{"method": "GET", "path": "/a"}], annotations=BOTH)
        self.assertEqual(mock_post.call_args[1]["json"]["annotations"], [SYSTEM])

    @mock.patch("requests.put")
    def test_catalog_carries_the_system_ones_in_the_body(self, mock_put):
        mock_put.return_value = make_response(200, {"system": "svc", "resources": []})
        self.client().push_catalog("svc", "kind: Component", annotations=BOTH)
        self.assertEqual(
            mock_put.call_args[1]["json"], {"catalog_info_yaml": "kind: Component", "annotations": [SYSTEM]}
        )


class TestOldServiceRefusingAnnotations(unittest.TestCase):
    def setUp(self):
        self.stderr = io.StringIO()
        patcher = mock.patch("sys.stderr", self.stderr)
        patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch("requests.post")
    def test_provide_is_repeated_without_them_and_warns_once(self, mock_post):
        mock_post.side_effect = [
            make_response(422, text=PROVIDE_REFUSES_ANNOTATIONS),
            make_response(202, PROVIDE_OK),
            make_response(202, PROVIDE_OK),
        ]
        client = SanshainClient("http://localhost:8080", strict=True)
        origin = {"build_url": "https://ci/1"}
        self.assertEqual(client.provide("svc", "x", "snapshot", origin=origin, annotations=BOTH), PROVIDE_OK)
        first, second = (c[1]["json"] for c in mock_post.call_args_list[:2])
        self.assertEqual(first["annotations"], BOTH)
        self.assertNotIn("annotations", second)
        # The refusal lists build_url among the fields it expects: the origin stays.
        self.assertEqual(second["build_url"], "https://ci/1")
        # The rest of the command sends none, and the warning is printed once.
        client.provide_asyncapi("svc", "x", "snapshot", annotations=BOTH)
        self.assertNotIn("annotations", mock_post.call_args[1]["json"])
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(self.stderr.getvalue(), f"⚠ {ANNOTATIONS_DROPPED_WARNING}\n")
        self.assertEqual(
            ANNOTATIONS_DROPPED_WARNING,
            "Sanshain Service before 2.13.0 does not take annotations; sending without them",
        )

    @mock.patch("requests.post")
    def test_a_2_8_service_refuses_both_in_either_order(self, mock_post):
        for refusals in ((OLD_REFUSES_ORIGIN, OLD_REFUSES_ANNOTATIONS), (OLD_REFUSES_ANNOTATIONS, OLD_REFUSES_ORIGIN)):
            with self.subTest(first=refusals[0][60:90]):
                mock_post.reset_mock()
                mock_post.side_effect = [make_response(422, text=t) for t in refusals] + [
                    make_response(202, PROVIDE_OK)
                ]
                client = SanshainClient("http://localhost:8080")
                result = client.provide("svc", "x", "snapshot", origin={"note": "why"}, annotations=BOTH)
                self.assertEqual(result, PROVIDE_OK)
                self.assertEqual(mock_post.call_count, 3)
                last = mock_post.call_args[1]["json"]
                self.assertNotIn("annotations", last)
                self.assertNotIn("note", last)
        out = self.stderr.getvalue()
        self.assertEqual(out.count(ANNOTATIONS_DROPPED_WARNING), 2)  # once per client
        self.assertEqual(out.count(ORIGIN_DROPPED_WARNING), 2)

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_a_field_listed_only_as_expected_triggers_no_fallback(self, mock_post, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.12.0"})
        refusal = (
            "Failed to deserialize the JSON body into the target type: unknown field `colour`, expected one of "
            "`producername`, `openapi_yaml`, `stability`, `build_url`, `change_url`, `tickets`, `note`, `annotations`"
        )
        mock_post.return_value = make_response(422, text=refusal)
        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.provide("svc", "x", "snapshot", origin={"build_url": "https://ci/1"}, annotations=BOTH)
        self.assertIn("Invalid request shape (422)", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(self.stderr.getvalue(), "")
        self.assertFalse(client.annotations_refused)

    @mock.patch("requests.get")
    def test_require_400_is_repeated_without_the_parameter_before_the_format_check(self, mock_get):
        doc = "openapi: 3.0.3\npaths: {}\n"
        mock_get.side_effect = [
            make_response(400, text=REQUIRE_REFUSES_ANNOTATIONS),
            make_response(200, text=doc, content=doc.encode()),
        ]
        client = SanshainClient("http://localhost:8080")
        result = client.require("c", "p", "1.0.0", "/a", "SUB", api_type="asyncapi", fmt="openapi", annotations=BOTH)
        self.assertEqual(result["body"], doc.encode())
        first, second = (c[1]["params"] for c in mock_get.call_args_list)
        self.assertIn("annotations", first)
        self.assertNotIn("annotations", second)
        self.assertEqual(second["format"], "openapi")
        self.assertEqual(self.stderr.getvalue(), f"⚠ {ANNOTATIONS_DROPPED_WARNING}\n")

    @mock.patch("requests.post")
    def test_bundle_is_repeated_without_them(self, mock_post):
        mock_post.side_effect = [
            make_response(422, text=BUNDLE_REFUSES_ANNOTATIONS),
            make_response(200, text="paths: {}", content=b"paths: {}"),
        ]
        client = SanshainClient("http://localhost:8080")
        client.require_bundle("c", "p", "1.0.0", [{"method": "GET", "path": "/a"}], annotations=BOTH)
        first, second = (c[1]["json"] for c in mock_post.call_args_list)
        self.assertEqual(first["annotations"], [SYSTEM])
        self.assertNotIn("annotations", second)
        self.assertTrue(client.annotations_refused)

    @mock.patch("requests.put")
    def test_catalog_is_repeated_without_them(self, mock_put):
        mock_put.side_effect = [
            make_response(422, text=CATALOG_REFUSES_ANNOTATIONS),
            make_response(200, {"system": "svc", "resources": []}),
        ]
        client = SanshainClient("http://localhost:8080")
        self.assertEqual(client.push_catalog("svc", "c", annotations=BOTH)["system"], "svc")
        self.assertEqual(mock_put.call_args_list[1][1]["json"], {"catalog_info_yaml": "c"})
        self.assertEqual(self.stderr.getvalue(), f"⚠ {ANNOTATIONS_DROPPED_WARNING}\n")

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_a_refusal_without_annotations_sent_is_not_retried(self, mock_post, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.12.0"})
        mock_post.return_value = make_response(422, text=PROVIDE_REFUSES_ANNOTATIONS)
        with self.assertRaises(SanshainError):
            SanshainClient("http://localhost:8080").provide("svc", "x", "snapshot")
        self.assertEqual(mock_post.call_count, 1)


class Project(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.dir)  # the CLI's ETag cache lands here
        with open(os.path.join(self.dir, "api.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 1.0.0\n")
        with open(os.path.join(self.dir, "catalog-info.yaml"), "w") as f:
            f.write("kind: Component\n")
        self.write_config()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir)

    def write_config(self, **extra):
        self.config_file = os.path.join(self.dir, "sanshain.yaml")
        config = {
            "sanshainUrl": "http://localhost:8080",
            "serviceName": "svc",
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
            "annotations": [
                {"scope": "version", "name": "requirements", "value": "http://solar.system/id-{{AREA}}/r/{{ID}}"},
                SYSTEM,
            ],
            **extra,
        }
        with open(self.config_file, "w") as f:
            yaml.dump(config, f)


class TestCliAnnotations(Project):
    def run_cli(self, command, *extra, env=None):
        argv = ["sanshain-conan", "--config", self.config_file, *extra, command]
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}, clear=True):
            with mock.patch("requests.post", return_value=make_response(202, PROVIDE_OK)) as mock_post:
                with mock.patch("requests.put", return_value=make_response(200, {"resources": []})) as mock_put:
                    ok = make_response(200, text="paths: {}", content=b"paths: {}")
                    with mock.patch("requests.get", return_value=ok) as mock_get:
                        with mock.patch("sys.argv", argv):
                            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                                try:
                                    main()
                                except SystemExit as e:
                                    code = e.code
        self.mock_post, self.mock_put, self.mock_get = mock_post, mock_put, mock_get
        return code, out.getvalue()

    def test_provide_sends_both_scopes_filled_from_set_and_environment(self):
        code, _ = self.run_cli("provide", "--set", "AREA=7", env={"SANSHAIN_SET_ID": "42"})
        self.assertEqual(code, 0)
        self.assertEqual(
            self.mock_post.call_args[1]["json"]["annotations"],
            [{"scope": "version", "name": "requirements", "value": "http://solar.system/id-7/r/42"}, SYSTEM],
        )

    def test_set_is_repeatable_and_keeps_everything_after_the_first_equals(self):
        code, _ = self.run_cli("provide", "--set", "AREA=a", "--set", "ID=x=y", "--set", "AREA=b")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.mock_post.call_args[1]["json"]["annotations"][0]["value"], "http://solar.system/id-b/r/x=y"
        )

    def test_a_set_without_equals_is_a_usage_error(self):
        err = io.StringIO()
        with mock.patch("sys.argv", ["sanshain-conan", "--set", "AREA", "provide"]), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("expected NAME=value, got 'AREA'", err.getvalue())

    def test_an_unfilled_entry_is_left_out_with_a_warning(self):
        code, out = self.run_cli("provide", "--set", "AREA=7")
        self.assertEqual(code, 0)
        self.assertIn("⚠ annotation 'requirements' left out: {{ID}} is not set (--set ID=… or SANSHAIN_SET_ID)\n", out)
        self.assertEqual(self.mock_post.call_args[1]["json"]["annotations"], [SYSTEM])

    def test_5_strict_fails_before_any_request(self):
        self.write_config(strict=True)
        for command in ("provide", "require", "catalog"):
            with self.subTest(command=command):
                code, out = self.run_cli(command, "--set", "AREA=7", "--best-effort")
                self.assertEqual(code, 1)
                self.assertTrue(
                    out.endswith(
                        "✗ strict: annotation 'requirements' left out: {{ID}} is not set "
                        "(--set ID=… or SANSHAIN_SET_ID)\n"
                    ),
                    out,
                )
                self.mock_post.assert_not_called()
                self.mock_put.assert_not_called()
                self.mock_get.assert_not_called()

    def test_retire_sends_no_annotations(self):
        self.write_config(provide={"apiType": "openapi", "retired": True})
        code, _ = self.run_cli("provide", "--set", "AREA=7", "--set", "ID=1")
        self.assertEqual(code, 0)
        self.assertEqual(self.mock_post.call_args[1]["json"], {"producername": "svc", "retired": True})

    def test_require_sends_the_system_ones(self):
        code, _ = self.run_cli("require", "--set", "AREA=7", "--set", "ID=1")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.mock_get.call_args[1]["params"]["annotations"]), [SYSTEM])

    def test_bundle_sends_the_system_ones(self):
        self.write_config(
            requires=[
                {
                    "serviceName": "p",
                    "version": "1.0.0",
                    "outputDirectory": "out",
                    "endpoints": [{"path": "/x", "method": "GET"}, {"path": "/y", "method": "GET"}],
                }
            ]
        )
        code, _ = self.run_cli("require")
        self.assertEqual(code, 0)
        self.assertEqual(self.mock_post.call_args[1]["json"]["annotations"], [SYSTEM])

    def test_catalog_sends_the_system_ones(self):
        code, _ = self.run_cli("catalog")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.mock_put.call_args[1]["json"], {"catalog_info_yaml": "kind: Component\n", "annotations": [SYSTEM]}
        )


class TestHelperAnnotations(Project):
    def helper(self, env):
        conanfile = SimpleNamespace(
            export_sources_folder=self.dir, recipe_folder=self.dir, base_folder=self.dir, output=mock.Mock()
        )
        with mock.patch.dict(os.environ, env, clear=True):
            return Sanshain(conanfile)

    def test_placeholders_come_from_the_environment(self):
        sanshain = self.helper({"SANSHAIN_SET_AREA": "7", "SANSHAIN_SET_ID": "42"})
        with mock.patch("requests.post", return_value=make_response(202, PROVIDE_OK)) as mock_post:
            sanshain.provide()
        self.assertEqual(
            mock_post.call_args[1]["json"]["annotations"],
            [{"scope": "version", "name": "requirements", "value": "http://solar.system/id-7/r/42"}, SYSTEM],
        )
        ok = make_response(200, text="paths: {}", content=b"paths: {}")
        with mock.patch("requests.get", return_value=ok) as mock_get:
            sanshain.require()
        self.assertEqual(json.loads(mock_get.call_args[1]["params"]["annotations"]), [SYSTEM])
        with mock.patch("requests.put", return_value=make_response(200, {"resources": []})) as mock_put:
            sanshain.catalog()
        self.assertEqual(mock_put.call_args[1]["json"]["annotations"], [SYSTEM])

    def test_an_unfilled_entry_warns_naming_the_variable(self):
        sanshain = self.helper({"SANSHAIN_SET_AREA": "7"})
        sanshain.conanfile.output.warning.assert_called_once_with(
            "Sanshain: annotation 'requirements' left out: {{ID}} is not set (SANSHAIN_SET_ID)"
        )
        self.assertEqual(sanshain.annotations, [SYSTEM])

    def test_strict_raises_when_created(self):
        self.write_config(strict=True)
        with self.assertRaisesRegex(Exception, r"^strict: annotation 'requirements' left out: \{\{AREA\}\}"):
            self.helper({})


if __name__ == "__main__":
    unittest.main()
