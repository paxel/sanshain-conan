"""The catalog step shared by the CLI and the Conan helper: push catalog-info.yaml to Sanshain."""

import os

from .client import SanshainError
from .config import ConfigError


def run_catalog(config, client, base_path, trunk, info, warn):
    """Push the file named by `catalogInfo` for this build's stream.

    Strict checks only serviceName and catalogInfo and raises ConfigError;
    an unreadable file or a failed call raises SanshainError, which the
    caller turns into a warning under best-effort. A push Sanshain did not
    record only warns (through the client), unless strict.
    """
    if not config.service_name:
        if config.strict:
            raise ConfigError("serviceName is required (in sanshain.yaml or via environment)")
        warn("No serviceName configured. Skipping catalog. Set strict: true to fail in this case.")
        return
    if not config.catalog_info:
        if config.strict:
            raise ConfigError("strict: sanshain.yaml has no catalogInfo")
        warn("No catalogInfo in sanshain.yaml - skipping catalog.")
        return

    path = os.path.join(base_path, config.catalog_info)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # UTF-8, BOM stripped
            content = f.read()
    except OSError as e:
        raise SanshainError(f"Cannot read catalogInfo file {path}: {e.strerror or e}")

    response = client.push_catalog(config.service_name, content, trunk=trunk, file_label=path) or {}
    if response.get("recorded", True) is False:
        return  # the client already warned why
    resources = response.get("resources") or []
    graphs = "main+dev" if response.get("trunk", trunk) else "dev"
    info(f"Catalog recorded for {response.get('system', config.service_name)} ({graphs}): {len(resources)} resources")
    for resource in resources:
        info(f"  {resource}")
