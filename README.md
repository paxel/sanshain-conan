# Sanshain Conan Plugin

A Conan extension to manage API specifications (OpenAPI, AsyncAPI, gRPC/Proto) during the C++ build process.

**Compatibility: sanshain-conan 2.x speaks Sanshain Service 2.x. The `catalog` command needs Sanshain Service 2.4.0 or later; all other commands work with any 2.x service.**

## Description
Sanshain Conan Plugin allows you to:
-   **Provide**: Upload your service's API specification to the Sanshain service under the version declared in the spec file itself.
-   **Require**: Download API snippets of other services, pinned to an exact version, to generate client code.
-   **Catalog**: Push the project's Backstage `catalog-info.yaml`, so Sanshain's network graph shows the resources (databases, buckets, queues) the service depends on. Needs Sanshain Service 2.4.0 or later.

## The 2.0 model

Sanshain 2.0 replaced branches with producer-declared versions:

-   **The version lives in the spec file.** For OpenAPI/AsyncAPI it is read from `info.version`; proto files must carry a `// sanshain-version: MAJOR.MINOR.PATCH` comment. Strict three-part semver, no suffixes.
-   **Stability is declared on every provide.** Every provide is a `snapshot` (overwritable work-in-progress) unless the ga switch is set — then it is `ga` (immutable; the number is permanently claimed).
-   **Consumers pin exact versions.** Each `requires` entry names the exact `version` to build against. No ranges, no `latest`, no fallback, no waiting.

## Installation

Install from PyPI, into the same environment Conan runs in:

```bash
pip install sanshain-conan
```

Then import the helper directly in your `conanfile.py`:

```python
from conan import ConanFile
from sanshainconan import Sanshain

class MyProject(ConanFile):
    def generate(self):
        sanshain = Sanshain(self)
        # Download required API specs (runs during `conan install`)
        sanshain.require()
        # proceed with client generation and build
```

> The 1.x/2.0 `python_requires = "sanshain-conan/x.y.z"` pattern is gone — it
> resolved from a Conan remote, and the package now ships on PyPI instead.

## Configuration

The plugin uses the standard `sanshain.yaml` file in the project root:

```yaml
sanshainUrl: "https://sanshain.example.com"
serviceName: "my-cpp-service"
catalogInfo: "catalog-info.yaml"  # optional, pushed by the catalog command

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

Every relative path in `sanshain.yaml` (`file`, `openApiFile`, `asyncApiFile`, `protoFile`, `outputDirectory`, `catalogInfo`) resolves against the folder that contains `sanshain.yaml`, never the working directory; absolute paths stay absolute. A config passed via `--config` (CLI) or `config_path` (Conan helper) therefore finds the same files as one in the current folder.

`sanshain.yaml` carries **no stability and no version for provides** — the version travels inside the spec file (`MAJOR[.MINOR[.PATCH]]`, optionally `v`-prefixed; omitted parts are zero and the stored form is always three-part), and stability is decided by the ga switch (below). Branch-era fields (`branch`, `timeout`, `baseVersion`, `releaseBranches`) are rejected at parse time with a migration hint.

### `requires` entry fields

| Field             | Required | Description                                                                                   |
|-------------------|----------|-----------------------------------------------------------------------------------------------|
| `serviceName`     | yes      | The Producer to require from.                                                                 |
| `version`         | yes      | Exact pin, `MAJOR.MINOR.PATCH`.                                                               |
| `outputDirectory` | yes      | Where the spec is written, relative to `sanshain.yaml`.                                       |
| `endpoints`       | yes      | `method` + `path` pairs; several are downloaded as one bundle.                                |
| `apiType`         | no       | `openapi` (default), `asyncapi` or `proto`.                                                   |
| `format`          | no       | Only `openapi`, only with `apiType: asyncapi`: the AsyncAPI answer converted to OpenAPI.      |

### AsyncAPI as OpenAPI (`format`)

`format: openapi` on an `apiType: asyncapi` entry asks Sanshain for the required channels as an OpenAPI document, for generators that only speak OpenAPI. It is the only conversion; any other `format` value or `apiType` is a configuration error. The file keeps its usual name (`<serviceName>.yaml`), so to get both formats list the entry twice with different `outputDirectory`s:

```yaml
requires:
  - serviceName: "notifier"
    apiType: asyncapi
    version: "1.2.0"
    outputDirectory: "generated/asyncapi"
    endpoints:
      - method: PUB
        path: user/signup
  - serviceName: "notifier"
    apiType: asyncapi
    format: openapi
    version: "1.2.0"
    outputDirectory: "generated/openapi"
    endpoints:
      - method: PUB
        path: user/signup
```

`format` needs Sanshain Service 2.4.0 or later. An older service rejects the single-endpoint request or returns AsyncAPI; the client reports that it needs 2.4.0. The message is `format: openapi needs Sanshain Service 2.4.0 or later (server is <version>)` (a warning with best-effort, and nothing is written).

### Unknown fields

A field no Sanshain client knows — usually a typo — is reported once per run (CLI: on stderr; Conan helper: as warnings) and otherwise ignored:

```
   /\_/\  ?
  ( O_o )   sanshain.yaml: unknown field 'catalogInf' - ignored
 ---U-U---
```

With `strict: true` the same message ends in `rejected (strict)` and the command fails; `--best-effort` does not soften this. Fields other Sanshain clients support but this one does not (`force`, `insecure`, `combine`, `compression`) are accepted silently. The branch-era fields above keep failing with their migration hint.

## Environment

-   `SANSHAIN_URL` overrides `sanshainUrl` from `sanshain.yaml` (and makes it optional there), so the service address can change without a commit.
-   `SANSHAIN_TOKEN` is sent as the Bearer token.
-   The switches `SANSHAIN_GA`, `SANSHAIN_TRUNK` and `SANSHAIN_BEST_EFFORT` are on for `true` or `1` (trimmed, case-insensitive); any other value — `yes`, `on`, empty — is off. A CLI flag (`--ga`, `--trunk`, `--best-effort`) turns a switch on regardless of the environment.

## Streams: trunk and release branches

Alongside stability, the pipeline declares which dependency graph its calls belong to. Like the
ga switch this is a property of the invocation and never appears in `sanshain.yaml`:

- Trunk CI sets `SANSHAIN_TRUNK=true` (CLI: `--trunk`) — provides mark trunk's current version
  and requires feed the main graph.
- Release and hotfix pipelines set `SANSHAIN_TAG=<branch>` (CLI: `--tag`) — the calls update
  that sanshain-branch instead of trunk. The branch must already exist and is never created by a
  build; with an unknown one the call still succeeds but is recorded in no release graph, and Sanshain
  warns `no sanshain-branch '<name>' - this build was not recorded in a release graph`.

Declaring both is not an error either: the client warns
`trunk and tag are mutually exclusive - this build is recorded in neither` and sends neither, so the
build only feeds the dev graph. With `strict: true` it fails before any request is sent.

## Sanshain warnings

The dependency graph is informational and never fails a build. When Sanshain accepts a call but
could not record all of it, it says so in a `Sanshain-Warning` response header. Every such header
line is printed as a warning (CLI: `⚠ <text>`; Conan helper: `output.warning("Sanshain: <text>")`),
on provide, retire, require and catalog calls alike, also on failed calls. With `strict: true` a
warning fails the command after the call with `strict: Sanshain warned: <text>` (the first warning
of that call); `--best-effort` does not soften this.

## Retiring a protocol

Removing a `provides` entry tells Sanshain nothing — it cannot distinguish a dropped protocol
from a pipeline that stopped running. Keep the entry and mark it:

```yaml
provides:
  - apiType: asyncapi
    retired: true
```

The next provide retires that family: the capability tag is cleared, it leaves the current
dependency graph, and its AsyncAPI channel contracts are released. Version history and existing
Consumer pins are untouched. Retiring needs the `releaser` role — which a release pipeline
already holds — or a maintainer grant on the Producer; publishing GA needs `releaser` too, and
a `403` names the role and the snapshot fallback.

> ⚠️ **AsyncAPI 2.x perspective.** Sanshain reads 2.x `publish`/`subscribe` from the
> **application's** perspective: `publish` means *this service publishes to the channel*,
> `subscribe` means *this service consumes it*. The AsyncAPI 2.x specification defines those
> keywords from the **client's** perspective — exactly inverted. Sanshain deliberately uses the
> application-perspective reading because it matches the unambiguous 3.x `send`/`receive`
> mapping. A document authored with the spec-literal reading registers its contracts, and has
> its subscriptions harvested, exactly backwards. Harvested subscriptions are printed after
> every AsyncAPI provide; those with drift or no publisher yet are warnings and never fail the
> build.

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

Import the installed package in your `conanfile.py`:

```python
from conan import ConanFile
from sanshainconan import Sanshain

class MyProject(ConanFile):
    def generate(self):
        sanshain = Sanshain(self)
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

# Push catalog-info.yaml (needs Sanshain Service 2.4.0)
sanshain-conan catalog
```

The installed package also provides the `sanshain-conan` command; `sanshain-conan provide` is the same as `python3 -m sanshainconan.cli provide`.

## Catalog

`catalogInfo` in `sanshain.yaml` names the project's Backstage `catalog-info.yaml`. The `catalog` command (CLI: `sanshain-conan catalog`; Conan helper: `Sanshain(self).catalog()`) pushes it with `PUT /catalog/<serviceName>`. Sanshain reads only the `Component` whose `metadata.name` equals `serviceName`, and of it only the `resource:` refs in `spec.dependsOn`; each push replaces the previous set.

**Needs Sanshain Service 2.4.0 or later.** An older service answers `404`, reported as `sanshain catalog needs Sanshain Service 2.4.0 or later (server is <version>)`. Every other command works with any 2.x service.

-   A trunk build (`--trunk` / `SANSHAIN_TRUNK=true`) updates the main and the dev graph; any other build only the dev graph. A sanshain-branch (`--tag`) is not sent.
-   On success:

    ```
    Catalog recorded for orders-service (main+dev): 2 resources
      resource:default/orders-bucket
      resource:default/orders-db
    ```

-   Without `catalogInfo` the command warns `No catalogInfo in sanshain.yaml - skipping catalog.` and exits 0; with `strict: true` it fails. Strict checks only `serviceName` and `catalogInfo` here, never provides or requires.
-   A missing file fails naming the resolved path. With `--best-effort` (or `SANSHAIN_BEST_EFFORT` / `bestEffort: true`) every failed push is a warning and the command exits 0.
-   If Sanshain cannot read the file as this project's Component — invalid YAML, or usually a `metadata.name` that is not the `serviceName` — it records nothing (the previous periphery stays) and answers with a warning naming the reason, which is printed; the command exits 0. With `strict: true` it fails with `strict: Sanshain warned: <reason>`.

Add it as a CI step next to `provide`, e.g. on trunk:

```bash
SANSHAIN_TRUNK=true sanshain-conan catalog
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

By default, the CLI warns and skips when configuration is incomplete (no `serviceName`, no `provides`, no `requires`, no `catalogInfo` for `catalog`). This makes it safe to run both commands even if only one applies.

To fail on missing configuration, enable strict mode in `sanshain.yaml`:

```yaml
strict: true
```

When strict mode is enabled:
- Missing `serviceName` → exit with error
- No `provides` configured → exit with error
- No `requires` configured → exit with error
- `catalog` without `catalogInfo` → exit with error (`catalog` checks only `serviceName` and `catalogInfo`)
- An unknown field in `sanshain.yaml` → exit with error (see [Unknown fields](#unknown-fields))
- A `Sanshain-Warning` from the service (see [Sanshain warnings](#sanshain-warnings)) → exit with error after the call, also with `--best-effort`
- Both trunk and tag declared → exit with error before any request

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
