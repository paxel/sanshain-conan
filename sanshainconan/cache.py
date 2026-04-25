import hashlib
import json
import os
from datetime import datetime, timezone


DEFAULT_CACHE_DIR = ".sanshain-cache"
CACHE_FILE = "state.json"


class SanshainCache:
    def __init__(self, cache_dir=None):
        d = cache_dir or DEFAULT_CACHE_DIR
        self.cache_file = os.path.join(d, CACHE_FILE)
        self.state = self._load()

    def _load(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"provides": {}, "requires": {}}

    def save(self):
        d = os.path.dirname(self.cache_file)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_provide_entry(self, key):
        return self.state["provides"].get(key)

    def update_provide_entry(self, key, content_hash, version):
        self.state["provides"][key] = {
            "content_hash": content_hash,
            "version": version,
            "last_provided": datetime.now(timezone.utc).isoformat()
        }

    def get_require_entry(self, key):
        return self.state["requires"].get(key)

    def update_require_entry(self, key, etag):
        self.state["requires"][key] = {
            "etag": etag,
            "last_fetched": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def compute_hash(content):
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"sha256:{h}"

    @staticmethod
    def require_key(service_name, branch, method, path):
        return f"{service_name}|{branch}|{method}|{path}"

    @staticmethod
    def require_bundle_key(service_name, branch):
        return f"{service_name}|{branch}|bundle"
