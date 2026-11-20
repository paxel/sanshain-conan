# sanshain-conan moves to the gates standard

Decided on 2026-11-18.

sanshain-conan had its own gates: a build workflow with flake8, black, bandit, a lenient mypy
and the tests on Python 3.11, osv-scanner, a SonarQube Cloud workflow, CodeQL, Scorecard, a
sourcehut build, and a release that published to PyPI. Every paxel repository had done so,
each differently. [paxel/gates](https://github.com/paxel/gates) is the one standard that
replaces those, as shared workflows a repository calls, and its audit found 19 checks of it
missing here ([issue 8](https://github.com/paxel/sanshain-conan/issues/8)).

sanshain-conan meets the standard of gates v1.2.0
([sancon-1000](https://github.com/paxel/sanshain-conan/issues/11) to
[sancon-1007](https://github.com/paxel/sanshain-conan/issues/18)). Where the standard
decides, it is followed without a note here: the shared OSV gate, Python gate, SonarQube
Cloud job, CodeQL, Scorecard, fuzz, release gate and provenance workflows, one coverage
ratchet, the lint config, the files and the badge row. What follows is where sanshain-conan
adds to it, or had a choice.

**The Python release.** `.python-version` names 3.12, which the gate, the fuzz run and the
release build with. It is the oldest release Atheris, the fuzzer, has wheels for, and the
shared workflows install wheels only. `requires-python` in `pyproject.toml` keeps `>=3.11`:
that is what a user is promised.

**The oldest Python.** The old build workflow tested on Python 3.11. The shared Python gate
runs on the pinned release. So CI keeps a job of the repository's own that runs the tests on
Python 3.11 and builds the wheel and the source distribution there. Atheris carries a marker
in the `dev` group, so that the same lock file installs on 3.11 without it.

**Lints and types.** The standard's `ruff.toml` is taken as it is, and the code was changed
to meet it, the tests included; ruff reads the target version from `requires-python`, so it
asks for nothing Python 3.11 lacks. mypy runs strict over the package, the tests and the
fuzz targets, checking against Python 3.11; every function got its types. The package is a
patch release, so no function changed its name, its parameters, their defaults or what it
returns. The values of `sanshain.yaml` and the answers of the service are typed `Any`: they
are whatever the user or the service wrote. A rule is silenced at two lines, both in the
tests: a made-up token handed to the client (`S106`). flake8, black and bandit are gone
with `setup.cfg` and `requirements-dev.txt`; ruff covers the three.

**Format.** `ruff format` with 110 columns replaces black with 120. It also formats the
Python examples in the Markdown files.

**The tests.** They are `unittest` cases, as before, and pytest runs them: the gate measures
coverage through pytest. pytest collects the same tests `unittest discover` ran.

**Dependencies.** osv-scanner ran before, for advisories; it now also checks the licences,
decided by gates' `osv_gate.py`. Three packages are accepted in `osv-scanner.toml`
until 2027-02-18, none of them installed with the client: typing-extensions under Python's
licence, which mypy brings, and colorama and atheris, whose licences the registry record
states unclearly or not at all (3-clause BSD and Apache-2.0 by their licence files).

**Coverage.** One part, `python`, over every file in `sanshainconan/`, measured by the gate
with `pytest --cov`. The first floor is the measurement on Python 3.12 minus 0.1. SonarQube
Cloud reads the Cobertura file the gate wrote.

**Fuzz targets.** Four, with the names every Sanshain client uses, as Atheris scripts in
`fuzz/`: `fuzz_config.py` reads `sanshain.yaml` through `load_config`, `fuzz_annotations.py`
fills the placeholders of annotation values through `fill_annotations`, `fuzz_response.py`
reads an answer through `warning_lines` and the client's response handling,
`fuzz_state.py` reads the require state file through `SanshainCache` and `etag_for`. The
shared workflow passes no seed corpus, so each target runs its seed inputs once when it
starts, and `fuzz_config.py` puts one of six beginnings of a valid file before the fuzzer's
bytes, which leads it into the entries of the lists. The response target answers the
client's question for the version of the service itself, so no call leaves the process. The
scripts are left out of the source distribution; the wheel never held them.

**What the first runs found.** An entry of `provides` or `requires` that is no mapping, and
a `provides` or `requires` that is no list, ended in a `TypeError` or an `AttributeError` of
Python; they are configuration errors now, and an empty `provides:` or `requires:` holds no
entry. A value PyYAML cannot build, such as the date `2001-99-99`, and a file nested deeper
than Python follows, are YAML errors now, in `sanshain.yaml` and in an answer that should be
an OpenAPI document; a JSON answer nested that deeply is read as text. A state file that is no text, or whose entry for a require is no ETag
record, made every later require of that endpoint fail; such a file or entry now counts as
absent and the endpoint is fetched again.

**Accepted findings.** SonarQube Cloud reports three findings that are what the client is
for: it reads and writes the files the user names. `sonar-project.properties` used to
silence them; they are now accepted in `code-scanning-ignores.toml` until 2027-02-18, beside
the three Scorecard findings of a single maintainer.

**Release.** The workflow first checks that the tag names the version in `pyproject.toml`.
The shared release gate checks alerts, findings, vulnerabilities, licences and the changelog
section, and runs no tests; the release runs the tests itself before it builds, because a
version on PyPI cannot be replaced.

**What the release attaches.** The wheel and the source distribution, built once, with the
SBOM of the source, a build provenance attestation and its Sigstore bundle. Those same two
files are then published to PyPI by trusted publishing, with PyPI's own attestations; a
version that is already on PyPI is skipped.

**The old agent files.** `ai/rules.md` and `ai/plan.md` are gone. The rules that still hold
are in `AGENTS.md`: linters and tests green before a commit, uv for everything, types on
every function, a `timeout` on every `requests` call, no bare `except`, a reason for every
`subprocess` call. The rules for a `python_requires` recipe are dropped: the client has been
a plain PyPI package since 2.0. The sourcehut build file `.build.yml` is gone too; it ran
the tests a second time.

## Consequences

- A branch gets its CI run through its pull request; pushes run CI only on `summer`.
- SonarQube Cloud analyses pull requests as well as `summer`, and its quality gate now
  fails CI.
- `ruff format`, `ruff check` and strict mypy over the package, the tests and the fuzz
  targets fail CI; mypy ran without requiring types before and left the tests out.
- The gate, the fuzz run and the release run on Python 3.12; Python 3.11 is tested in a job
  of its own.
- osv-scanner also decides on licences.
- Fuzzing, CodeQL, Scorecard and the weekly Security run come from gates; the weekly run
  also fails on SonarQube Cloud findings and secret alerts.
- The release and the weekly Security run need the secret `GATES_ALERTS_TOKEN`, a
  fine-grained token that can read the repository's alerts
  ([sancon-1008](https://github.com/paxel/sanshain-conan/issues/19)).
- The release's SBOM and Sigstore bundle are named
  `sanshain-conan-<tag>-source.cdx.json` and `sanshain-conan-<tag>-provenance.sigstore.json`.
- The README badges of SonarQube Cloud's security rating and coverage and of the Python
  version are gone; the fixed row and the PyPI badge remain.
- No build runs on sourcehut any more.
