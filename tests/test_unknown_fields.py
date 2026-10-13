"""The puzzled cat: unknown sanshain.yaml fields are reported, and rejected under strict."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from sanshainconan.cli import main
from sanshainconan.config import ConfigError, find_unknown_fields, load_config, puzzled_cat
from sanshainconan.integration import Sanshain

BASE = """sanshainUrl: http://localhost:8080
serviceName: svc
"""

REQUIRES = """requires:
  - serviceName: a
    version: 1.0.0
    outputDirectory: gen
    endpoints:
      - method: GET
        path: /a
"""


def cat(text):
    return f"   /\\_/\\  ?\n  ( O_o )   {text}\n ---U-U---\n"


class TestFindUnknownFields(unittest.TestCase):
    def test_paths_at_every_level_in_file_order(self):
        data = {
            "sanshainUrl": "x",
            "catalogInf": "c.yaml",
            "provide": {"fiel": "a.yaml"},
            "provides": [{"file": "a.yaml"}, {"file": "b.yaml", "verison": "1"}],
            "requires": [
                {
                    "outputDirectroy": "gen",
                    "endpoints": [{"method": "GET"}, {"path": "/x"}, {"methd": "GET"}],
                }
            ],
            "zzz": 1,
        }
        self.assertEqual(
            find_unknown_fields(data),
            [
                "catalogInf",
                "provide.fiel",
                "provides[1].verison",
                "requires[0].outputDirectroy",
                "requires[0].endpoints[2].methd",
                "zzz",
            ],
        )

    def test_known_but_unsupported_fields_are_not_unknown(self):
        data = {
            "sanshainUrl": "x",
            "clientName": "c",
            "compression": True,
            "bestEffort": False,
            "strict": False,
            "force": True,
            "insecure": True,
            "combine": True,
            "catalogInfo": "catalog-info.yaml",
            "provide": {"file": "a", "apiType": "openapi", "combine": True, "retired": False},
            "provides": [{"openApiFile": "a", "asyncApiFile": "b", "protoFile": "c"}],
            "requires": [
                {
                    "serviceName": "s",
                    "apiType": "openapi",
                    "version": "1.0.0",
                    "outputDirectory": "g",
                    "endpoints": [{"method": "GET", "path": "/"}],
                }
            ],
        }
        self.assertEqual(find_unknown_fields(data), [])

    def test_the_cat_is_exact(self):
        self.assertEqual(
            "\n".join(puzzled_cat(["catalogInf"], False)) + "\n",
            cat("sanshain.yaml: unknown field 'catalogInf' - ignored"),
        )
        self.assertEqual(
            puzzled_cat(["catalogInf", "requires[0].verison"], True)[1],
            "  ( O_o )   sanshain.yaml: unknown fields 'catalogInf', 'requires[0].verison' - rejected (strict)",
        )


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.config_file = os.path.join(self.folder, "sanshain.yaml")

    def tearDown(self):
        shutil.rmtree(self.folder)

    def write(self, text):
        with open(self.config_file, "w") as f:
            f.write(text)

    def run_cli(self, *extra, env=None):
        argv = ["sanshain-conan", "--config", self.config_file, *extra, "require"]
        out, err = io.StringIO(), io.StringIO()
        code = 0
        cwd = os.getcwd()
        os.chdir(self.folder)
        try:
            with mock.patch.dict(os.environ, env or {}, clear=True):
                with mock.patch("sanshainconan.cli.SanshainClient") as client_cls:
                    client_cls.return_value.require.return_value = {"not_modified": True}
                    with mock.patch("sys.argv", argv):
                        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            try:
                                main()
                            except SystemExit as e:
                                code = e.code
        finally:
            os.chdir(cwd)
        return code, out.getvalue(), err.getvalue(), client_cls


class TestCliCat(CliTestCase):
    def test_single_unknown_field_prints_the_cat_once_and_continues(self):
        self.write(BASE + "catalogInf: catalog-info.yaml\n" + REQUIRES)
        code, out, err, client_cls = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(err, cat("sanshain.yaml: unknown field 'catalogInf' - ignored"))
        self.assertNotIn("O_o", out)
        client_cls.return_value.require.assert_called_once()

    def test_several_unknown_fields_in_file_order(self):
        self.write(BASE + "catalogInf: c.yaml\n" + REQUIRES.replace("version:", "verison: 1.0.0\n    version:"))
        code, _, err, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(err, cat("sanshain.yaml: unknown fields 'catalogInf', 'requires[0].verison' - ignored"))

    def test_nested_endpoint_path(self):
        self.write(BASE + REQUIRES + "      - methd: GET\n")
        _, _, err, _ = self.run_cli()
        self.assertIn("unknown field 'requires[0].endpoints[1].methd' - ignored", err)

    def test_strict_rejects_even_with_best_effort(self):
        self.write(BASE + "strict: true\ncatalogInf: c.yaml\n" + REQUIRES)
        for extra, env in (((), {}), (("--best-effort",), {"SANSHAIN_BEST_EFFORT": "true"})):
            with self.subTest(extra=extra):
                code, _, err, client_cls = self.run_cli(*extra, env=env)
                self.assertEqual(code, 1)
                self.assertEqual(err, cat("sanshain.yaml: unknown field 'catalogInf' - rejected (strict)"))
                client_cls.return_value.require.assert_not_called()

    def test_legacy_field_still_errors_without_a_cat(self):
        self.write(BASE + "timeout: 30\ncatalogInf: c.yaml\n" + REQUIRES)
        with self.assertRaisesRegex(ConfigError, "'timeout' is no longer supported"):
            load_config(self.config_file)
        # The CLI fails on it (its own error path), and no cat is shown first.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises((SystemExit, Exception)):
                with mock.patch("sys.argv", ["sanshain-conan", "--config", self.config_file, "require"]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()
        self.assertNotIn("O_o", err.getvalue())

    def test_known_but_unsupported_field_gives_no_cat(self):
        self.write(BASE + "insecure: true\nforce: true\ncombine: true\n" + REQUIRES)
        code, out, err, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertNotIn("O_o", err + out)


class TestHelperCat(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.conanfile = SimpleNamespace(
            export_sources_folder=self.folder, recipe_folder=self.folder, base_folder=self.folder, output=mock.Mock()
        )

    def tearDown(self):
        shutil.rmtree(self.folder)

    def write(self, text):
        with open(os.path.join(self.folder, "sanshain.yaml"), "w") as f:
            f.write(text)

    def warnings(self):
        return [c.args[0] for c in self.conanfile.output.warning.call_args_list]

    def test_warns_with_the_cat_line_by_line(self):
        self.write(BASE + "provide:\n  fiel: a.yaml\n  file: a.yaml\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            Sanshain(self.conanfile)
        self.assertEqual(
            self.warnings(),
            puzzled_cat(["provide.fiel"], False),
        )

    def test_strict_raises_after_the_cat(self):
        self.write(BASE + "strict: true\nprovides:\n  - file: a.yaml\n  - file: b.yaml\n    verison: 1\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                Sanshain(self.conanfile)
        self.assertEqual(str(ctx.exception), "sanshain.yaml: unknown field 'provides[1].verison' - rejected (strict)")
        self.assertEqual(self.warnings(), puzzled_cat(["provides[1].verison"], True))

    def test_legacy_field_still_errors_without_a_cat(self):
        self.write(BASE + "releaseBranches: [main]\ncatalogInf: c.yaml\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigError, "'releaseBranches' is no longer supported"):
                Sanshain(self.conanfile)
        self.conanfile.output.warning.assert_not_called()

    def test_known_fields_give_no_cat(self):
        self.write(BASE + "insecure: true\ncatalogInfo: catalog-info.yaml\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config(os.path.join(self.folder, "sanshain.yaml"))
            Sanshain(self.conanfile)
        self.assertEqual(config.unknown_fields, [])
        self.conanfile.output.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
