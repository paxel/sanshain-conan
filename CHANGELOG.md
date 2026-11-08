# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [2.5.0]

### Added
- `autoGa: true` in `sanshain.yaml` makes a provide GA whenever the build declares trunk or a tag (CLI and Conan integration); `SANSHAIN_GA=false` keeps such a build a snapshot.
- `annotations` in `sanshain.yaml` travel with provide, require, bundle and catalog push, their `{{NAME}}` placeholders filled from `--set NAME=value` or `SANSHAIN_SET_NAME` (needs Sanshain Service 2.13.0 or later).

### Fixed
- A failed `require()` in the `conanfile.py` helper with `bestEffort: true` now warns `Sanshain: Continuing (best effort)` and goes on; before, it stopped `conan install` with an `AttributeError` (`output.warn` does not exist in Conan 2).

---

Historical changes have been moved to [OLDER_CHANGES.md](OLDER_CHANGES.md).
