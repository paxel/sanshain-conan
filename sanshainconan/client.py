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
        return self._post("/provide", payload)

    def provide_asyncapi(self, service_name, branch, asyncapi_yaml):
        payload = {
            "servicename": service_name,
            "branch": branch,
            "asyncapi_yaml": asyncapi_yaml
        }
        return self._post("/provide/asyncapi", payload)

    def provide_proto(self, service_name, branch, proto_content):
        payload = {
            "servicename": service_name,
            "branch": branch,
            "proto_content": proto_content
        }
        return self._post("/provide/grpc", payload)

    def _post(self, path, payload):
        response = requests.post(f"{self.url}{path}", json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def require_bundle(self, client_name, service_name, branch, endpoints, timeout=30, api_type=None):
        payload = {
            "clientname": client_name,
            "servicename": service_name,
            "branch": branch,
            "endpoints": endpoints,
            "timeout": timeout
        }
        if api_type:
            payload["api_type"] = api_type
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        response = requests.post(f"{self.url}/require-bundle", json=payload, headers=headers)
        response.raise_for_status()
        return response.text

    def require(self, client_name, service_name, branch, path, method, timeout=30, api_type=None):
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
        url = f"{self.url}/require"
        if api_type == "asyncapi":
            url = f"{self.url}/require/asyncapi"
        elif api_type == "proto":
            url = f"{self.url}/require/grpc"

        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.text
