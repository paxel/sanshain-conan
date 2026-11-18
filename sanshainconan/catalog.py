"""The catalog step shared by the CLI and the Conan helper: push catalog-info.yaml to Sanshain."""

import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .client import SanshainClient, SanshainError
from .config import ConfigError, SanshainConfig


def run_catalog(
    config: SanshainConfig,
    client: SanshainClient,
    base_path: str,
    trunk: bool,
    info: Callable[[str], object],
    warn: Callable[[str], object],
    annotations: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """Push the file named by `catalogInfo` for this build's stream, with the
    filled annotations (the client sends only the system ones).

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
        with open(path, encoding="utf-8-sig") as f:  # UTF-8, BOM stripped
            content = f.read()
    except OSError as e:
        raise SanshainError(f"Cannot read catalogInfo file {path}: {e.strerror or e}") from e

    response = (
        client.push_catalog(
            config.service_name, content, trunk=trunk, file_label=path, annotations=annotations
        )
        or {}
    )
    if response.get("recorded", True) is False:
        return  # the client already warned why
    resources = response.get("resources") or []
    graphs = "main+dev" if response.get("trunk", trunk) else "dev"
    system = response.get("system", config.service_name)
    info(f"Catalog recorded for {system} ({graphs}): {len(resources)} resources")
    for resource in resources:
        info(f"  {resource}")
