import json
import os
from datetime import datetime, timezone

DEFAULT_CACHE_DIR = ".sanshain-cache"
CACHE_FILE = "state.json"


class SanshainCache:
    """Require-side ETag cache: remembers the ETag of each downloaded snippet
    so subsequent runs can send If-None-Match and skip on 304 Not Modified."""

    def __init__(self, cache_dir=None):
        d = cache_dir or DEFAULT_CACHE_DIR
        self.cache_file = os.path.join(d, CACHE_FILE)
        self.state = self._load()

    def _load(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    state = json.load(f)
                    if isinstance(state, dict) and isinstance(state.get("requires"), dict):
                        return {"requires": state["requires"]}
        except (OSError, json.JSONDecodeError):
            pass
        return {"requires": {}}

    def save(self):
        d = os.path.dirname(self.cache_file)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_require_entry(self, key):
        return self.state["requires"].get(key)

    def update_require_entry(self, key, etag):
        self.state["requires"][key] = {"etag": etag, "last_fetched": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def require_key(service_name, version, method, path):
        return f"{service_name}|{version}|{method}|{path}"

    @staticmethod
    def require_bundle_key(service_name, version):
        return f"{service_name}|{version}|bundle"
