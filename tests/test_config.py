import os
import unittest
import yaml
import tempfile
import shutil
from sanshainconan.config import load_config, ConfigError


class TestSanshainConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def _write(self, data):
        config_file = os.path.join(self.test_dir, "sanshain.yaml")
        with open(config_file, "w") as f:
            yaml.dump(data, f)
        return config_file

    def _valid_data(self):
        return {
            "sanshainUrl": "http://localhost:8080",
            "serviceName": "test-service",
            "provide": {"file": "api.yaml"},
            "requires": [
                {
                    "serviceName": "other-service",
                    "version": "1.2.0",
                    "outputDirectory": "gen",
                    "endpoints": [{"path": "/foo", "method": "GET"}],
                }
            ],
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_config_valid(self):
        config_file = self._write(self._valid_data())

        config = load_config(config_file)
        self.assertEqual(config.sanshain_url, "http://localhost:8080")
        self.assertEqual(config.service_name, "test-service")
        self.assertEqual(config.provide["file"], "api.yaml")
        self.assertEqual(len(config.requires), 1)
        self.assertEqual(config.requires[0]["version"], "1.2.0")

    def test_load_config_missing_required(self):
        config_file = self._write({"serviceName": "x"})  # missing sanshainUrl

        with self.assertRaisesRegex(ConfigError, "Missing required field: sanshainUrl"):
            load_config(config_file)

    def test_load_config_not_found(self):
        with self.assertRaisesRegex(ConfigError, "Config file not found"):
            load_config("nonexistent.yaml")

    def test_require_missing_version_names_entry_and_hints_migration(self):
        data = self._valid_data()
        del data["requires"][0]["version"]
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("requires[0] (other-service): missing 'version'", msg)
        self.assertIn("Sanshain 2.0 pins exact versions", msg)
        self.assertIn("GET /producers/other-service/versions", msg)

    def test_require_branch_is_rejected_by_name(self):
        data = self._valid_data()
        data["requires"][0]["branch"] = "main"
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("requires[0] (other-service)", msg)
        self.assertIn("'branch' is no longer supported", msg)
        self.assertIn("branch model was removed in Sanshain 2.0", msg)
        self.assertIn("'version' pin", msg)

    def test_require_timeout_is_rejected_by_name(self):
        data = self._valid_data()
        data["requires"][0]["timeout"] = 60
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("requires[0] (other-service): 'timeout' is no longer supported", msg)
        self.assertIn("no long-polling", msg)

    def test_top_level_timeout_is_rejected_by_name(self):
        data = self._valid_data()
        data["timeout"] = 30
        config_file = self._write(data)

        with self.assertRaisesRegex(ConfigError, r"sanshain\.yaml: 'timeout' is no longer supported"):
            load_config(config_file)

    def test_provide_branch_is_rejected_with_spec_file_hint(self):
        data = self._valid_data()
        data["provide"]["branch"] = "release/1.x"
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("provide: 'branch' is no longer supported", msg)
        self.assertIn("info.version", msg)
        self.assertIn("sanshain-version", msg)

    def test_provide_base_version_is_rejected_by_name(self):
        data = self._valid_data()
        data["provides"] = [{"file": "api.yaml", "baseVersion": 5}]
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("provides[0]: 'baseVersion' is no longer supported", msg)
        self.assertIn("GA immutability", msg)

    def test_release_branches_is_rejected_by_name(self):
        data = self._valid_data()
        data["releaseBranches"] = ["main", "release/*"]
        config_file = self._write(data)

        with self.assertRaises(ConfigError) as ctx:
            load_config(config_file)

        msg = str(ctx.exception)
        self.assertIn("'releaseBranches' is no longer supported", msg)
        self.assertIn("SANSHAIN_GA=true", msg)
