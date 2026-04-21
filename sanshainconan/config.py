import os
import yaml

class ConfigError(Exception):
    pass

class SanshainConfig:
    def __init__(self, data):
        self.sanshain_url = data.get("sanshainUrl")
        self.client_name = data.get("clientName")
        self.timeout = data.get("timeout", 30)
        self.compression = data.get("compression", False)
        
        self.provide = data.get("provide")
        self.requires = data.get("requires", [])
        
        self._validate()

    def _validate(self):
        if not self.sanshain_url:
            raise ConfigError("Missing required field: sanshainUrl")
        if not self.client_name:
            raise ConfigError("Missing required field: clientName")
            
        if self.provide:
            if "serviceName" not in self.provide:
                raise ConfigError("Missing required field in provide: serviceName")
            if "openApiFile" not in self.provide:
                raise ConfigError("Missing required field in provide: openApiFile")
        
        for req in self.requires:
            if "serviceName" not in req:
                raise ConfigError("Missing required field in require entry: serviceName")
            if "outputDirectory" not in req:
                raise ConfigError("Missing required field in require entry: outputDirectory")
            if "endpoints" not in req:
                raise ConfigError("Missing required field in require entry: endpoints")

def load_config(path):
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
            if data is None:
                raise ConfigError(f"Config file is empty: {path}")
            return SanshainConfig(data)
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML: {e}")
