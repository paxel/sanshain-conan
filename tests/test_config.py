import os
import unittest
import yaml
import tempfile
import shutil
from sanshainconan.config import load_config, SanshainConfig, ConfigError


class TestSanshainConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_config_valid(self):
        config_file = os.path.join(self.test_dir, "sanshain.yaml")
        data = {
            "sanshainUrl": "http://localhost:8080",
            "serviceName": "test-service",
            "provide": {"openApiFile": "api.yaml"},
            "requires": [
                {
                    "serviceName": "other-service",
                    "outputDirectory": "gen",
                    "endpoints": [{"path": "/foo", "method": "GET"}],
                }
            ],
        }
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        config = load_config(config_file)
        self.assertEqual(config.sanshain_url, "http://localhost:8080")
        self.assertEqual(config.service_name, "test-service")
        self.assertEqual(config.provide["openApiFile"], "api.yaml")
        self.assertEqual(len(config.requires), 1)

    def test_load_config_missing_required(self):
        config_file = os.path.join(self.test_dir, "sanshain.yaml")
        data = {}  # missing sanshainUrl
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        with self.assertRaisesRegex(ConfigError, "Missing required field: sanshainUrl"):
            load_config(config_file)

    def test_load_config_not_found(self):
        with self.assertRaisesRegex(ConfigError, "Config file not found"):
            load_config("nonexistent.yaml")
