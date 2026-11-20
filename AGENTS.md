# sanshain-conan

The Conan client of the [Sanshain Service](https://github.com/paxel/sanshain-service): one
PyPI package, `sanshain-conan`, that is the command `sanshain-conan` and the helper a
project's `conanfile.py` imports from `sanshainconan`.

| Path                           | What it is                                                              |
|--------------------------------|-------------------------------------------------------------------------|
| `sanshainconan/cli.py`         | The command: flags, the commands and what they print.                   |
| `sanshainconan/integration.py` | The helper `Sanshain` for a `conanfile.py`.                             |
| `sanshainconan/config.py`      | Reads and validates `sanshain.yaml`; finds the unknown fields.          |
| `sanshainconan/annotations.py` | Fills the annotation placeholders.                                      |
| `sanshainconan/client.py`      | The calls to the service, the wire payloads, the warnings of an answer. |
| `sanshainconan/cache.py`       | The require state file with the ETag of every require.                  |
| `sanshainconan/catalog.py`     | The catalog step the command and the helper share.                      |
| `sanshainconan/__init__.py`    | What the package exports.                                               |
| `tests/`                       | The tests, written as `unittest` cases and run by pytest.               |
| `fuzz/`                        | The Atheris fuzz targets.                                               |
| `docs/integration.md`          | The guide to the helper.                                                |

What users rely on is the command, its flags and variables, what it prints, its exit codes,
`sanshain.yaml`, the state file, and every function and class of `sanshainconan` with its
parameters, defaults, return values and exceptions. The user documentation lives on the
Sanshain site, in the repository of the service.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `paxel/sanshain-conan`, managed with the `gh` CLI. See
`docs/agents/issue-tracker.md`.

### Triage labels

Default canonical vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Ticket IDs

Prefix `sancon`, as in `sancon-1003`. See `docs/agents/ticket-ids.md`.

## Quality gates

The standard sanshain-conan is held to is [paxel/gates](https://github.com/paxel/gates);
`docs/adr/0001-move-to-gates.md` says where sanshain-conan adds to it and why. The workflows
call gates' shared workflows, pinned by commit; Dependabot moves the pin.

### Before a commit

A change is done only when the format check, the linter, the type check and the tests are
green, on the Python `.python-version` pins. uv installs and runs everything; nothing is
installed with pip. These are the commands of the shared Python gate:

```sh
uv sync --locked --no-build --no-binary-package sanshain-conan --all-extras --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest --cov --cov-report=lcov:coverage.lcov --cov-report=xml:coverage.xml
```

`ruff.toml` is the standard's rule selection; `[tool.mypy]` in `pyproject.toml` is strict
and checks against Python 3.11. Every function carries its types, in the package, the tests
and the fuzz targets. `requires-python` in `pyproject.toml` is the oldest Python the package
runs on, 3.11; CI runs the tests on it in a job of its own
(`UV_PYTHON=3.11 uv run pytest`). Do not use what Python 3.11 does not have.

### Coverage ratchet

Line coverage may only go up. The Python gate in `ci.yml` fails under the floor in
`coverage-floors.toml`. Every feature ships with tests that hold or raise coverage; a
feature that lowers it is not done. When coverage rises, raise the floor and the badge in
the same pull request, with gates checked out beside the repository:

```sh
uv run pytest --cov --cov-report=lcov:coverage.lcov --cov-report=xml:coverage.xml
mkdir -p coverage && cp coverage.lcov coverage/python.lcov
python3 ../gates/scripts/coverage_ratchet.py --floors coverage-floors.toml
```

Never lower the floor.

### Fuzzing

The fuzz targets are the scripts in `fuzz/`: `fuzz_config.py`, `fuzz_annotations.py`,
`fuzz_response.py` and `fuzz_state.py`; `fuzz.yml` runs them weekly. Each runs its seed
inputs once when it starts. Atheris installs on Python 3.12 and later only. One target by
hand: `uv run python fuzz/fuzz_config.py -max_total_time=30`

### Before a release

The commands of the gate, the tests on Python 3.11, osv-scanner with gates'
`scripts/osv_gate.py`, the coverage ratchet, and `uv build`, whose wheel holds the package
`sanshainconan` and nothing else. The version stands in `pyproject.toml` and `uv.lock`. The
release workflow runs the shared release gate and the tests on the tagged commit before it
builds.

### Security rules

The decisions behind these are in `docs/adr/0001-move-to-gates.md`.

- A finding of ruff or mypy is fixed in the code. One that must stay is silenced at its line
  with `# noqa: <rule> - <reason>` or `# type: ignore[<code>]  # <reason>`, never in
  `ruff.toml` or `pyproject.toml` and never without the reason. A public signature does not
  change to satisfy a rule.
- Every `requests` call carries a `timeout`.
- No bare `except:`. An `except Exception` stands only where any failure of one step becomes
  its message, with that reason beside it; everywhere else the exceptions are named.
- The package starts no process. A `subprocess` call needs its reason in a comment and a
  fixed argument list, never a shell.
- No dependency is built from its source archive: every install is
  `uv sync --locked --no-build`, with the project itself as the one exception.
- Every action in `.github/workflows/` is pinned to a full commit SHA with its version in
  a trailing comment. Never reference an action by tag or branch alone.
- Python is pinned in `.python-version`; the shared workflows and the release read it from
  there. A bump is a commit of its own.
- Every workflow starts with `permissions: contents: read`; a job that writes widens it
  itself.
- A dependency advisory is fixed by an update. When no fixed release exists, it is accepted
  in `osv-scanner.toml` with the reason sanshain-conan is not exposed and an `ignoreUntil`
  date. A licence outside the allowlist is accepted per package with `effectiveUntil`. Never
  ignore without reason and date.
- A code-scanning alert or a SonarQube Cloud finding that stays open is accepted in
  `code-scanning-ignores.toml` with its tool, rule, file, reason and an `ignoreUntil` date.
  Nothing is dismissed in GitHub or marked in SonarQube Cloud.
- The release fails on a known vulnerability, on every open code-scanning alert, secret
  alert and SonarQube Cloud finding that is not accepted, and on a missing `CHANGELOG.md`
  section for the version. The weekly Security run fails on the same, and on unmaintained
  dependencies and passed dates.
- `summer` takes pull requests only.
