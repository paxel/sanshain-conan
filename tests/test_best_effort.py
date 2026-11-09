"""Best effort softens failed calls, per entry, and a missing or broken sanshain.yaml when it comes
from the flag or SANSHAIN_BEST_EFFORT; strict and the conanfile helper's broken file always fail."""

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
from sanshainconan.client import SanshainError
from sanshainconan.config import ConfigError
from sanshainconan.integration import Sanshain

OK = {"version": "1.0.0", "stability": "snapshot", "changes": {}}
TWO_PROVIDES = {
    "sanshainUrl": "http://localhost:3000",
    "serviceName": "svc",
    "provides": [{"file": "openapi.yaml"}, {"file": "asyncapi.yaml", "apiType": "asyncapi"}],
}
REQUIRE_WITHOUT_VERSION = "requires:\n  - serviceName: users\n    outputDirectory: gen\n    endpoints: []\n"
_BASE = "sanshainUrl: http://localhost:3000\nserviceName: svc\n"
# case: (how the file is placed, its content, the message it fails with)
BROKEN = {
    "missing": ("none", None, "Config file not found: {path}"),
    "a directory": ("dir", None, "Cannot read config file {path}: Is a directory"),
    "not UTF-8": ("bytes", b"sanshainUrl: \xff\n", "Cannot read config file {path}: 'utf-8' codec can't decode"),
    "invalid YAML": ("text", "sanshainUrl: [unclosed\n", "Failed to parse YAML: "),
    "no mapping": ("text", "- sanshainUrl\n", "{path} must be a mapping of settings"),
    "1.x field": ("text", _BASE + "releaseBranches: [main]\n", "sanshain.yaml: 'releaseBranches' is no longer"),
    "invalid entry": ("text", _BASE + REQUIRE_WITHOUT_VERSION, "requires[0] (users): missing 'version'"),
    "unsupported apiType": (
        "text",
        _BASE + "provides:\n  - file: openapi.yaml\n    apiType: raml\n",
        "provides[0]: unsupported apiType 'raml'",
    ),
}


class BestEffortTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.cwd = os.getcwd()
        os.chdir(self.folder)  # keep the .sanshain-cache inside the temp dir
        self.addCleanup(os.chdir, self.cwd)
        self.config_file = os.path.join(self.folder, "sanshain.yaml")
        for name in ("openapi.yaml", "asyncapi.yaml"):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write("info:\n  version: 1.0.0\n")

    def write(self, data):
        with open(self.config_file, "w") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                yaml.dump(data, f)

    def place(self, case):
        """Put the sanshain.yaml of a BROKEN case in place; the message it fails with."""
        if os.path.isdir(self.config_file):
            os.rmdir(self.config_file)
        elif os.path.exists(self.config_file):
            os.remove(self.config_file)
        kind, content, message = BROKEN[case]
        if kind == "dir":
            os.mkdir(self.config_file)
        elif kind == "bytes":
            with open(self.config_file, "wb") as f:
                f.write(content)
        elif kind == "text":
            self.write(content)
        return message.format(path=self.config_file)

    def failing_client(self):
        client = mock.Mock()
        client.provide.side_effect = SanshainError("Request failed with status 500: boom")
        client.provide_asyncapi.return_value = OK
        client.require.side_effect = [
            SanshainError("Request failed with status 500: boom"),
            {"not_modified": False, "content": "paths: {}", "body": b"paths: {}", "etag": None},
        ]
        return client

    def run_cli(self, *argv, client=None, env=None):
        client = client or mock.Mock()
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client) as client_cls:
                with mock.patch("sys.argv", ["sanshainconan", "--config", self.config_file, *argv]):
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                        try:
                            main()
                        except SystemExit as e:
                            code = e.code
        return code, out.getvalue(), client_cls


class TestCli(BestEffortTestCase):
    def test_a_failed_provide_warns_and_the_next_entry_is_provided(self):
        self.write(TWO_PROVIDES)
        code, out, _ = self.run_cli("--best-effort", "provide", client=(client := self.failing_client()))
        self.assertEqual(code, 0)
        self.assertIn("Error: Request failed with status 500: boom\nContinuing (best effort)", out)
        client.provide_asyncapi.assert_called_once()
        self.assertIn("✓ Provided 1.0.0 (snapshot)", out)

        code, _, _ = self.run_cli("provide", client=(client := self.failing_client()))
        self.assertEqual(code, 1)
        client.provide_asyncapi.assert_not_called()

    def test_a_failed_require_warns_and_the_next_entry_is_written(self):
        entry = {"version": "1.0.0", "outputDirectory": "gen", "endpoints": [{"method": "GET", "path": "/x"}]}
        self.write(
            {
                "sanshainUrl": "http://localhost:3000",
                "serviceName": "svc",
                "requires": [{"serviceName": "ghost", **entry}, {"serviceName": "users", **entry}],
            }
        )
        code, out, _ = self.run_cli("--best-effort", "require", client=self.failing_client())
        self.assertEqual(code, 0)
        self.assertIn("Error requiring ghost: Request failed with status 500: boom", out)
        with open(os.path.join(self.folder, "gen", "users.yaml"), "rb") as f:
            self.assertEqual(f.read(), b"paths: {}")

    def test_a_missing_or_broken_config_fails_without_best_effort(self):
        for case in BROKEN:
            for command in ("provide", "require", "catalog"):
                with self.subTest(case=case, command=command):
                    message = self.place(case)
                    code, out, client_cls = self.run_cli(command)
                    self.assertEqual(code, 1)
                    self.assertIn(f"Error: {message}", out)
                    self.assertNotIn("Continuing (best effort)", out)
                    client_cls.assert_not_called()

    def test_best_effort_from_the_flag_or_the_variable_turns_a_missing_or_broken_config_into_a_warning(self):
        switches = {
            "flag": (("--best-effort",), {}),
            "variable true": ((), {"SANSHAIN_BEST_EFFORT": "true"}),
            "variable 1": ((), {"SANSHAIN_BEST_EFFORT": "1"}),
        }
        for case in BROKEN:
            for command in ("provide", "require", "catalog"):
                for switch, (flags, env) in switches.items():
                    with self.subTest(case=case, command=command, switch=switch):
                        message = self.place(case)
                        code, out, client_cls = self.run_cli(*flags, command, env=env)
                        self.assertEqual(code, 0)
                        self.assertTrue(out.startswith(f"Error: {message}"), out)
                        self.assertTrue(out.endswith("\nContinuing (best effort)\n"), out)
                        client_cls.assert_not_called()

    def test_the_broken_files_own_best_effort_does_not_count(self):
        base = "sanshainUrl: http://localhost:3000\nserviceName: svc\nbestEffort: true\n"
        cases = {
            "1.x field": base + "releaseBranches: [main]\n",
            "invalid entry": base + REQUIRE_WITHOUT_VERSION,
            "unsupported apiType": base + "provides:\n  - file: openapi.yaml\n    apiType: raml\n",
        }
        for name, text in cases.items():
            for command in ("provide", "require", "catalog"):
                with self.subTest(case=name, command=command):
                    self.write(text)
                    code, out, client_cls = self.run_cli(command, env={"SANSHAIN_BEST_EFFORT": "false"})
                    self.assertEqual(code, 1)
                    self.assertIn("Error: ", out)
                    self.assertNotIn("Continuing (best effort)", out)
                    client_cls.assert_not_called()

    def test_the_broken_files_own_strict_does_not_count(self):
        base = "sanshainUrl: http://localhost:3000\nserviceName: svc\nstrict: true\n"
        for text in (base + "releaseBranches: [main]\n", base + REQUIRE_WITHOUT_VERSION):
            with self.subTest(text=text):
                self.write(text)
                code, out, client_cls = self.run_cli("--best-effort", "require")
                self.assertEqual(code, 0)
                self.assertIn("Continuing (best effort)", out)
                client_cls.assert_not_called()

    def test_the_best_effort_help_names_a_missing_or_broken_config(self):
        out = io.StringIO()
        with mock.patch("sys.argv", ["sanshainconan", "--help"]), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit):
                main()
        help_text = " ".join(out.getvalue().split())
        self.assertIn(
            "--best-effort turn failed calls, and a missing or broken sanshain.yaml, into warnings and exit 0 "
            "(also SANSHAIN_BEST_EFFORT=true or 1; bestEffort: true in sanshain.yaml counts for failed calls only)",
            help_text,
        )

    def test_missing_configuration_under_strict_fails_also_with_best_effort(self):
        cases = [
            ("provide", {"strict": True}, "serviceName is required"),
            ("require", {"strict": True}, "serviceName is required"),
            ("catalog", {"strict": True}, "serviceName is required"),
            ("provide", {"strict": True, "serviceName": "svc"}, "No 'provide' section"),
            ("require", {"strict": True, "serviceName": "svc"}, "No requires configured"),
            ("catalog", {"strict": True, "serviceName": "svc"}, "no catalogInfo"),
        ]
        for command, data, message in cases:
            with self.subTest(command=command, data=data):
                self.write({"sanshainUrl": "http://localhost:3000", **data})
                code, out, _ = self.run_cli("--best-effort", command)
                self.assertEqual(code, 1)
                self.assertIn(message, out)


class TestHelper(BestEffortTestCase):
    def helper(self, data):
        self.write(data)
        conanfile = SimpleNamespace(export_sources_folder=self.folder, recipe_folder=self.folder, output=mock.Mock())
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(conanfile)
        sanshain.client = self.failing_client()
        return sanshain

    def test_a_failed_provide_warns_and_the_next_entry_is_provided(self):
        sanshain = self.helper({**TWO_PROVIDES, "bestEffort": True})
        sanshain.provide()
        sanshain.client.provide_asyncapi.assert_called_once()
        output = sanshain.conanfile.output
        output.warning.assert_any_call("Sanshain: Request failed with status 500: boom")
        output.warning.assert_any_call("Sanshain: Continuing (best effort)")
        output.info.assert_any_call("Sanshain: Successfully provided spec(s)")

    def test_without_best_effort_a_failed_provide_raises(self):
        sanshain = self.helper(TWO_PROVIDES)
        with self.assertRaises(SanshainError):
            sanshain.provide()
        sanshain.client.provide_asyncapi.assert_not_called()
        sanshain.conanfile.output.error.assert_called_once_with("Sanshain: Request failed with status 500: boom")

    def test_a_missing_spec_file_is_logged_once_and_raises(self):
        os.remove(os.path.join(self.folder, "openapi.yaml"))
        sanshain = self.helper(TWO_PROVIDES)
        with self.assertRaises(Exception):
            sanshain.provide()
        path = os.path.join(self.folder, "openapi.yaml")
        sanshain.conanfile.output.error.assert_called_once_with(f"Sanshain: File not found: {path}")

    def test_a_missing_or_broken_config_raises_also_with_best_effort(self):
        # The helper has no flag and does not read SANSHAIN_BEST_EFFORT; a
        # broken file's own bestEffort does not count.
        conanfile = SimpleNamespace(export_sources_folder=self.folder, recipe_folder=self.folder, output=mock.Mock())
        for case in BROKEN:
            with self.subTest(case=case):
                message = self.place(case)
                if BROKEN[case][0] == "text" and not BROKEN[case][1].startswith("-"):
                    with open(self.config_file, "a") as f:
                        f.write("bestEffort: true\n")
                with mock.patch.dict(os.environ, {"SANSHAIN_BEST_EFFORT": "true"}, clear=True):
                    with self.assertRaises(ConfigError) as ctx:
                        Sanshain(conanfile)
                self.assertTrue(str(ctx.exception).startswith(message), str(ctx.exception))

    def test_an_unsupported_provide_api_type_raises_also_with_best_effort(self):
        with self.assertRaises(ConfigError) as ctx:
            self.helper(
                {
                    "sanshainUrl": "http://localhost:3000",
                    "serviceName": "svc",
                    "bestEffort": True,
                    "provides": [{"file": "openapi.yaml", "apiType": "raml"}],
                }
            )
        self.assertEqual(
            str(ctx.exception),
            "provides[0]: unsupported apiType 'raml' — use openapi, asyncapi or proto (grpc means proto)",
        )


if __name__ == "__main__":
    unittest.main()
