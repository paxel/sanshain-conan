import os
import string

import requests

HTTP_TIMEOUT = 30


def sanitize(text):
    if not text:
        return ""
    if len(text) > 1000:
        text = text[:1000] + "... (truncated)"

    printable = set(string.printable)
    return "".join(c if c in printable else "?" for c in text)


def _is_pre_2(version_str):
    try:
        parts = [int(p) for p in str(version_str).strip().split(".")[:3]]
    except ValueError:
        return False
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts) < (2, 0, 0)


class SanshainError(Exception):
    """A Sanshain request failed or was rejected by the server."""


class VersionConflictError(SanshainError):
    """The server rejected a provide by the version rules (409).

    Carries the server's message and the `proposed_version` — the next free
    version to publish as instead.
    """

    def __init__(self, server_message, proposed_version):
        self.server_message = server_message
        self.proposed_version = proposed_version
        super().__init__(f"{server_message} (proposed_version: {proposed_version})")


class SanshainClient:
    def __init__(self, url, token=None, insecure=False):
        self.url = url.rstrip("/")
        self.token = token or os.environ.get("SANSHAIN_TOKEN")
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.verify = not insecure

    def get_server_version(self):
        """Return the server's own build version string, or None if unreachable."""
        try:
            response = requests.get(
                f"{self.url}/version", headers=self.headers, verify=self.verify, timeout=HTTP_TIMEOUT
            )
            if response.status_code != 200:
                return None
            return response.json().get("version")
        except (requests.RequestException, ValueError, AttributeError):
            return None

    def _diagnose_wrong_server(self):
        version = self.get_server_version()
        if version and _is_pre_2(version):
            return (
                f"Sanshain server at {self.url} is {version}; this client requires Sanshain 2.x — upgrade the server."
            )
        return None

    def _handle_response(self, response, producer_name=None):
        if 200 <= response.status_code < 300:
            return response

        status = response.status_code
        try:
            body = response.text
        except Exception:
            body = str(response.content)

        error_json = None
        try:
            error_json = response.json()
        except ValueError:
            pass

        if status == 409 and isinstance(error_json, dict) and error_json.get("proposed_version"):
            raise VersionConflictError(error_json.get("error", body), error_json["proposed_version"])

        # A confusing failure may just be a pre-2.0 server; check once, lazily.
        wrong_server = self._diagnose_wrong_server()
        if wrong_server:
            raise SanshainError(wrong_server)

        sanitized_body = sanitize(body)
        producer = producer_name or "<producer>"

        if status == 404:
            raise SanshainError(
                f"Unknown (404): the producer or the pinned version does not exist on the server "
                f"(in either stability). Fix the 'version' pin — list available versions: "
                f"GET /producers/{producer}/versions. Server said: {sanitized_body}"
            )
        if status == 410:
            raise SanshainError(
                f"Absent (410): the pinned version exists but deliberately does not include the "
                f"requested endpoint(s). Server said: {sanitized_body}"
            )
        if status == 422:
            raise SanshainError(f"Invalid request shape (422): {sanitized_body}")

        raise SanshainError(f"Request failed with status {status}: {sanitized_body}")

    def provide(self, producer_name, openapi_yaml, stability):
        payload = {
            "producername": producer_name,
            "openapi_yaml": openapi_yaml,
            "stability": stability,
        }
        return self._post_provide("/provide", payload, producer_name)

    def provide_asyncapi(self, producer_name, asyncapi_yaml, stability):
        payload = {
            "producername": producer_name,
            "asyncapi_yaml": asyncapi_yaml,
            "stability": stability,
        }
        return self._post_provide("/provide/asyncapi", payload, producer_name)

    def provide_proto(self, producer_name, proto_content, stability):
        payload = {
            "producername": producer_name,
            "proto_content": proto_content,
            "stability": stability,
        }
        return self._post_provide("/provide/grpc", payload, producer_name)

    def _post_provide(self, path, payload, producer_name):
        response = requests.post(
            f"{self.url}{path}", json=payload, headers=self.headers, verify=self.verify, timeout=HTTP_TIMEOUT
        )
        self._handle_response(response, producer_name)
        try:
            return response.json()
        except ValueError:
            return None

    def require_bundle(self, consumer_name, producer_name, version, endpoints, api_type=None, etag=None):
        payload = {
            "consumername": consumer_name,
            "producername": producer_name,
            "version": version,
            "endpoints": endpoints,
            "api_type": api_type or "openapi",
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        if etag:
            headers["If-None-Match"] = etag
        response = requests.post(
            f"{self.url}/require-bundle", json=payload, headers=headers, verify=self.verify, timeout=HTTP_TIMEOUT
        )
        if response.status_code == 304:
            return {"not_modified": True, "content": None, "etag": None}
        self._handle_response(response, producer_name)
        response_etag = response.headers.get("ETag")
        return {"not_modified": False, "content": response.text, "etag": response_etag}

    def require(self, consumer_name, producer_name, version, path, method, api_type=None, etag=None):
        params = {
            "consumername": consumer_name,
            "producername": producer_name,
            "version": version,
            "path": path,
            "method": method,
        }
        headers = self.headers.copy()
        headers["Accept-Encoding"] = "gzip"
        if etag:
            headers["If-None-Match"] = etag
        url = f"{self.url}/require"
        if api_type == "asyncapi":
            url = f"{self.url}/require/asyncapi"
        elif api_type == "proto" or api_type == "grpc":
            url = f"{self.url}/require/grpc"

        response = requests.get(url, params=params, headers=headers, verify=self.verify, timeout=HTTP_TIMEOUT)
        if response.status_code == 304:
            return {"not_modified": True, "content": None, "etag": None}
        self._handle_response(response, producer_name)
        response_etag = response.headers.get("ETag")
        return {"not_modified": False, "content": response.text, "etag": response_etag}
