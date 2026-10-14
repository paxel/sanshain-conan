# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [2.2.0] - Unreleased

### Added
- `catalog` command (`sanshain-conan catalog`, or `Sanshain(self).catalog()` in a conanfile) pushes the Backstage `catalog-info.yaml` named by the new `catalogInfo` field in `sanshain.yaml` to Sanshain. `catalog` requires Sanshain Service 2.4.0; all other commands work with any 2.x service.
- `SANSHAIN_URL` overrides `sanshainUrl` from `sanshain.yaml`, which may then be omitted.
- `format: openapi` on an `apiType: asyncapi` requires entry downloads the AsyncAPI channels as an OpenAPI document; needs Sanshain Service 2.4.0.
- Unknown fields in `sanshain.yaml` (usually typos) are reported by name and ignored; with `strict: true` they fail the command.

### Changed
- The Conan helper resolves relative paths in `sanshain.yaml` (spec files, `outputDirectory`) against the folder `sanshain.yaml` was loaded from, instead of the recipe or export-sources folder.
- `SANSHAIN_GA`, `SANSHAIN_TRUNK` and `SANSHAIN_BEST_EFFORT` accept `true` or `1`, trimmed and case-insensitive (`TRUE`, ` true `); any other value is off.

### Fixed
- `require` writes the downloaded spec byte for byte: no newline translation on Windows, and non-ASCII characters are no longer garbled when the server names no charset.

---

Historical changes have been moved to [OLDER_CHANGES.md](OLDER_CHANGES.md).
