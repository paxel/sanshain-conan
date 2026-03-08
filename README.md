# SanShain Conan Plugin

A Conan extension to manage OpenAPI specifications during the C++ build process.

## Description
SanShain Conan Plugin allows you to:
-   **Provide**: Upload your service's OpenAPI specification to the SanShain service.
-   **Require**: Download OpenAPI snippets of other services to generate client code.

## Installation
Add the repository to your `conanfile.py` using `python_requires`:
```python
from conan import ConanFile

class MyProject(ConanFile):
    python_requires = "sanshain-conan/0.1.0"
    
    def build(self):
        sanshain = self.python_requires["sanshain-conan"].module.SanShain(self)
        # require OpenAPI snippets
        sanshain.require()
        # proceed with client generation and build
```

## Configuration
The plugin can be configured via a `sanshain.yaml` file in the project root:
```yaml
sanshainUrl: "http://sanshain.example.com"
provide:
  serviceName: "my-cpp-service"
  openApiFile: "openapi.yaml"
require:
  - clientName: "my-cpp-client"
    requirements:
      - serviceName: "other-service"
        branch: "main"
        path: "/api/v1/user"
        method: "GET"
    outputDirectory: "generated/sanshain"
    timeout: 300
    retryInterval: 10
```

## Features
-   **Automatic Branch Detection**: Automatically detects the current Git branch.
-   **Retry Mechanism**: Waits for required OpenAPI definitions if they are not yet available.
-   **YAML Support**: Uses the same `sanshain.yaml` as the Maven plugin.

## License
AGPL-3.0 - See the `LICENSE` file for more details.
