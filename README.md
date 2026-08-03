# Sanshain Conan Plugin

A Conan extension to manage API specifications (OpenAPI, AsyncAPI, gRPC/Proto) during the C++ build process.

**Compatibility: sanshain-conan 2.x speaks Sanshain Service 2.x.**

## Description
Sanshain Conan Plugin allows you to:
-   **Provide**: Upload your service's API specification to the Sanshain service under the version declared in the spec file itself.
-   **Require**: Download API snippets of other services, pinned to an exact version, to generate client code.

## The 2.0 model

Sanshain 2.0 replaced branches with producer-declared versions:

-   **The version lives in the spec file.** For OpenAPI/AsyncAPI it is read from `info.version`; proto files must carry a `// sanshain-version: MAJOR.MINOR.PATCH` comment. Strict three-part semver, no suffixes.
-   **Stability is declared on every provide.** Every provide is a `snapshot` (overwritable work-in-progress) unless the ga switch is set — then it is `ga` (immutable; the number is permanently claimed).
-   **Consumers pin exact versions.** Each `requires` entry names the exact `version` to build against. No ranges, no `latest`, no fallback, no waiting.

## Installation
Add the repository to your `conanfile.py` using `python_requires`:
```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/2.0.0"

    def generate(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # Download required API specs (runs during `conan install`)
        sanshain.require()
        # proceed with client generation and build
```

## Configuration

The plugin uses the standard `sanshain.yaml` file in the project root:

```yaml
sanshainUrl: "https://sanshain.example.com"
serviceName: "my-cpp-service"

provides:
  - file: "openapi.yaml"        # version read from its info.version

requires:
  - serviceName: "other-service"
    version: "1.2.0"            # exact pin (MAJOR.MINOR.PATCH)
    outputDirectory: "generated/sanshain"
    endpoints:
      - method: GET
        path: /api/v1/user
```

`sanshain.yaml` carries **no stability and no version for provides** — the version travels inside the spec file, and stability is decided by the ga switch (below). Branch-era fields (`branch`, `timeout`, `baseVersion`, `releaseBranches`) are rejected at parse time with a migration hint.

## Stability: the ga switch

Every provide is a `snapshot` by default — a developer building locally can never accidentally release. `ga` is an explicit act:

-   Environment variable: `SANSHAIN_GA=true` (works for the CLI and the Conan integration)
-   CLI flag: `--ga`

CI sets the switch on its protected-branch pipelines; that is the whole mechanism. There is no git detection and no branch matching.

```bash
# Local / feature pipeline: snapshot
python3 -m sanshainconan.cli provide

# Release pipeline: ga
python3 -m sanshainconan.cli --ga provide
# or: SANSHAIN_GA=true python3 -m sanshainconan.cli provide
```

## Usage

### Conan Integration

Add it as a `python_requires` in your `conanfile.py`:

```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/2.0.0"

    def generate(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # Download required API specs (runs during `conan install`)
        sanshain.require()
```

> **Why `generate()` and not `build()`?**
>
> Conan [best practice](https://docs.conan.io/2/knowledge/guidelines.html) recommends keeping
> `build()` simple — it should only compile. The `generate()` method runs during `conan install`
> and is designed to prepare all build inputs (toolchain files, downloaded specs, generated code).
> Placing `require()` in `generate()` means developers can run `conan install .` followed by a
> native build (e.g., `cmake --build .`) without needing Conan during the actual compilation step.
>
> **Why is `provide()` not in a Conan lifecycle method?**
>
> Uploading your API spec to Sanshain is a **publish** action with side effects — it should only
> happen once after tests pass, typically as a CI step. Use the CLI:

### CLI Tool

```bash
# Provide (upload) spec — run in CI after tests pass; add --ga on release pipelines
python3 -m sanshainconan.cli provide

# Require (download) specs — alternative to generate() integration
python3 -m sanshainconan.cli require
```

## Provide Response Summary

After each successful provide, the CLI logs a human-readable summary:

```
✓ Provided 1.4.0 (snapshot): 2 new, 1 updated, 0 deleted endpoints
```

Re-providing byte-identical content is a no-op on the server (`changes` reports all zero), so CI re-runs of the same commit never fight.

## Failure Modes

The 2.0 server fails immediately — nothing waits:

-   **`404` Unknown**: the producer or the pinned version does not exist (in either stability). A configuration error — fix the `version` pin. List what exists: `GET /producers/<serviceName>/versions`.
-   **`410` Absent**: the pinned version exists but deliberately does not include the requested endpoint(s).
-   **`409` Version conflict** (provide): rejected by the version rules — e.g. re-providing an existing GA version with different content. The CLI surfaces the server's message and the proposed next free version:

    ```
    ✗ Version conflict: GA 1.2.0 is immutable
      Publish as 1.3.0 — update info.version in specs/openapi.yaml
    ```

    The plugin never modifies your spec files — bump the version yourself and republish.

-   **Wrong server**: if a provide/require fails and the instance turns out to be pre-2.0, the confusing error is replaced with `Sanshain server at <url> is <version>; this client requires Sanshain 2.x — upgrade the server.`

## Require-Side ETag Caching

The CLI stores the `ETag` from require responses and sends `If-None-Match` on subsequent runs. On `304 Not Modified`:

```
⏭ user-service spec unchanged (304), skipping code generation.
```

A pin on a GA version can never change content; a pin on a snapshot can — which is exactly what the ETag detects.

### State File

The local cache is stored at `.sanshain-cache/state.json` in the current working directory. The format is:

```json
{
  "requires": {
    "user-service|1.2.0|GET|/api/v1/users": {
      "etag": "\"sha256:def456...\"",
      "last_fetched": "2026-04-25T12:00:00Z"
    }
  }
}
```

## Strict Mode

By default, the CLI warns and skips when configuration is incomplete (no `serviceName`, no `provides`, no `requires`). This makes it safe to run both commands even if only one applies.

To fail on missing configuration, enable strict mode in `sanshain.yaml`:

```yaml
strict: true
```

When strict mode is enabled:
- Missing `serviceName` → exit with error
- No `provides` configured → exit with error
- No `requires` configured → exit with error

Note that a `requires` entry without a `version`, or any leftover branch-era field, is always a hard error — strict mode does not change that.

## Features
- **Exact Version Pins**: Requires resolve immediately against the pinned version — GA preferred, else the same-numbered snapshot, else failure.
- **Bundle Support**: Downloads merged API specs for multiple endpoints with deduplicated schemas.
- **Bearer Token Auth**: Uses `SANSHAIN_TOKEN` environment variable.
- **GZIP Support**: Efficiently downloads large specifications.

## Development

### Local Development with uv

It is recommended to use [uv](https://github.com/astral-sh/uv) for managing the development environment.

1.  **Install uv**:
    Follow the [official installation guide](https://github.com/astral-sh/uv#installation).

2.  **Sync environment**:
    ```bash
    uv sync --dev
    ```

3.  **Run tests**:
    ```bash
    uv run python -m unittest discover tests
    ```

4.  **Linting and Checks**:
    ```bash
    uv run flake8 .
    uv run black --check .
    uv run bandit -r .
    uv run mypy .
    ```

5.  **Running Tools without Install (uvx)**:
    ```bash
    uvx black .
    ```

### Traditional Installation

If you prefer `pip`, you can still use it:

1.  **Install dependencies**:
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run tests**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    python3 -m unittest discover tests
    ```

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
