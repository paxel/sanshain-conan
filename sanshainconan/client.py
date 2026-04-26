import os
import requests
import string


def sanitize(text):
    if not text:
        return ""
    if len(text) > 1000:
        text = text[:1000] + "... (truncated)"

    printable = set(string.printable)
    return "".join(c if c in printable else "?" for c in text)


class SanshainClient:
    def __init__(self, url, token=None, insecure=False):
        self.url = url.rstrip("/")
        self.token = token or os.environ.get("SANSHAIN_TOKEN")
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.verify = not insecure

    def _handle_response(self, response):
        if 200 <= response.status_code < 300:
            return response

        try:
            body = response.text
        except Exception:
            body = str(response.content)

        sanitized_body = sanitize(body)

        if response.status_code == 409:
            raise Exception(
                "Concurrent modification detected. Server version has advanced beyond your base_version. Re-run to fetch the latest state."
            )

        raise Exception(f"Request failed with status {response.status_code}: {sanitized_body}")

    def provide(self, service_name, branch, openapi_yaml, base_version=None):
        payload = {"servicename": service_name, "branch": branch, "openapi_yaml": openapi_yaml, "api_type": "openapi"}
        if base_version is not None:
            payload["base_version"] = base_version
        return self._post_provide("/provide", payload)

    def provide_asyncapi(self, service_name, branch, asyncapi_yaml, base_version=None):
        payload = {
            "servicename": service_name,
            "branch": branch,
            "asyncapi_yaml": asyncapi_yaml,
            "api_type": "asyncapi",
        }
        if base_version is not None:
            payload["base_version"] = base_version
        return self._post_provide("/provide/asyncapi", payload)

    def provide_proto(self, service_name, branch, proto_content, base_version=None):
        payload = {"servicename": service_name, "branch": branch, "proto_content": proto_content, "api_type": "proto"}
        if base_version is not None:
            payload["base_version"] = base_version
        return self._post_provide("/provide/grpc", payload)

    def _post_provide(self, path, payload):
        response = requests.post(f"{self.url}{path}", json=payload, headers=self.headers, verify=self.verify)
        self._handle_response(response)
        try:
            return response.json()
        except ValueError:
            return None

    def _post(self, path, payload):
        response = requests.post(f"{self.url}{path}", json=payload, headers=self.headers, verify=self.verify)
        self._handle_response(response)
        try:
            return response.json()
        except ValueError:
            return response.text

    def require_bundle(self, client_name, service_name, branch, endpoints, timeout=30, api_type=None, etag=None):
        payload = {
            "clientname": client_name,
            "servicename": service_name,
            "branch": branch,
            "endpoints": endpoints,
            "timeout": timeout,
            "api_type": api_type or "openapi",
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        if etag:
            headers["If-None-Match"] = etag
        response = requests.post(f"{self.url}/require-bundle", json=payload, headers=headers, verify=self.verify)
        if response.status_code == 304:
            return {"not_modified": True, "content": None, "etag": None}
        self._handle_response(response)
        response_etag = response.headers.get("ETag")
        return {"not_modified": False, "content": response.text, "etag": response_etag}

    def require(self, client_name, service_name, branch, path, method, timeout=30, api_type=None, etag=None):
        params = {
            "clientname": client_name,
            "servicename": service_name,
            "branch": branch,
            "path": path,
            "method": method,
            "timeout": timeout,
            "api_type": api_type or "openapi",
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        if etag:
            headers["If-None-Match"] = etag
        url = f"{self.url}/require"
        if api_type == "asyncapi":
            url = f"{self.url}/require/asyncapi"
        elif api_type == "proto":
            url = f"{self.url}/require/grpc"

        response = requests.get(url, params=params, headers=headers, verify=self.verify)
        if response.status_code == 304:
            return {"not_modified": True, "content": None, "etag": None}
        self._handle_response(response)
        response_etag = response.headers.get("ETag")
        return {"not_modified": False, "content": response.text, "etag": response_etag}
