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


def normalize_line_endings(content):
    """Rewrite CRLF (and stray CR) to LF before upload.

    Sanshain compares provided content byte for byte, so a Windows checkout of
    an otherwise identical file would hash differently and provoke a spurious
    409 version conflict.
    """
    if content is None or "\r" not in content:
        return content
    return content.replace("\r\n", "\n").replace("\r", "\n")


def resolve_stream(trunk_flag=False, tag=None):
    """Resolve which dependency graph this build's calls belong to.

    The stream is a property of the invocation, never of sanshain.yaml: the
    same checkout is built by trunk CI and on a developer's laptop, and the
    trunk pin store is last-writer-wins — inferring it would let a local build
    overwrite what CI recorded. Reads SANSHAIN_TRUNK / SANSHAIN_TAG when the
    flags are unset.

    Returns a (trunk, tag) pair; declaring both raises, because the server
    would answer 400 and naming the misconfiguration locally beats a round
    trip.
    """
    trunk = trunk_flag or os.environ.get("SANSHAIN_TRUNK") in ("true", "1")
    resolved_tag = (tag or os.environ.get("SANSHAIN_TAG") or "").strip() or None
    if trunk and resolved_tag:
        raise SanshainError(
            f"this build declares both trunk and tag '{resolved_tag}' — a build belongs to the "
            "trunk stream or to one sanshain-branch, never both; set only one of --trunk / "
            "SANSHAIN_TRUNK and --tag / SANSHAIN_TAG"
        )
    return trunk, resolved_tag


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
        if status == 403:
            # The remedy is a role grant — nothing the Producer can change in
            # its own repository — so the message has to name it.
            raise SanshainError(
                f"Refused (403): {sanitized_body}\n"
                "  Publishing GA requires the 'releaser' role; retiring requires it too, or a "
                f"maintainer grant on '{producer}'. Grant the role to the user or token this "
                "build authenticates as (administrators and root always hold it), or publish "
                "as a snapshot by leaving --ga / SANSHAIN_GA unset."
            )

        raise SanshainError(f"Request failed with status {status}: {sanitized_body}")

    @staticmethod
    def _apply_stream(payload, trunk, tag):
        # Absent fields rather than false/null: the server defaults them and
        # rejects unknown shapes.
        if trunk:
            payload["trunk"] = True
        elif tag:
            payload["tag"] = tag
        return payload

    def provide(self, producer_name, openapi_yaml, stability, trunk=False, tag=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "openapi_yaml": normalize_line_endings(openapi_yaml),
                "stability": stability,
            },
            trunk,
            tag,
        )
        return self._post_provide("/provide", payload, producer_name)

    def provide_asyncapi(self, producer_name, asyncapi_yaml, stability, trunk=False, tag=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "asyncapi_yaml": normalize_line_endings(asyncapi_yaml),
                "stability": stability,
            },
            trunk,
            tag,
        )
        return self._post_provide("/provide/asyncapi", payload, producer_name)

    def provide_proto(self, producer_name, proto_content, stability, trunk=False, tag=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "proto_content": normalize_line_endings(proto_content),
                "stability": stability,
            },
            trunk,
            tag,
        )
        return self._post_provide("/provide/grpc", payload, producer_name)

    def retire(self, producer_name, api_type=None, dry_run=False):
        """Declare that this Producer no longer provides an API family.

        An ordinary provide call for that family carrying `retired: true` and
        no document — it deliberately has no way to carry a body, a stability
        or a stream, which the server refuses alongside `retired` with 400.
        Gated like releasing: the caller needs the 'releaser' role or a
        maintainer grant on this Producer, or the server answers 403.
        """
        path = "/provide"
        if api_type == "asyncapi":
            path = "/provide/asyncapi"
        elif api_type in ("proto", "grpc"):
            path = "/provide/grpc"
        payload = {"producername": producer_name, "retired": True}
        if dry_run:
            payload["dry_run"] = True
        return self._post_provide(path, payload, producer_name)

    def _post_provide(self, path, payload, producer_name):
        response = requests.post(
            f"{self.url}{path}", json=payload, headers=self.headers, verify=self.verify, timeout=HTTP_TIMEOUT
        )
        self._handle_response(response, producer_name)
        try:
            return response.json()
        except ValueError:
            return None

    def require_bundle(
        self, consumer_name, producer_name, version, endpoints, api_type=None, etag=None, trunk=False, tag=None
    ):
        # The bundle endpoint reads the stream from the body — its handler has
        # no query extractor, so query parameters would be silently dropped and
        # a trunk build would record no trunk pins.
        payload = self._apply_stream(
            {
                "consumername": consumer_name,
                "producername": producer_name,
                "version": version,
                "endpoints": endpoints,
                "api_type": api_type or "openapi",
            },
            trunk,
            tag,
        )
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

    def require(
        self, consumer_name, producer_name, version, path, method, api_type=None, etag=None, trunk=False, tag=None
    ):
        # Unlike the bundle, the single-endpoint require reads its stream from
        # the query string.
        params = self._apply_stream(
            {
                "consumername": consumer_name,
                "producername": producer_name,
                "version": version,
                "path": path,
                "method": method,
            },
            trunk,
            tag,
        )
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
