"""Best effort softens failed calls only, per entry; a broken sanshain.yaml and strict always fail."""

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

    def test_a_broken_config_fails_also_with_best_effort(self):
        base = "sanshainUrl: http://localhost:3000\nserviceName: svc\n"
        cases = {
            "unreadable": None,
            "invalid": base + "requires:\n  - serviceName: users\n    outputDirectory: gen\n    endpoints: []\n",
            "1.x field": base + "releaseBranches: [main]\n",
            "unsupported apiType": base + "provides:\n  - file: openapi.yaml\n    apiType: raml\n",
            "bestEffort in the file": base + "bestEffort: true\nprovides:\n  - file: openapi.yaml\n    apiType: raml\n",
        }
        for name, text in cases.items():
            for command in ("provide", "require", "catalog"):
                with self.subTest(case=name, command=command):
                    if text is None:
                        if os.path.exists(self.config_file):
                            os.remove(self.config_file)
                    else:
                        self.write(text)
                    code, out, client_cls = self.run_cli("--best-effort", command, env={"SANSHAIN_BEST_EFFORT": "true"})
                    self.assertEqual(code, 1)
                    self.assertIn("Error: ", out)
                    self.assertNotIn("Continuing (best effort)", out)
                    client_cls.assert_not_called()

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
