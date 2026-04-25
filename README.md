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
    python_requires = "sanshain-conan/1.3.0"
    
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
    python_requires = "sanshain-conan/1.3.0"
    
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

## v0.13.0 Features

- **Optimistic Concurrency Control**: Add `baseVersion` to your provide config for conflict detection.
- **Provide Response**: Logs a summary after each provide (e.g., `✓ Provided to Sanshain v5: 2 new, 1 updated, 0 deleted endpoints`).
- **Client-Side Content Caching**: Skips provide if spec file SHA-256 hash is unchanged.
- **Require-Side ETag Caching**: Sends `If-None-Match` on subsequent requires, skips file writes on `304 Not Modified`.

## Features
- **Automatic Branch Detection**: Supports Git, GitHub Actions, GitLab CI, and Jenkins.
- **Bundle Support**: Downloads merged OpenAPI specs for multiple endpoints.
- **Bearer Token Auth**: Uses `SANSHAIN_TOKEN` environment variable.
- **GZIP Support**: Efficiently downloads large specifications.

## License

This project is licensed under the GNU Affero General Public License (AGPL-3.0). See the [LICENSE](LICENSE) file for details.
