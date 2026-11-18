"""Fuzz target `state`: the require state file as any content. Reading it never fails, the
ETag it gives for a require is a text or none, and the state can always be written and saved
again.

    uv run python fuzz/fuzz_state.py -max_total_time=30
"""

import os
import sys
import tempfile

import atheris

with atheris.instrument_imports(include=["sanshainconan"]):
    from sanshainconan.cache import CACHE_FILE, SanshainCache
    from sanshainconan.cli import etag_for

DIR = tempfile.mkdtemp(prefix="sanshain-fuzz-state-")
FILE = os.path.join(DIR, CACHE_FILE)

# What the tests of the other Sanshain clients start from; run once whenever the target starts.
SEEDS = [
    b'{"requires":{"p|1.0.0|GET|/a|out=gen":{"etag":"abc","last_fetched":"2026-11-18T10:00:00Z"}}}',
    b'{"requires":{"key":null}}',
    b'{"requires":{"key":7}}',
    b'{"requires":{"key":{"etag":7}}}',
    b'{"requires":null}',
    b'{"requires":[1,2]}',
    b'{"requires":7}',
    b'"text"',
    b"\xff\xfe",
    b"",
]


def read(content: bytes) -> None:
    with open(FILE, "wb") as f:
        f.write(content)
    cache = SanshainCache(DIR)
    # FILE exists, so the ETag of the entry is looked up as for an output file that is there.
    etag = etag_for(cache, "key", FILE)
    if etag is not None and not isinstance(etag, str):
        raise AssertionError(f"expected an ETag or none, got {etag!r}")
    cache.update_require_entry("key", "etag")
    if etag_for(cache, "key", FILE) != "etag":
        raise AssertionError("expected the entry just written")
    cache.save()
    if etag_for(SanshainCache(DIR), "key", FILE) != "etag":
        raise AssertionError("expected the saved entry to be read again")


def test_one(data: bytes) -> None:
    read(data)


if __name__ == "__main__":
    for seed in SEEDS:
        read(seed)
    atheris.Setup(sys.argv, test_one)
    atheris.Fuzz()
