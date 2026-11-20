"""Fuzz target `annotations`: filling the placeholders of annotation values with any value,
any --set pair and any environment. fill_annotations documents no error, so whatever it raises
is a finding, and every entry is either kept or left out with a warning.

The first line holds the annotation values, separated by tabs. Every further line is a
NAME=value pair, by turns a --set pair and an environment variable.

    uv run python fuzz/fuzz_annotations.py -max_total_time=30
"""

import sys

import atheris

with atheris.instrument_imports(include=["sanshainconan"]):
    from sanshainconan.annotations import SET_ENV_PREFIX, fill_annotations

# What the tests of the other Sanshain clients start from; run once whenever the target starts.
SEEDS = [
    "build {{ID}}\t{{TEAM}}\nID=42\nTEAM=core",
    "{{MISSING}}\tplain\t{{ a }}{{}}\nMISSING=",
    "{{A}}{{B}}{{A}}\nA={{B}}\nB=x\nA=y",
    "{{__class__}}\t{{__init__}}\t{{get}}\n__class__=x",
    "",
]


def fill(text: str) -> None:
    first, *pairs = text.split("\n")
    declared = [
        {"scope": "system" if i % 2 else "version", "name": "annotation", "value": value}
        for i, value in enumerate(first.split("\t"))
    ]
    sets: dict[str, str] = {}
    environment: dict[str, str] = {}
    for i, line in enumerate(pairs):
        name, sep, value = line.partition("=")
        if not sep:
            continue
        if i % 2 == 0:
            sets[name] = value
        else:
            environment[SET_ENV_PREFIX + name] = value
    for flag_hint in (True, False):
        annotations, warnings = fill_annotations(declared, sets, environment, flag_hint)
        if len(annotations) + len(warnings) != len(declared):
            raise AssertionError(
                f"{len(declared)} declared, but {len(annotations)} kept and {len(warnings)} left out"
            )
        for annotation in annotations:
            if set(annotation) != {"scope", "name", "value"}:
                raise AssertionError(f"expected scope, name and value, got {sorted(annotation)}")


def test_one(data: bytes) -> None:
    fill(data.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    for seed in SEEDS:
        fill(seed)
    atheris.Setup(sys.argv, test_one)
    atheris.Fuzz()
