# Conan Integration Guide

This guide explains how to use `sanshain-conan` in your C++ projects.

`sanshain-conan` 2.x speaks Sanshain Service 2.x.

## Prerequisite

1.  A `sanshain.yaml` file in your project root, with each `requires` entry pinned to an exact `version`.
2.  `sanshain-conan` installed from PyPI into the environment Conan runs in:

```bash
pip install sanshain-conan
```

## Using in `conanfile.py`

Import the helper directly — the `python_requires` pattern is gone; it resolved
from a Conan remote, and the package ships on PyPI instead.

```python
from conan import ConanFile
from sanshainconan import Sanshain

class MyProject(ConanFile):
    def generate(self):
        # Initialize the helper
        sanshain = Sanshain(self)

        # Download all dependencies declared in sanshain.yaml
        sanshain.require()

        # Now you can use the downloaded files with a generator
        # e.g., openapi-generator-cli
```

## Methods

### `Sanshain(conanfile, config_path=None)`
Initializes the helper.
- `conanfile`: The current `ConanFile` instance (`self`).
- `config_path`: Optional path to `sanshain.yaml`. Defaults to project root.

### `sanshain.provide()`
Reads the `provide` section from `sanshain.yaml` and uploads the specification to the Sanshain service. The version is read from the spec file itself (`info.version`, or the `// sanshain-version:` comment for proto); the stability is `snapshot` unless `SANSHAIN_GA=true` is set.

### `sanshain.require()`
Reads the `requires` section from `sanshain.yaml` and downloads the specifications at each entry's pinned `version` to the specified output directories.

## CI/CD Integration

### Authentication
Ensure the `SANSHAIN_TOKEN` environment variable is set in your CI pipeline.

### Stability (the ga switch)
Every provide is a `snapshot` by default. Release pipelines mark their provides as `ga` by setting the switch explicitly:

- Environment variable: `SANSHAIN_GA=true`
- CLI flag: `--ga`

Set it only on protected-branch (release) pipelines. There is no git or branch detection — the switch is the whole mechanism.

## Typical Workflow

1.  `conan install .` (triggers `generate()` which calls `sanshain.require()`).
2.  Run OpenAPI generator on the downloaded `openapi.yaml` files.
3.  Build your C++ project.
4.  In CI, after tests pass, run `python3 -m sanshainconan.cli provide` to publish your own API (add `--ga` on the release pipeline).

## Failure Modes

- `404`: the producer or the pinned version does not exist — fix the `version` pin (list available versions: `GET /producers/<serviceName>/versions`).
- `410`: the pinned version exists but deliberately lacks the requested endpoint(s).
- `409` (provide): rejected by the version rules; the error names the `proposed_version` to publish as instead — update the version in your spec file and republish.
