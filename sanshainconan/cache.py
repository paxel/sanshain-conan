import json
import os
import posixpath
from datetime import UTC, datetime
from typing import Any

DEFAULT_CACHE_DIR = ".sanshain-cache"
CACHE_FILE = "state.json"


class SanshainCache:
    """Require-side ETag cache: remembers the ETag of each downloaded snippet
    so subsequent runs can send If-None-Match and skip on 304 Not Modified."""

    def __init__(self, cache_dir: str | os.PathLike[str] | None = None) -> None:
        d = cache_dir or DEFAULT_CACHE_DIR
        self.cache_file = os.path.join(d, CACHE_FILE)
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file) as f:
                    state = json.load(f)
                    if isinstance(state, dict) and isinstance(state.get("requires"), dict):
                        return {"requires": state["requires"]}
        except (OSError, ValueError, RecursionError):
            # Unreadable, not JSON, not text at all or nested too deeply: an empty state, every
            # require is fetched.
            pass
        return {"requires": {}}

    def save(self) -> None:
        d = os.path.dirname(self.cache_file)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_require_entry(self, key: str) -> Any:
        return self.state["requires"].get(key)

    def update_require_entry(self, key: str, etag: str) -> None:
        self.state["requires"][key] = {"etag": etag, "last_fetched": datetime.now(UTC).isoformat()}

    @staticmethod
    def require_key(
        service_name: str,
        version: str,
        method: str,
        path: str,
        fmt: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        # The format and the output directory are part of the key, so neither
        # the AsyncAPI and the OpenAPI rendering of the same pin nor two
        # directories it is written to share an ETag.
        return _suffixed(f"{service_name}|{version}|{method}|{path}", fmt, output_dir)

    @staticmethod
    def require_bundle_key(
        service_name: str, version: str, fmt: str | None = None, output_dir: str | None = None
    ) -> str:
        return _suffixed(f"{service_name}|{version}|bundle", fmt, output_dir)


def _suffixed(key: str, fmt: str | None, output_dir: str | None) -> str:
    if fmt:
        key = f"{key}|format={fmt}"
    if output_dir:
        # As written in sanshain.yaml, with forward slashes and normalized.
        normalized = posixpath.normpath(str(output_dir).replace("\\", "/"))
        key = f"{key}|out={normalized}"
    return key
