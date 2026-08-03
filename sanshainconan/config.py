import os

import yaml


class ConfigError(Exception):
    pass


_BRANCH_HINT_REQUIRE = (
    "'branch' is no longer supported — the branch model was removed in Sanshain 2.0; "
    "replace with an exact 'version' pin"
)
_BRANCH_HINT_PROVIDE = (
    "'branch' is no longer supported — the branch model was removed in Sanshain 2.0; "
    "the version is read from the spec file itself (info.version, or a "
    "// sanshain-version: comment for proto)"
)
_TIMEOUT_HINT = "'timeout' is no longer supported — Sanshain 2.0 resolves immediately (no long-polling); remove it"
_BASE_VERSION_HINT = (
    "'baseVersion' is no longer supported — GA immutability replaced optimistic "
    "concurrency in Sanshain 2.0; remove it"
)
_RELEASE_BRANCHES_HINT = (
    "'releaseBranches' is no longer supported — stability is decided by the ga switch "
    "(SANSHAIN_GA=true or --ga) in Sanshain 2.0; remove it"
)


class SanshainConfig:
    def __init__(self, data):
        self.sanshain_url = data.get("sanshainUrl")
        self.service_name = data.get("serviceName", data.get("clientName"))
        self.client_name = self.service_name  # alias
        self.compression = data.get("compression", False)
        self.best_effort = data.get("bestEffort", False)
        self.strict = data.get("strict", False)

        self.provide = data.get("provide")
        self.provides = data.get("provides", [])
        self.requires = data.get("requires", [])

        self._validate(data)

    def _validate(self, data):
        if not self.sanshain_url:
            raise ConfigError("Missing required field: sanshainUrl")

        def reject_branch_era(entry, context, branch_hint):
            if "branch" in entry:
                raise ConfigError(f"{context}: {branch_hint}")
            if "timeout" in entry:
                raise ConfigError(f"{context}: {_TIMEOUT_HINT}")
            if "baseVersion" in entry:
                raise ConfigError(f"{context}: {_BASE_VERSION_HINT}")
            if "releaseBranches" in entry:
                raise ConfigError(f"{context}: {_RELEASE_BRANCHES_HINT}")

        reject_branch_era(data, "sanshain.yaml", _BRANCH_HINT_REQUIRE)

        def validate_provide(p, context):
            reject_branch_era(p, context, _BRANCH_HINT_PROVIDE)
            if not any(k in p for k in ["file", "openApiFile", "asyncApiFile", "protoFile"]):
                raise ConfigError(
                    f"At least one of file, openApiFile, asyncApiFile, or protoFile must be specified in {context}"
                )

        if self.provide:
            validate_provide(self.provide, "provide")

        for i, p in enumerate(self.provides):
            validate_provide(p, f"provides[{i}]")

        for i, req in enumerate(self.requires):
            if "serviceName" not in req:
                raise ConfigError("Missing required field in require entry: serviceName")
            name = req["serviceName"]
            context = f"requires[{i}] ({name})"
            reject_branch_era(req, context, _BRANCH_HINT_REQUIRE)
            if "version" not in req:
                raise ConfigError(
                    f"{context}: missing 'version' — Sanshain 2.0 pins exact versions; "
                    f"add version: MAJOR.MINOR.PATCH "
                    f"(list available: GET /producers/{name}/versions)"
                )
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
