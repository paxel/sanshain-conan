import os
import string
import sys
from urllib.parse import quote

import requests
import yaml

from .config import env_flag

HTTP_TIMEOUT = 30
WARNING_HEADER = "Sanshain-Warning"


def sanitize(text):
    if not text:
        return ""
    if len(text) > 1000:
        text = text[:1000] + "... (truncated)"

    printable = set(string.printable)
    return "".join(c if c in printable else "?" for c in text)


def _parse_version(version_str):
    try:
        parts = [int(p) for p in str(version_str).strip().split(".")[:3]]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_pre_2(version_str):
    parts = _parse_version(version_str)
    return parts is not None and parts < (2, 0, 0)


def normalize_line_endings(content):
    """Rewrite CRLF (and stray CR) to LF before upload.

    Sanshain compares provided content byte for byte, so a Windows checkout of
    an otherwise identical file would hash differently and provoke a spurious
    409 version conflict.
    """
    if content is None or "\r" not in content:
        return content
    return content.replace("\r\n", "\n").replace("\r", "\n")


BOTH_STREAMS = "trunk and tag are mutually exclusive - this build is recorded in neither"


ORIGIN_FIELDS = ("build_url", "change_url", "tickets", "note")
ORIGIN_DROPPED_WARNING = "Sanshain Service before 2.9.0 does not take the build's origin; providing without it"


def _first(*values):
    """The first value that is not blank, stripped; None when there is none."""
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _runner_build_url(env):
    server, repo, run = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY"), env.get("GITHUB_RUN_ID")
    if _first(server) and _first(repo) and _first(run):
        return f"{server.strip()}/{repo.strip()}/actions/runs/{run.strip()}"
    return _first(env.get("CI_JOB_URL"), env.get("BUILD_URL"))


def _runner_change_url(env):
    server, repo = _first(env.get("GITHUB_SERVER_URL")), _first(env.get("GITHUB_REPOSITORY"))
    ref = (env.get("GITHUB_REF") or "").strip()
    if server and repo and ref.startswith("refs/pull/"):
        parts = ref.split("/")
        if len(parts) >= 3 and parts[2]:
            return f"{server}/{repo}/pull/{parts[2]}"
    project, iid = _first(env.get("CI_MERGE_REQUEST_PROJECT_URL")), _first(env.get("CI_MERGE_REQUEST_IID"))
    if project and iid:
        return f"{project}/-/merge_requests/{iid}"
    return _first(env.get("CHANGE_URL"))


def resolve_origin(build_url=None, change_url=None, tickets=None, note=None, env=None):
    """What the pipeline knows about why a provide runs, as payload fields.

    An explicit value first, then SANSHAIN_BUILD_URL / SANSHAIN_CHANGE_URL /
    SANSHAIN_TICKETS / SANSHAIN_NOTE, and for the build and change URL the
    runner's own variables on GitHub Actions, GitLab CI and Jenkins. Tickets
    and the note are human intent and never come from the runner. Nothing is
    read from git. Only known fields are present: the server refuses nulls.
    """
    env = os.environ if env is None else env
    origin = {}
    build = _first(build_url, env.get("SANSHAIN_BUILD_URL"), _runner_build_url(env))
    change = _first(change_url, env.get("SANSHAIN_CHANGE_URL"), _runner_change_url(env))
    text = _first(note, env.get("SANSHAIN_NOTE"))
    ids = []
    for raw in (_first(tickets, env.get("SANSHAIN_TICKETS")) or "").split(","):
        ticket = raw.strip()
        if ticket and ticket not in ids:
            ids.append(ticket)
    if build:
        origin["build_url"] = build
    if change:
        origin["change_url"] = change
    if ids:
        origin["tickets"] = ids
    if text:
        origin["note"] = text
    return origin


def resolve_stream(trunk_flag=False, tag=None, strict=False, warn=None):
    """Resolve which dependency graph this build's calls belong to.

    The stream is a property of the invocation, never of sanshain.yaml: the
    same checkout is built by trunk CI and on a developer's laptop, and the
    trunk pin store is last-writer-wins — inferring it would let a local build
    overwrite what CI recorded. Reads SANSHAIN_TRUNK / SANSHAIN_TAG when the
    flags are unset.

    Returns a (trunk, tag) pair. Declaring both is a warning, never a failed
    build: the graph is informational, so the build sends neither and is
    recorded in no stream. Under strict it raises StrictError before any
    request.
    """
    trunk = trunk_flag or env_flag("SANSHAIN_TRUNK")
    resolved_tag = (tag or os.environ.get("SANSHAIN_TAG") or "").strip() or None
    if trunk and resolved_tag:
        if strict:
            raise StrictError(f"strict: {BOTH_STREAMS}")
        if warn:
            warn(BOTH_STREAMS)
        return False, None
    return trunk, resolved_tag


def warning_lines(response):
    """Every Sanshain-Warning header line of a response, one entry per line.

    requests joins repeated headers with commas in `response.headers`, and a
    warning may itself contain a comma, so the separate lines are read from
    the underlying urllib3 headers; the merged value is only the fallback.
    """
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    getlist = getattr(raw_headers, "getlist", None)
    lines = None
    if callable(getlist):
        try:
            lines = getlist(WARNING_HEADER)
        except (TypeError, AttributeError):
            lines = None
    if not isinstance(lines, list):
        headers = getattr(response, "headers", None)
        merged = headers.get(WARNING_HEADER) if headers is not None else None
        lines = [merged] if isinstance(merged, str) else []
    return [line.strip() for line in lines if isinstance(line, str) and line.strip()]


class StrictError(Exception):
    """Strict mode turned a warning into a failure; best-effort does not soften it.

    `error` is the failure of the same call, if it failed too: callers print
    it before the strict failure.
    """

    def __init__(self, message, error=None):
        self.error = error
        super().__init__(message)


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
    def __init__(self, url, token=None, insecure=False, on_warning=None, strict=False):
        """`on_warning` receives every Sanshain-Warning header line as
        received; with `strict` a call that carried one raises StrictError
        after it."""
        self.url = url.rstrip("/")
        self.on_warning = on_warning
        self.strict = strict
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

    def _report_warnings(self, response):
        lines = warning_lines(response)
        if self.on_warning:
            for line in lines:
                self.on_warning(line)
        return lines

    def _check_strict(self, warnings, error=None):
        if self.strict and warnings:
            raise StrictError(f"strict: Sanshain warned: {warnings[0]}", error)

    def _warned_call(self, response, finish):
        """Print the response's warnings, then `finish(response)`. Under
        strict a warning fails the call afterwards, also when it failed."""
        warnings = self._report_warnings(response)
        try:
            result = finish(response)
        except SanshainError as e:
            self._check_strict(warnings, e)
            raise
        self._check_strict(warnings)
        return result

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

    def provide(self, producer_name, openapi_yaml, stability, trunk=False, tag=None, origin=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "openapi_yaml": normalize_line_endings(openapi_yaml),
                "stability": stability,
            },
            trunk,
            tag,
        )
        payload.update(origin or {})
        return self._post_provide("/provide", payload, producer_name)

    def provide_asyncapi(self, producer_name, asyncapi_yaml, stability, trunk=False, tag=None, origin=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "asyncapi_yaml": normalize_line_endings(asyncapi_yaml),
                "stability": stability,
            },
            trunk,
            tag,
        )
        payload.update(origin or {})
        return self._post_provide("/provide/asyncapi", payload, producer_name)

    def provide_proto(self, producer_name, proto_content, stability, trunk=False, tag=None, origin=None):
        payload = self._apply_stream(
            {
                "producername": producer_name,
                "proto_content": normalize_line_endings(proto_content),
                "stability": stability,
            },
            trunk,
            tag,
        )
        payload.update(origin or {})
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
        # A service before 2.9.0 refuses the origin fields by name: the provide
        # must not fail for a fact the service cannot store, so it is repeated
        # without them.
        if response.status_code == 422 and any(f in payload for f in ORIGIN_FIELDS):
            if any(f"unknown field `{f}`" in (response.text or "") for f in ORIGIN_FIELDS):
                print(f"⚠ {ORIGIN_DROPPED_WARNING}", file=sys.stderr)
                payload = {k: v for k, v in payload.items() if k not in ORIGIN_FIELDS}
                response = requests.post(
                    f"{self.url}{path}", json=payload, headers=self.headers, verify=self.verify, timeout=HTTP_TIMEOUT
                )

        def finish(response):
            self._handle_response(response, producer_name)
            try:
                return response.json()
            except ValueError:
                return None

        return self._warned_call(response, finish)

    def _check_format(self, response, fmt):
        """With format: openapi the answer must be an OpenAPI document; an
        older service ignores the parameter and answers AsyncAPI."""
        if not fmt:
            return
        try:
            doc = yaml.safe_load(response.text)
        except yaml.YAMLError:
            doc = None
        if isinstance(doc, dict) and "openapi" in doc:
            return
        self._raise_format_needs_2_4(fmt, self.get_server_version())

    @staticmethod
    def _raise_format_needs_2_4(fmt, version):
        server = f"server is {version}" if version else "server version unknown"
        raise SanshainError(f"format: {fmt} needs Sanshain Service 2.4.0 or later ({server})")

    def _check_format_rejected(self, response, fmt):
        """A service older than 2.4.0 rejects the unknown `format` query
        parameter with 400; name that instead of the raw 400. A 2.4.0+
        service's own 400 passes through unchanged."""
        if not fmt or response.status_code != 400 or "format" not in (response.text or "").lower():
            return
        version = self.get_server_version()
        parsed = _parse_version(version) if version else None
        if parsed is None or parsed < (2, 4, 0):
            self._raise_format_needs_2_4(fmt, version)

    def _finish_require(self, response, producer_name, fmt):
        if response.status_code == 304:
            return {"not_modified": True, "content": None, "etag": None}
        self._check_format_rejected(response, fmt)
        self._handle_response(response, producer_name)
        self._check_format(response, fmt)
        response_etag = response.headers.get("ETag")
        # `body` is the answer byte for byte; it is what gets written to disk.
        return {"not_modified": False, "content": response.text, "body": response.content, "etag": response_etag}

    def require_bundle(
        self,
        consumer_name,
        producer_name,
        version,
        endpoints,
        api_type=None,
        etag=None,
        trunk=False,
        tag=None,
        fmt=None,
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
            f"{self.url}/require-bundle",
            json=payload,
            params={"format": fmt} if fmt else None,
            headers=headers,
            verify=self.verify,
            timeout=HTTP_TIMEOUT,
        )
        return self._warned_call(response, lambda r: self._finish_require(r, producer_name, fmt))

    def require(
        self,
        consumer_name,
        producer_name,
        version,
        path,
        method,
        api_type=None,
        etag=None,
        trunk=False,
        tag=None,
        fmt=None,
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
        if fmt:
            params["format"] = fmt
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
        return self._warned_call(response, lambda r: self._finish_require(r, producer_name, fmt))

    def push_catalog(self, system_name, catalog_info_yaml, trunk=False, file_label="catalogInfo"):
        """Record the system's periphery from its Backstage catalog-info.yaml (PUT /catalog/<system>).

        Carries `trunk: true` only for a trunk build and never a tag: the
        endpoint answers 422 to unknown fields. Needs Sanshain Service 2.4.0.

        A file Sanshain cannot read is no failure: the answer is a 200 with
        `recorded: false` and the reason in a Sanshain-Warning header.
        """
        payload = {"catalog_info_yaml": catalog_info_yaml}
        if trunk:
            payload["trunk"] = True
        response = requests.put(
            f"{self.url}/catalog/{quote(system_name, safe='')}",
            json=payload,
            headers=self.headers,
            verify=self.verify,
            timeout=HTTP_TIMEOUT,
        )
        warnings = self._report_warnings(response)
        try:
            if response.status_code == 404:
                version = self.get_server_version()
                server = f"server is {version}" if version else "server version unknown"
                raise SanshainError(f"sanshain catalog needs Sanshain Service 2.4.0 or later ({server})")
            self._handle_response(response, system_name)
        except SanshainError as e:
            self._check_strict(warnings, e)
            raise
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            body = {}
        # Missing `recorded` counts as true (a 2.4.0 pre-release service).
        if body.get("recorded", True) is False and not warnings:
            # The service names the reason in a header; without one, say so.
            text = f"Sanshain did not record {file_label}"
            if self.on_warning:
                self.on_warning(text)
            if self.strict:
                raise StrictError(f"strict: {text}")
        self._check_strict(warnings)
        return body
