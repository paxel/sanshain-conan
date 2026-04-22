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
    python_requires = "sanshain-conan/1.0.0"
    
    def build(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # require OpenAPI snippets
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
    python_requires = "sanshain-conan/1.0.0"
    
    def generate(self):
        sanshain = self.python_requires["sanshain-conan"].module.Sanshain(self)
        # Download required OpenAPI specs
        sanshain.require()
```

### CLI Tool

You can also use it as a standalone CLI:

```bash
# Provide (upload) spec
python3 -m sanshainconan.cli provide

# Require (download) specs
python3 -m sanshainconan.cli require
```

## Features
- **Automatic Branch Detection**: Supports Git, GitHub Actions, GitLab CI, and Jenkins.
- **Bundle Support**: Downloads merged OpenAPI specs for multiple endpoints.
- **Bearer Token Auth**: Uses `SANSHAIN_TOKEN` environment variable.
- **GZIP Support**: Efficiently downloads large specifications.

## License

This project is licensed under the GNU Affero General Public License (AGPL-3.0). See the [LICENSE](LICENSE) file for details.
