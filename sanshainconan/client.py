import os
import requests

class SanshainClient:
    def __init__(self, url, token=None):
        self.url = url.rstrip("/")
        self.token = token or os.environ.get("SANSHAIN_TOKEN")
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def provide(self, service_name, branch, openapi_yaml):
        payload = {
            "servicename": service_name,
            "branch": branch,
            "openapi_yaml": openapi_yaml
        }
        response = requests.post(f"{self.url}/provide", json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def require_bundle(self, client_name, service_name, branch, endpoints, timeout=30):
        payload = {
            "clientname": client_name,
            "servicename": service_name,
            "branch": branch,
            "endpoints": endpoints,
            "timeout": timeout
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        response = requests.post(f"{self.url}/require-bundle", json=payload, headers=headers)
        response.raise_for_status()
        return response.text

    def require(self, client_name, service_name, branch, path, method, timeout=30):
        params = {
            "clientname": client_name,
            "servicename": service_name,
            "branch": branch,
            "path": path,
            "method": method,
            "timeout": timeout
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        response = requests.get(f"{self.url}/require", params=params, headers=headers)
        response.raise_for_status()
        return response.text
