# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [2.5.1]

### Added
- The release on GitHub carries the wheel and the source distribution, the files PyPI holds, with a CycloneDX SBOM of the source, a build provenance attestation and its Sigstore bundle; `gh attestation verify <file> -R paxel/sanshain-conan` checks a download. The files on PyPI carry PyPI's own attestations ([sancon-1005](https://github.com/paxel/sanshain-conan/issues/16)). Apart from the fixes below, the command and the `conanfile.py` helper behave as in 2.5.0.

### Fixed
- An entry of `provides` or `requires` in `sanshain.yaml` that is not a mapping, such as an empty `-`, a `provide` that is not a mapping, and a `provides` or `requires` that is not a list fail as a configuration error naming the place, for example `provides[0]: must be an entry with a file` or `requires must be a list of entries`. They ended in a Python error such as `argument of type 'NoneType' is not iterable`; `load_config` and the `conanfile.py` helper now raise `ConfigError` there. An empty `provides:` or `requires:` holds no entry; it failed the same way ([sancon-1003](https://github.com/paxel/sanshain-conan/issues/14)).
- A `sanshain.yaml` with a value YAML cannot build, such as the date `2001-99-99`, or nested deeper than Python follows, fails with `Failed to parse YAML: <reason>`, as a `ConfigError`; it failed with the bare reason, such as `month must be in 1..12`, as a `ValueError` or `RecursionError` in the helper. With `format: openapi`, such an answer of the service counts as no OpenAPI document and gets the message for that ([sancon-1003](https://github.com/paxel/sanshain-conan/issues/14)).
- A require state file (`.sanshain-cache/state.json`) that is not text or is nested too deeply counts as empty, and an entry in it that is not an ETag record, such as a number, counts as absent: the endpoint is fetched again and the entry rewritten. Before, every require of that endpoint failed until the file was deleted ([sancon-1003](https://github.com/paxel/sanshain-conan/issues/14)).

---

Historical changes have been moved to [OLDER_CHANGES.md](OLDER_CHANGES.md).
