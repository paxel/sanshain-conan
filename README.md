# Sanshain Conan Plugin

A Conan extension to manage OpenAPI specifications during the C++ build process.

## Description
Sanshain Conan Plugin allows you to:
-   **Provide**: Upload your service's OpenAPI specification to the Sanshain service.
-   **Require**: Download OpenAPI snippets of other services to generate client code.

## Installation
Add the repository to your `conanfile.py` using `python_requires`:
```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/1.4.0"
    
    def generate(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # Download required OpenAPI specs (runs during `conan install`)
        sanshain.require()
        # proceed with client generation and build
```

## Configuration

The plugin uses the standard `sanshain.yaml` file in the project root:

```yaml
sanshainUrl: "https://sanshain.example.com"
serviceName: "my-cpp-service"

provides:
  - file: "openapi.yaml"

requires:
  - serviceName: "other-service"
    outputDirectory: "generated/sanshain"
    endpoints:
      - method: GET
        path: /api/v1/user
```

The `branch` is automatically detected from Git or common CI environment variables. It can be overridden via `SANSHAIN_BRANCH`.

## Usage

### Conan Integration

Add it as a `python_requires` in your `conanfile.py`:

```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/1.4.0"
    
    def generate(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # Download required OpenAPI specs (runs during `conan install`)
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
# Provide (upload) spec — run in CI after tests pass
python3 -m sanshainconan.cli provide

# Require (download) specs — alternative to generate() integration
python3 -m sanshainconan.cli require
```

## v0.14.0 Features

### Optimistic Concurrency Control (`baseVersion`)

Add `baseVersion` to your provide configuration to detect concurrent modifications:

```yaml
provides:
  - file: openapi.yaml
    baseVersion: 5
```

If the server version has advanced beyond your `baseVersion`, the provide call fails with:

> Concurrent modification detected. Server version has advanced beyond your base_version. Re-run to fetch the latest state.

The CLI automatically tracks the last known version in a local cache, so after the first successful provide, subsequent runs send the correct `base_version` automatically.

### Provide Response Summary

After each successful provide, the CLI logs a human-readable summary:

```
✓ Provided to Sanshain v5: 2 new, 1 updated, 0 deleted endpoints
```

### Client-Side Content Caching (Skip-if-unchanged)

Before uploading, the CLI computes the SHA-256 hash of the spec file and compares it with the cached hash from the last provide. If unchanged:

```
⏭ Spec unchanged (hash match), skipping provide.
```

### Require-Side ETag Caching

The CLI stores the `ETag` from require responses and sends `If-None-Match` on subsequent runs. On `304 Not Modified`:

```
⏭ user-service spec unchanged (304), skipping code generation.
```

### State File

The local cache is stored at `.sanshain-cache.json` in the current working directory. The format is:

```json
{
  "provides": {
    "openapi.yaml": {
      "content_hash": "sha256:abc123...",
      "version": 5,
      "last_provided": "2026-04-25T12:00:00Z"
    }
  },
  "requires": {
    "user-service|main|GET|/api/v1/users": {
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

## Features
- **Automatic Branch Detection**: Supports Git, GitHub Actions, GitLab CI, and Jenkins.
- **Bundle Support**: Downloads merged OpenAPI specs for multiple endpoints.
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
