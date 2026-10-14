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

An unknown field in `sanshain.yaml` (usually a typo) is reported as a warning; with `strict: true` the helper raises instead.

Relative paths in `sanshain.yaml` (the spec `file`s, `outputDirectory`) resolve against the folder `sanshain.yaml` was loaded from; absolute paths stay absolute.

### `sanshain.provide()`
Reads the `provide` section from `sanshain.yaml` and uploads the specification to the Sanshain service. The version is read from the spec file itself (`info.version`, or the `// sanshain-version:` comment for proto); the stability is `snapshot` unless `SANSHAIN_GA=true` is set.

### `sanshain.require()`
Reads the `requires` section from `sanshain.yaml` and downloads the specifications at each entry's pinned `version` to the specified output directories.

An `apiType: asyncapi` entry with `format: openapi` downloads the channels as an OpenAPI document instead, under the same file name (list the entry twice with different `outputDirectory`s for both formats). `format` accepts only `openapi`, only with `apiType: asyncapi`, and needs Sanshain Service 2.4.0 or later.

### `sanshain.catalog()`
Pushes the file named by `catalogInfo` in `sanshain.yaml` (the project's Backstage `catalog-info.yaml`, relative to `sanshain.yaml`) to Sanshain with `PUT /catalog/<serviceName>`. **Needs Sanshain Service 2.4.0 or later**; all other methods work with any 2.x service. Without `catalogInfo` it warns and skips (with `strict: true` it raises). A rejected push raises — a `400` usually means the Component's `metadata.name` is not the `serviceName` — or only warns with `bestEffort: true`. `SANSHAIN_TRUNK=true` updates the main graph as well as the dev graph.

## CI/CD Integration

### Authentication
Ensure the `SANSHAIN_TOKEN` environment variable is set in your CI pipeline.

### Service URL
`SANSHAIN_URL` overrides `sanshainUrl` from `sanshain.yaml`.

### Switches
`SANSHAIN_GA` and `SANSHAIN_TRUNK` (and `SANSHAIN_BEST_EFFORT` for the CLI) are on for `true` or `1`, trimmed and case-insensitive; any other value is off.

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
5.  Optionally, in CI, run `sanshain-conan catalog` to push `catalog-info.yaml` (needs Sanshain Service 2.4.0).

## Failure Modes

- `404`: the producer or the pinned version does not exist — fix the `version` pin (list available versions: `GET /producers/<serviceName>/versions`).
- `410`: the pinned version exists but deliberately lacks the requested endpoint(s).
- `409` (provide): rejected by the version rules; the error names the `proposed_version` to publish as instead — update the version in your spec file and republish.
