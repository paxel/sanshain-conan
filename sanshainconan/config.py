import os

import yaml


class ConfigError(Exception):
    """sanshain.yaml is unusable. Carries the unknown fields found before the
    failure, so the caller can show the cat ahead of the error."""

    def __init__(self, message, unknown_fields=None, strict=False):
        super().__init__(message)
        self.unknown_fields = unknown_fields or []
        self.strict = strict


def env_flag(name):
    """A SANSHAIN_* boolean switch: trimmed, case-insensitive `true` or `1` is on, anything else off."""
    return (os.environ.get(name) or "").strip().lower() in ("true", "1")


def env_url():
    """SANSHAIN_URL, or None when unset or blank."""
    return (os.environ.get("SANSHAIN_URL") or "").strip() or None


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


# Every field any Sanshain client knows, per level. A field known here but not
# supported by this client is accepted silently; anything else is unknown.
_KNOWN_TOP = {
    "sanshainUrl",
    "serviceName",
    "clientName",
    "compression",
    "bestEffort",
    "strict",
    "force",
    "insecure",
    "combine",
    "catalogInfo",
    "provide",
    "provides",
    "requires",
}
_KNOWN_PROVIDE = {"file", "apiType", "retired", "openApiFile", "asyncApiFile", "protoFile", "combine"}
_KNOWN_REQUIRE = {"serviceName", "apiType", "version", "outputDirectory", "endpoints", "format"}
_KNOWN_ENDPOINT = {"method", "path"}


def find_unknown_fields(data):
    """Paths of the unknown fields in a parsed sanshain.yaml, in file order."""
    found = []

    def check(entry, known, prefix, nested):
        # Depth-first in key order, so the paths come out as they appear in the file.
        if not isinstance(entry, dict):
            return
        for key, value in entry.items():
            if key not in known:
                found.append(f"{prefix}{key}")
            elif key in nested:
                nested[key](value, f"{prefix}{key}")

    def each(known, nested=None):
        def walk(entries, path):
            if isinstance(entries, list):
                for i, entry in enumerate(entries):
                    check(entry, known, f"{path}[{i}].", nested or {})

        return walk

    check(
        data,
        _KNOWN_TOP,
        "",
        {
            "provide": lambda entry, path: check(entry, _KNOWN_PROVIDE, f"{path}.", {}),
            "provides": each(_KNOWN_PROVIDE),
            "requires": each(_KNOWN_REQUIRE, {"endpoints": each(_KNOWN_ENDPOINT)}),
        },
    )
    return found


def unknown_fields_message(fields, strict):
    noun = "field" if len(fields) == 1 else "fields"
    names = ", ".join(f"'{f}'" for f in fields)
    verdict = "rejected (strict)" if strict else "ignored"
    return f"sanshain.yaml: unknown {noun} {names} - {verdict}"


def puzzled_cat(fields, strict):
    """The three lines that report unknown fields, ending in `ignored` or `rejected (strict)`."""
    return [
        "   /\\_/\\  ?",
        f"  ( O_o )   {unknown_fields_message(fields, strict)}",
        " ---U-U---",
    ]


class SanshainConfig:
    def __init__(self, data):
        # SANSHAIN_URL beats the yaml's sanshainUrl: the service address is
        # an environment concern and moves without a commit.
        self.sanshain_url = env_url() or data.get("sanshainUrl")
        self.service_name = data.get("serviceName", data.get("clientName"))
        self.client_name = self.service_name  # alias
        self.compression = data.get("compression", False)
        self.best_effort = data.get("bestEffort", False)
        self.strict = data.get("strict", False)
        self.catalog_info = data.get("catalogInfo")

        self.provide = data.get("provide")
        self.provides = data.get("provides", [])
        self.requires = data.get("requires", [])

        # Order: legacy-field rejections, then unknown fields (the cat; under
        # strict they fail here), then the remaining validation — so a typo
        # that replaces a required field is named before the error it causes.
        self._reject_legacy(data)
        self.unknown_fields = find_unknown_fields(data)
        if self.unknown_fields and self.strict:
            raise ConfigError(unknown_fields_message(self.unknown_fields, True), self.unknown_fields, strict=True)
        try:
            self._validate(data)
        except ConfigError as e:
            e.unknown_fields = self.unknown_fields
            raise

    @staticmethod
    def _reject_legacy(data):
        def reject_branch_era(entry, context, branch_hint):
            if not isinstance(entry, dict):
                return
            if "branch" in entry:
                raise ConfigError(f"{context}: {branch_hint}")
            if "timeout" in entry:
                raise ConfigError(f"{context}: {_TIMEOUT_HINT}")
            if "baseVersion" in entry:
                raise ConfigError(f"{context}: {_BASE_VERSION_HINT}")
            if "releaseBranches" in entry:
                raise ConfigError(f"{context}: {_RELEASE_BRANCHES_HINT}")

        reject_branch_era(data, "sanshain.yaml", _BRANCH_HINT_REQUIRE)
        if data.get("provide"):
            reject_branch_era(data["provide"], "provide", _BRANCH_HINT_PROVIDE)
        for i, p in enumerate(data.get("provides") or []):
            reject_branch_era(p, f"provides[{i}]", _BRANCH_HINT_PROVIDE)
        for i, req in enumerate(data.get("requires") or []):
            name = req.get("serviceName") if isinstance(req, dict) else None
            context = f"requires[{i}] ({name})" if name else f"requires[{i}]"
            reject_branch_era(req, context, _BRANCH_HINT_REQUIRE)

    def _validate(self, data):
        if not self.sanshain_url:
            raise ConfigError("Missing required field: sanshainUrl")

        def validate_provide(p, context):
            # A retired entry names its family via apiType alone: the project
            # no longer provides it, so demanding a spec file would force a
            # dead file to stay on disk forever.
            if p.get("retired"):
                return
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
            if "format" in req and (req["format"] != "openapi" or req.get("apiType") != "asyncapi"):
                raise ConfigError(
                    f"{context}: format {req['format']!r} with apiType {req.get('apiType') or 'openapi'!r} "
                    "is not supported; the only combination is apiType: asyncapi with format: openapi"
                )


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
