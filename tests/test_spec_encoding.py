"""Spec files are read as UTF-8 whatever the locale, with a UTF-8 BOM stripped."""

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

SPEC = "openapi: 3.0.3\ninfo:\n  title: Grüße\n  version: 1.2.0\n"


class TestSpecEncoding(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.config_file = os.path.join(self.folder, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump({"sanshainUrl": "http://x", "serviceName": "svc", "provide": {"file": "api.yaml"}}, f)

    def tearDown(self):
        shutil.rmtree(self.folder)

    def write_spec(self, data):
        with open(os.path.join(self.folder, "api.yaml"), "wb") as f:
            f.write(data)

    def provide_cli(self):
        client = mock.Mock()
        client.provide.return_value = {}
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
                with mock.patch("sys.argv", ["sanshain-conan", "--config", self.config_file, "provide"]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        main()
        return client.provide.call_args[0][1]

    def provide_helper(self):
        conanfile = SimpleNamespace(
            export_sources_folder=self.folder, recipe_folder=self.folder, base_folder=self.folder, output=mock.Mock()
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(conanfile)
        sanshain.client = mock.Mock()
        sanshain.client.provide.return_value = {}
        sanshain.provide()
        return sanshain.client.provide.call_args[0][1]

    def test_a_bom_is_stripped(self):
        self.write_spec(b"\xef\xbb\xbf" + SPEC.encode("utf-8"))
        self.assertEqual(self.provide_cli(), SPEC)
        self.assertEqual(self.provide_helper(), SPEC)

    def test_spec_files_are_opened_as_utf8(self):
        # Explicit, so the locale encoding (e.g. cp1252 on Windows) never applies.
        self.write_spec(SPEC.encode("utf-8"))
        real_open = open
        encodings = []
        spec_path = os.path.join(self.folder, "api.yaml")

        def spy(path, mode="r", *args, **kwargs):
            if str(path) == spec_path:
                encodings.append(kwargs.get("encoding"))
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=spy):
            self.provide_cli()
            self.provide_helper()
        self.assertEqual(encodings, ["utf-8-sig", "utf-8-sig"])


if __name__ == "__main__":
    unittest.main()
