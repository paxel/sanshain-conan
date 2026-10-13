# Older Changes

This file contains historical changelog entries for sanshain-conan.
For recent changes, see [CHANGELOG.md](CHANGELOG.md).

## [2.1.0] - 2026-08-14

### Added
- Installable from PyPI (`pip install sanshain-conan`): import the helper with `from sanshainconan import Sanshain`, and run the CLI as `sanshain-conan`.
- Streams: `--trunk` / `SANSHAIN_TRUNK=true` marks a trunk build, `--tag` / `SANSHAIN_TAG=<branch>` a sanshain-branch build; declaring both fails before any request is sent.
- A `provides` entry with `retired: true` (and only an `apiType`) retires that API family on the next provide.
- Harvested AsyncAPI subscriptions are listed after each provide; those with drift or no publisher yet are warnings.
- A `403` names the `releaser` role or maintainer grant it needs and the snapshot fallback.

### Removed
- The `python_requires = "sanshain-conan/x.y.z"` integration; the package is no longer served from a Conan remote.

### Fixed
- Spec files with Windows (CRLF) line endings no longer cause spurious `409` version conflicts.

## [2.0.0] - 2026-08-03

### Added
- Every provide is a `snapshot` unless the ga switch is set (`--ga` or `SANSHAIN_GA=true`), which publishes it as immutable `ga`.
- A `409` version conflict shows the server's message and the next free version to publish as, naming the spec file to update.
- A failing call against a pre-2.0 server reports that the server must be upgraded.
- Distinct messages for `404` (unknown producer or version) and `410` (version lacks the requested endpoints).
- `--best-effort` and `SANSHAIN_BEST_EFFORT=true` turn failures, including an unreadable `sanshain.yaml`, into warnings.

### Changed
- Requires Sanshain Service 2.x.
- The provided version is read from the spec file (`info.version`, or a `// sanshain-version:` comment for proto).
- Each `requires` entry must pin an exact `version`.
- The provide summary shows the published version and stability.

### Removed
- Branch detection from git and CI variables, and `SANSHAIN_BRANCH`.
- The `branch`, `timeout` and `baseVersion` fields; they are rejected with a migration hint (as is `releaseBranches`).
- The CLI's skip of unchanged spec files on provide.

### Fixed
- The Conan helper's `require()` saves the downloaded specs again.

## [1.4.0] - 2026-04-26

### Changed
- Licensed under the Apache License 2.0 instead of AGPL-3.0; the Conan package includes the `LICENSE` file.

### Fixed
- Calls to the server time out (30 seconds for provides, the configured `timeout` for requires) instead of hanging indefinitely.

## [1.3.0] - 2026-04-25

### Added
- `baseVersion` on a provide entry detects concurrent modifications; the CLI remembers the last provided version and sends it automatically.
- The CLI prints a summary after each provide (version and new, updated and deleted endpoints).
- The CLI skips a provide whose spec file is unchanged since the last provide.
- The CLI skips downloading a required spec that is unchanged since the last run (ETag, `304 Not Modified`); the state is kept in `.sanshain-cache/state.json`.
- `strict: true` makes a missing `serviceName`, `provide` or `requires` configuration fail the command.

### Changed
- Without `strict`, the CLI warns and skips when `serviceName`, `provide` or `requires` is missing instead of failing; `serviceName` is no longer required in `sanshain.yaml`.

## [1.2.0] - 2026-04-23

### Added
- Branch detection for Bitbucket Pipelines, Azure DevOps, Travis CI, CircleCI and Jenkins `BRANCH_NAME`.
- On a detached HEAD the branch is resolved from the branches containing the commit.

### Changed
- Pull and merge request builds use the source branch (GitHub `GITHUB_HEAD_REF`, GitLab `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME`); GitLab branch builds read `CI_COMMIT_BRANCH`.

### Fixed
- Jenkins branch names no longer carry the `origin/` prefix.

## [1.1.0] - 2026-04-22

### Added
- `--insecure` CLI flag allows connections to servers with untrusted TLS certificates.

### Changed
- A failed call reports the server's status and response body.

### Fixed
- Provides and requires always name their API type (`openapi` by default) instead of relying on the server's fallback.
- A provide no longer fails when the server answers with a non-JSON body.

## [1.0.0] - 2026-04-22

### Added
- AsyncAPI and proto support: `provides` list with `file` and `apiType` (`openapi`, `asyncapi`, `proto`), the `asyncApiFile` and `protoFile` shortcuts, and `apiType` on `requires` entries.
- `bestEffort: true` continues past failed provides and requires.

### Changed
- `serviceName` moves from the `provide` section to the top level of `sanshain.yaml`; `clientName` is still accepted.
- Required specs are saved as `<serviceName>.yaml` (`.proto` for proto) instead of `openapi.yaml`.
- The Conan helper's `provide()` fails on a missing spec file instead of only logging it.

## [0.1.1] - 2026-04-21

### Added
- Conan `python_requires` helper `Sanshain` with `provide()` and `require()`.
- CLI `python3 -m sanshainconan.cli provide|require`, reading `sanshain.yaml` (or `--config`).
- Provide uploads an OpenAPI spec; require downloads endpoint snippets, merged into one bundle for several endpoints.
- The branch is detected from `SANSHAIN_BRANCH`, CI variables or git.
- Bearer token authentication via `SANSHAIN_TOKEN`, and gzip-compressed downloads.
