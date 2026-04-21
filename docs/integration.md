# Conan Integration Guide

This guide explains how to use `sanshain-conan` in your C++ projects.

## Prerequisite

1.  A `sanshain.yaml` file in your project root.
2.  `sanshain-conan` exported to your local Conan cache or available in a remote.

```bash
# Export the plugin locally
conan export .
```

## Using in `conanfile.py`

To use the plugin, declare it in `python_requires` and call the `Sanshain` helper.

```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/0.1.0"
    
    def generate(self):
        # Initialize the helper
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        
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
Reads the `provide` section from `sanshain.yaml` and uploads the specification to the Sanshain service.

### `sanshain.require()`
Reads the `requires` section from `sanshain.yaml` and downloads the merged specifications to the specified output directories.

## CI/CD Integration

### Authentication
Ensure the `SANSHAIN_TOKEN` environment variable is set in your CI pipeline.

### Branch Detection
The plugin automatically detects the branch name in common CI environments:
- GitHub Actions (`GITHUB_REF_NAME`)
- GitLab CI (`CI_COMMIT_REF_NAME`)
- Jenkins (`GIT_BRANCH`)

You can override it by setting `SANSHAIN_BRANCH`.

## Typical Workflow

1.  `conan install .` (triggers `generate()` which calls `sanshain.require()`).
2.  Run OpenAPI generator on the downloaded `openapi.yaml` files.
3.  Build your C++ project.
4.  In CI, after tests pass, run `python3 -m sanshainconan.cli provide` to publish your own API.
