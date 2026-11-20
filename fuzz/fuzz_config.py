"""Fuzz target `config`: sanshain.yaml as any content. load_config gives a configuration or
the ConfigError it documents; anything else it raises is a finding.

The first byte decides best effort and how the file begins, the rest is what follows. The
beginnings lead the fuzzer past the first checks, into the entries of the lists.

    uv run python fuzz/fuzz_config.py -max_total_time=30
"""

import os
import sys
import tempfile

import atheris

with atheris.instrument_imports(include=["sanshainconan"]):
    from sanshainconan.config import ConfigError, SanshainConfig, load_config

FILE = os.path.join(tempfile.mkdtemp(prefix="sanshain-fuzz-config-"), "sanshain.yaml")

BEGINNINGS = [
    b"",
    b"sanshainUrl: http://localhost:8080\n",
    b"sanshainUrl: http://localhost:8080\nserviceName: svc\nprovides:\n  - ",
    b"sanshainUrl: http://localhost:8080\nserviceName: svc\nannotations:\n"
    b"  - scope: version\n    name: build\n    value: ",
    b"sanshainUrl: http://localhost:8080\nrequires:\n  - serviceName: auth\n"
    b"    outputDirectory: gen\n    endpoints:\n      - method: GET\n        path: /a\n    ",
    b"sanshainUrl: http://localhost:8080\nrequires:\n  - serviceName: auth\n"
    b"    version: 1.2.0\n    outputDirectory: gen\n    endpoints:\n      - ",
]

# What the tests of the other Sanshain clients start from; run once whenever the target starts.
SEEDS = [
    b"sanshainUrl: http://localhost:8080\nserviceName: svc\nprovides:\n  - file: api/openapi.yaml\n",
    b"sanshainUrl: http://localhost:8080\nstrict: true\ntypo: 1\nrequires:\n  - serviceName: auth\n"
    b"    version: 1.2.0\n    outputDirectory: gen\n    endpoints:\n      - method: GET\n        path: /a\n",
    b"sanshainUrl: http://localhost:8080\nannotations:\n  - scope: version\n    name: build\n"
    b'    value: "{{ID}}"\n  - scope: 42\n',
    b"sanshainUrl: http://localhost:8080\nprovides:\n  - null\nrequires:\n  - null\n",
    b"sanshainUrl: http://localhost:8080\nprovide: 7\nprovides: 7\nrequires: text\n",
    b"sanshainUrl: http://localhost:8080\nprovides:\nrequires:\n",
    b"branch: main\nprovide:\n  timeout: 3\n",
    b"- a\n- [b\n",
    b"sanshainUrl: \xff\n",
    b"sanshainUrl: http://localhost:8080\nreleased: 2001-99-99\nretries: !!int many\n",
    b"",
]


def load(content: bytes, best_effort: bool) -> None:
    with open(FILE, "wb") as f:
        f.write(content)
    try:
        config = load_config(FILE, best_effort)
    except ConfigError:
        return
    if not isinstance(config, SanshainConfig):
        raise AssertionError(f"expected a configuration or a ConfigError, got {type(config).__name__}")


def test_one(data: bytes) -> None:
    first = data[0] if data else 0
    load(BEGINNINGS[(first >> 1) % len(BEGINNINGS)] + data[1:], first & 1 == 1)


if __name__ == "__main__":
    for seed in SEEDS:
        load(seed, False)
        load(seed, True)
    atheris.Setup(sys.argv, test_one)
    atheris.Fuzz()
