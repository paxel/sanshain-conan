# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [2.4.0]

### Added
- `provide` sends the origin of the build: `--build-url` and `--change-url` default to the runner's own variables on GitHub Actions, GitLab CI and Jenkins (overridden by `SANSHAIN_BUILD_URL` / `SANSHAIN_CHANGE_URL`), plus `--tickets` / `SANSHAIN_TICKETS` and `--note` / `SANSHAIN_NOTE`; the Conan integration reads the environment. Sanshain Service 2.9.0 and later stores it with the version and shows it as "why"; an older service gets the provide without it, with a warning.

---

Historical changes have been moved to [OLDER_CHANGES.md](OLDER_CHANGES.md).
