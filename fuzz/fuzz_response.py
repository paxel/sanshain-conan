"""Fuzz target `response`: what the service answers. The input is read as the status and the
body of an answer and, split at line feeds, as the values of its Sanshain-Warning headers.
warning_lines gives one trimmed warning per header line that is not blank; the client's
response handling gives the answer or a SanshainError. Anything else is a finding.

The first two bytes decide the status, the version the service reports and whether a format
was asked for; the rest is the body.

    uv run python fuzz/fuzz_response.py -max_total_time=30
"""

import io
import sys

import atheris
import requests
from requests.structures import CaseInsensitiveDict
from urllib3 import HTTPResponse
from urllib3._collections import HTTPHeaderDict

with atheris.instrument_imports(include=["sanshainconan"]):
    from sanshainconan.client import WARNING_HEADER, SanshainClient, SanshainError, warning_lines

STATUSES = [200, 202, 204, 304, 400, 403, 404, 409, 410, 422, 500, 502]
VERSIONS = [None, "", "1.9.3", "2.3.0", "2.13.0", "not a version"]


class OfflineClient(SanshainClient):
    """No call leaves the process: the version of the service is part of the input."""

    version: str | None = None

    def get_server_version(self) -> str | None:
        return self.version


def answer(status: int, body: bytes, lines: list[str]) -> requests.Response:
    """A response as requests builds it over urllib3: the raw headers keep every line,
    `headers` holds the comma-joined merge."""
    raw_headers = HTTPHeaderDict()
    for line in lines:
        raw_headers.add(WARNING_HEADER, line)
    raw_headers.add("ETag", '"e1"')
    response = requests.Response()
    response.status_code = status
    # A 204 and a 304 have no body; urllib3 refuses to read one.
    content = b"" if status in (204, 304) else body
    response.raw = HTTPResponse(
        body=io.BytesIO(content), headers=raw_headers, status=status, preload_content=False
    )
    response.headers = CaseInsensitiveDict(raw_headers)
    return response


def read(status: int, version: str | None, fmt: str | None, body: bytes) -> None:
    lines = body.decode("utf-8", errors="replace").split("\n")
    warnings = warning_lines(answer(status, body, lines))
    if len(warnings) > len(lines) or any(not w or w != w.strip() for w in warnings):
        raise AssertionError(f"expected one trimmed warning per header line of {body!r}, got {warnings!r}")
    # An answer without the header, and no answer at all.
    if warning_lines(answer(status, body, [])) or warning_lines(None):
        raise AssertionError("expected no warning without the header")

    client = OfflineClient("http://localhost:8080")
    client.version = version
    response = answer(status, body, lines)
    try:
        if client._handle_response(response, "producer") is not response:
            raise AssertionError("expected the answer itself")
    except SanshainError:
        pass
    try:
        result = client._finish_require(answer(status, body, lines), "producer", fmt)
    except SanshainError:
        return
    if result["not_modified"] is not (status == 304):
        raise AssertionError(f"expected not_modified only for a 304, got {result!r} for {status}")
    if status not in (204, 304) and result["body"] != body:
        raise AssertionError("expected the body byte for byte")


# What the tests of the other Sanshain clients start from; run once whenever the target starts.
SEEDS = [
    b'{"error":"version 1.2.0 is GA and immutable","proposed_version":"1.2.1"}',
    b'{"version":"1.2.0","stability":"snapshot","content_hash":"sha256:a",'
    b'"changes":{"inserts":1,"updates":0,"deletes":0}}',
    b"unknown field `annotations`, expected one of `producername`, `build_url`\nsecond line",
    b"<html>\x00\xff bad gateway</html>",
    b'{"error":7,"changes":[]}',
    b"this build requires the 'releaser' role\n\x1b[31m",
    b"openapi: 3.0.3\npaths: {}\n",
    b"asyncapi: 2.6.0\nchannels: {}\n",
    b"2001-99-99",
    b"",
]


def test_one(data: bytes) -> None:
    first = data[0] if data else 0
    second = data[1] if len(data) > 1 else 0
    read(
        STATUSES[first % len(STATUSES)],
        VERSIONS[second % len(VERSIONS)],
        "openapi" if second & 128 else None,
        data[2:],
    )


if __name__ == "__main__":
    for seed in SEEDS:
        for status in STATUSES:
            for version in VERSIONS:
                read(status, version, None, seed)
                read(status, version, "openapi", seed)
    atheris.Setup(sys.argv, test_one)
    atheris.Fuzz()
