import os
import yaml

class ConfigError(Exception):
    pass

class SanshainConfig:
    def __init__(self, data):
        self.sanshain_url = data.get("sanshainUrl")
        self.service_name = data.get("serviceName", data.get("clientName"))
        self.client_name = self.service_name # alias
        self.timeout = data.get("timeout", 30)
        self.compression = data.get("compression", False)
        self.best_effort = data.get("bestEffort", False)
        self.strict = data.get("strict", False)
        
        self.provide = data.get("provide")
        self.provides = data.get("provides", [])
        self.requires = data.get("requires", [])
        
        self._validate()

    def _validate(self):
        if not self.sanshain_url:
            raise ConfigError("Missing required field: sanshainUrl")
            
        def validate_provide(p, context):
            if not any(k in p for k in ["file", "openApiFile", "asyncApiFile", "protoFile"]):
                raise ConfigError(f"At least one of file, openApiFile, asyncApiFile, or protoFile must be specified in {context}")

        if self.provide:
            validate_provide(self.provide, "provide")
        
        for i, p in enumerate(self.provides):
            validate_provide(p, f"provides[{i}]")
        
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
