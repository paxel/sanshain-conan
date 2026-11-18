"""`require` writes the server's answer byte for byte."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest import mock

import yaml

from sanshainconan.cli import main
from sanshainconan.integration import Sanshain

# CRLF, a UTF-8 umlaut and a trailing line without newline. `text` is how
# requests decodes a text/* answer without a charset (ISO-8859-1), so writing
# it would garble the umlaut; and text mode would rewrite "\n" on Windows.
BODY = "openapi: 3.0.3\r\ninfo:\n  title: Grüße\n  version: 1.0.0".encode()


def answer() -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = 200
    resp.content = BODY
    resp.text = BODY.decode("latin-1")
    resp.headers = {}
    return resp


class TestRequireBytes(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.folder)
        self.config_file = os.path.join(self.folder, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(
                {
                    "sanshainUrl": "http://localhost:8080",
                    "serviceName": "svc",
                    "requires": [
                        {
                            "serviceName": "other",
                            "version": "1.0.0",
                            "outputDirectory": "gen",
                            "endpoints": [{"method": "GET", "path": "/x"}],
                        }
                    ],
                },
                f,
            )
        self.output = os.path.join(self.folder, "gen", "other.yaml")

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        shutil.rmtree(self.folder)

    def written(self) -> bytes:
        with open(self.output, "rb") as f:
            return f.read()

    @mock.patch("requests.get")
    def test_cli_writes_the_bytes(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = answer()
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sys.argv", ["sanshain-conan", "--config", self.config_file, "require"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    main()
        self.assertEqual(self.written(), BODY)

    @mock.patch("requests.get")
    def test_helper_writes_the_bytes(self, mock_get: mock.MagicMock) -> None:
        mock_get.return_value = answer()
        conanfile = SimpleNamespace(
            export_sources_folder=self.folder,
            recipe_folder=self.folder,
            source_folder=self.folder,
            output=mock.Mock(),
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            Sanshain(conanfile).require()
        self.assertEqual(self.written(), BODY)

    def test_the_output_is_opened_in_binary_mode(self) -> None:
        # Text mode would translate newlines on Windows; binary mode never does.
        real_open = open
        modes = []

        def spy(path: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if str(path) == self.output:
                modes.append(mode)
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("requests.get", return_value=answer()):
            with mock.patch("builtins.open", side_effect=spy):
                with mock.patch.dict(os.environ, {}, clear=True):
                    with mock.patch("sys.argv", ["sanshain-conan", "--config", self.config_file, "require"]):
                        with contextlib.redirect_stdout(io.StringIO()):
                            main()
        self.assertEqual(modes, ["wb"])


if __name__ == "__main__":
    unittest.main()
