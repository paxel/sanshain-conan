# Sanshain Conan Plugin

[![CI](https://github.com/paxel/sanshain-conan/actions/workflows/ci.yml/badge.svg?branch=summer)](https://github.com/paxel/sanshain-conan/actions/workflows/ci.yml)
[![Security](https://github.com/paxel/sanshain-conan/actions/workflows/security.yml/badge.svg?branch=summer)](https://github.com/paxel/sanshain-conan/actions/workflows/security.yml)
[![CodeQL](https://github.com/paxel/sanshain-conan/actions/workflows/codeql.yml/badge.svg?branch=summer)](https://github.com/paxel/sanshain-conan/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/paxel/sanshain-conan/badge)](https://scorecard.dev/viewer/?uri=github.com/paxel/sanshain-conan)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=paxel_sanshain-conan&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=paxel_sanshain-conan)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fpaxel%2Fsanshain-conan%2Fsummer%2F.github%2Fbadges%2Fcoverage-python.json)](coverage-floors.toml)
[![Fuzz](https://github.com/paxel/sanshain-conan/actions/workflows/fuzz.yml/badge.svg?branch=summer)](https://github.com/paxel/sanshain-conan/actions/workflows/fuzz.yml)
[![Release](https://img.shields.io/github/v/release/paxel/sanshain-conan)](https://github.com/paxel/sanshain-conan/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[![PyPI](https://img.shields.io/pypi/v/sanshain-conan)](https://pypi.org/project/sanshain-conan/)

A Conan extension and command-line client for the [Sanshain Service](https://github.com/paxel/sanshain-service): a C or C++ project provides its API specifications (OpenAPI, AsyncAPI, gRPC/Proto) under the version declared in the spec file, and downloads the endpoint snippets it depends on, pinned to an exact version, during `conan install`.

**The documentation lives on the Sanshain site: [Conan client](https://paxel.github.io/sanshain-service/developer/clients/conan.html).** It lists every flag, variable and `sanshain.yaml` field with the version it arrived in, the precedence, what the [`conanfile.py` helper](https://paxel.github.io/sanshain-service/developer/clients/conan.html#conanfile) reads, the ETag state file, strict mode and best effort, the failure modes and CI recipes. The file itself is described in [`sanshain.yaml`](https://paxel.github.io/sanshain-service/developer/sanshain-yaml.html).

**Compatibility: sanshain-conan 2.x speaks Sanshain Service 2.x.** Python 3.11 or later.

## Install

Install from PyPI, into the same environment Conan runs in:

```bash
pip install sanshain-conan
```

## A minimal example

`sanshain.yaml` in the project root:

```yaml
serviceName: my-cpp-service
provides:
  - file: openapi.yaml            # the version is read from info.version
requires:
  - serviceName: other-service
    version: 1.2.0                # an exact pin
    outputDirectory: generated/sanshain
    endpoints:
      - method: GET
        path: /api/v1/user
```

The `conanfile.py` requires during `conan install`:

```python
from conan import ConanFile
from sanshainconan import Sanshain


class MyProject(ConanFile):
    def generate(self):
        Sanshain(self).require()  # writes generated/sanshain/other-service.yaml
```

The pipeline provides from the command line after the tests, with `SANSHAIN_URL` and `SANSHAIN_TOKEN` in the environment (flags go before the command):

```bash
sanshain-conan provide          # snapshot (the default)
sanshain-conan --ga provide     # immutable GA, from the release pipeline
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
