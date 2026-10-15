"""The catalog command: PUT /catalog/<serviceName> with the catalogInfo file."""

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

from sanshainconan.cli import main
from sanshainconan.client import SanshainClient, SanshainError
from sanshainconan.config import ConfigError
from sanshainconan.integration import Sanshain

CATALOG = "apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata:\n  name: orders-service\n"


def make_response(status_code=200, json_data=None, text=""):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


def recorded(trunk=False, resources=("resource:default/orders-db", "resource:default/orders-bucket")):
    return make_response(200, {"system": "orders-service", "trunk": trunk, "resources": list(resources)})


class TestPushCatalog(unittest.TestCase):
    @mock.patch("requests.put")
    def test_trunk_sends_trunk_and_plain_omits_it(self, mock_put):
        mock_put.return_value = recorded()
        client = SanshainClient("http://localhost:8080", token="t")  # nosec B106

        client.push_catalog("orders-service", CATALOG, trunk=True)
        args, kwargs = mock_put.call_args
        self.assertEqual(args[0], "http://localhost:8080/catalog/orders-service")
        self.assertEqual(kwargs["json"], {"catalog_info_yaml": CATALOG, "trunk": True})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer t")
        self.assertEqual(kwargs["timeout"], 30)

        client.push_catalog("orders-service", CATALOG)
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG})

    @mock.patch("requests.put")
    def test_the_name_is_url_encoded(self, mock_put):
        mock_put.return_value = recorded()
        SanshainClient("http://localhost:8080/").push_catalog("a b/c", CATALOG)
        self.assertEqual(mock_put.call_args[0][0], "http://localhost:8080/catalog/a%20b%2Fc")

    @mock.patch("requests.put")
    def test_insecure_is_honoured(self, mock_put):
        mock_put.return_value = recorded()
        SanshainClient("https://x", insecure=True).push_catalog("s", CATALOG)
        self.assertFalse(mock_put.call_args[1]["verify"])

    @mock.patch("requests.get")
    @mock.patch("requests.put")
    def test_404_needs_service_2_4(self, mock_put, mock_get):
        mock_put.return_value = make_response(404, text="Not Found")
        mock_get.return_value = make_response(200, {"version": "2.3.1"})
        with self.assertRaises(SanshainError) as ctx:
            SanshainClient("http://x").push_catalog("s", CATALOG)
        self.assertEqual(str(ctx.exception), "sanshain catalog needs Sanshain Service 2.4.0 or later (server is 2.3.1)")

    @mock.patch("requests.get")
    @mock.patch("requests.put")
    def test_404_with_unknown_server_version(self, mock_put, mock_get):
        mock_put.return_value = make_response(404, text="Not Found")
        mock_get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(SanshainError) as ctx:
            SanshainClient("http://x").push_catalog("s", CATALOG)
        self.assertEqual(
            str(ctx.exception), "sanshain catalog needs Sanshain Service 2.4.0 or later (server version unknown)"
        )

    @mock.patch("requests.get")
    @mock.patch("requests.put")
    def test_other_failures_use_the_normal_mapping(self, mock_put, mock_get):
        mock_get.return_value = make_response(200, {"version": "2.4.0"})
        mock_put.return_value = make_response(422, text="unknown field `tag`")
        with self.assertRaisesRegex(SanshainError, r"Invalid request shape \(422\)"):
            SanshainClient("http://x").push_catalog("s", CATALOG)
        mock_put.return_value = make_response(500, text="boom")
        with self.assertRaisesRegex(SanshainError, "status 500"):
            SanshainClient("http://x").push_catalog("s", CATALOG)


class CatalogProject(unittest.TestCase):
    def setUp(self):
        # The config lives in its own folder; the process runs elsewhere.
        self.config_dir = tempfile.mkdtemp()
        self.work_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.work_dir)
        os.makedirs(os.path.join(self.config_dir, "meta"))
        with open(os.path.join(self.config_dir, "meta", "catalog-info.yaml"), "w") as f:
            f.write(CATALOG)
        self.config_file = self.write_config(catalogInfo="meta/catalog-info.yaml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.config_dir)
        shutil.rmtree(self.work_dir)

    def write_config(self, **extra):
        path = os.path.join(self.config_dir, "sanshain.yaml")
        with open(path, "w") as f:
            yaml.dump({"sanshainUrl": "http://localhost:8080", "serviceName": "orders-service", **extra}, f)
        return path


class TestCliCatalog(CatalogProject):
    def run_cli(self, *extra, env=None, put=None, get=None):
        argv = ["sanshain-conan", "--config", self.config_file, *extra, "catalog"]
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}, clear=True):
            with mock.patch("requests.put", return_value=put or recorded()) as mock_put:
                with mock.patch("requests.get", return_value=get or make_response(200, {"version": "2.4.0"})):
                    with mock.patch("sys.argv", argv):
                        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                            try:
                                main()
                            except SystemExit as e:
                                code = e.code
        return code, out.getvalue(), mock_put

    def test_trunk_build_sends_trunk(self):
        code, out, mock_put = self.run_cli(env={"SANSHAIN_TRUNK": "true"}, put=recorded(trunk=True))
        self.assertEqual(code, 0)
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG, "trunk": True})
        self.assertIn("Catalog recorded for orders-service (main+dev): 2 resources", out)

    def test_plain_build_omits_trunk(self):
        _, _, mock_put = self.run_cli()
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG})

    def test_tag_build_sends_neither_trunk_nor_tag(self):
        _, _, mock_put = self.run_cli("--tag", "release-1")
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG})
        _, _, mock_put = self.run_cli(env={"SANSHAIN_TAG": "release-1"})
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG})

    def test_200_prints_the_resources(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(
            out,
            "Catalog recorded for orders-service (dev): 2 resources\n"
            "  resource:default/orders-db\n"
            "  resource:default/orders-bucket\n",
        )

    def test_relative_catalog_info_resolves_next_to_the_config(self):
        _, _, mock_put = self.run_cli()
        self.assertEqual(mock_put.call_args[1]["json"]["catalog_info_yaml"], CATALOG)
        self.assertNotEqual(os.getcwd(), self.config_dir)

    def test_404_needs_2_4(self):
        code, out, _ = self.run_cli(
            put=make_response(404, text="Not Found"), get=make_response(200, {"version": "2.3.0"})
        )
        self.assertEqual(code, 1)
        self.assertIn("sanshain catalog needs Sanshain Service 2.4.0 or later (server is 2.3.0)", out)

    def test_no_catalog_info_warns_and_skips(self):
        self.write_config()
        code, out, mock_put = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(out, "No catalogInfo in sanshain.yaml - skipping catalog.\n")
        mock_put.assert_not_called()

    def test_no_catalog_info_under_strict_fails(self):
        self.write_config(strict=True)
        for extra in ((), ("--best-effort",)):
            with self.subTest(extra=extra):
                code, out, mock_put = self.run_cli(*extra)
                self.assertEqual(code, 1)
                self.assertIn("strict: sanshain.yaml has no catalogInfo", out)
                mock_put.assert_not_called()

    def test_strict_does_not_require_provides_or_requires(self):
        self.write_config(strict=True, catalogInfo="meta/catalog-info.yaml")
        code, _, mock_put = self.run_cli()
        self.assertEqual(code, 0)
        mock_put.assert_called_once()

    def test_missing_file_fails_naming_the_resolved_path(self):
        self.write_config(catalogInfo="nope.yaml")
        resolved = os.path.join(self.config_dir, "nope.yaml")
        code, out, mock_put = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn(resolved, out)
        mock_put.assert_not_called()

        code, out, _ = self.run_cli("--best-effort")
        self.assertEqual(code, 0)
        self.assertIn(resolved, out)


class TestHelperCatalog(CatalogProject):
    def helper(self, env=None):
        conanfile = SimpleNamespace(
            export_sources_folder=self.work_dir,
            recipe_folder=self.work_dir,
            base_folder=self.work_dir,
            output=mock.Mock(),
        )
        with mock.patch.dict(os.environ, env or {}, clear=True):
            return Sanshain(conanfile, config_path=self.config_file)

    @mock.patch("requests.put")
    def test_pushes_and_reports(self, mock_put):
        mock_put.return_value = recorded(trunk=True)
        sanshain = self.helper(env={"SANSHAIN_TRUNK": "1"})
        sanshain.catalog()
        self.assertEqual(mock_put.call_args[1]["json"], {"catalog_info_yaml": CATALOG, "trunk": True})
        infos = [c.args[0] for c in sanshain.conanfile.output.info.call_args_list]
        self.assertEqual(
            infos,
            [
                "Catalog recorded for orders-service (main+dev): 2 resources",
                "  resource:default/orders-db",
                "  resource:default/orders-bucket",
            ],
        )

    @mock.patch("requests.put")
    def test_no_catalog_info_warns(self, mock_put):
        self.write_config()
        sanshain = self.helper()
        sanshain.catalog()
        sanshain.conanfile.output.warning.assert_called_once_with("No catalogInfo in sanshain.yaml - skipping catalog.")
        mock_put.assert_not_called()

    def test_no_catalog_info_under_strict_raises(self):
        self.write_config(strict=True)
        with self.assertRaisesRegex(ConfigError, "strict: sanshain.yaml has no catalogInfo"):
            self.helper().catalog()


if __name__ == "__main__":
    unittest.main()
