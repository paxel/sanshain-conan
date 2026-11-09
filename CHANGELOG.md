# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [2.5.0]

### Added
- `autoGa: true` in `sanshain.yaml` makes a provide GA whenever the build declares trunk or a tag (CLI and Conan integration); `SANSHAIN_GA=false` keeps such a build a snapshot.
- `annotations` in `sanshain.yaml` travel with provide, require, bundle and catalog push, their `{{NAME}}` placeholders filled from `--set NAME=value` or `SANSHAIN_SET_NAME` (needs Sanshain Service 2.13.0 or later).

### Fixed
- A failed `require()` in the `conanfile.py` helper with `bestEffort: true` now warns `Sanshain: Continuing (best effort)` and goes on; before, it stopped `conan install` with an `AttributeError` (`output.warn` does not exist in Conan 2).
- A require with `apiType: grpc` is saved as `.proto` (it was `.yaml`) by the CLI and the `conanfile.py` helper, and its bundle sends `api_type: proto`, the spelling the service's contract names.
- Best effort softens failed calls only, the same in provide, require and catalog: an unreadable or invalid `sanshain.yaml` (1.x fields and an unsupported provide `apiType` included) now fails also with best effort, and a failed provide no longer stops the next `provides` entry, in the CLI and in the `conanfile.py` helper's `provide()`, which softened nothing before.
- A `403` on provide or retire names the releaser role only when the service refused for want of it; any other `403`, such as a read-only token's, shows the service's message alone.
- The require ETag cache in `.sanshain-cache/state.json` is kept per output directory: the same endpoint required into two directories is written to both instead of the second getting a `304` and staying empty, and a deleted output file is fetched again instead of being skipped.
- An unknown `requires[].apiType` fails as a configuration error when `sanshain.yaml` is loaded, before any call; it was sent to `/require` as OpenAPI.
- A `sanshain.yaml` that holds no mapping of settings (a plain string, a number, a list) fails naming the file, in the CLI and the `conanfile.py` helper; it failed with a Python `AttributeError` such as `'str' object has no attribute 'get'`.
- `Sanshain(self)` without `config_path` falls back to the recipe's `source_folder` when it has neither an export-sources nor a recipe folder; it named `base_folder`, which Conan 2's `ConanFile` lacks, and failed with an `AttributeError`.
- The build, release and security workflows pin every action to a full commit SHA; they referenced tags and a branch.

---

Historical changes have been moved to [OLDER_CHANGES.md](OLDER_CHANGES.md).
