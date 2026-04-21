import os
import pytest
import yaml
from sanshainconan.config import load_config, SanshainConfig, ConfigError

def test_load_config_valid(tmp_path):
    config_file = tmp_path / "sanshain.yaml"
    data = {
        "sanshainUrl": "http://localhost:8080",
        "clientName": "test-client",
        "provide": {
            "serviceName": "test-service",
            "openApiFile": "api.yaml"
        },
        "requires": [
            {
                "serviceName": "other-service",
                "outputDirectory": "gen",
                "endpoints": [{"path": "/foo", "method": "GET"}]
            }
        ]
    }
    config_file.write_text(yaml.dump(data))
    
    config = load_config(str(config_file))
    assert config.sanshain_url == "http://localhost:8080"
    assert config.client_name == "test-client"
    assert config.provide["serviceName"] == "test-service"
    assert len(config.requires) == 1

def test_load_config_missing_required(tmp_path):
    config_file = tmp_path / "sanshain.yaml"
    data = {"sanshainUrl": "http://localhost:8080"} # missing clientName
    config_file.write_text(yaml.dump(data))
    
    with pytest.raises(ConfigError, match="Missing required field: clientName"):
        load_config(str(config_file))

def test_load_config_not_found():
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config("nonexistent.yaml")
