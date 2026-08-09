# PS5 Payload Source

Self-updating custom source for [PS5 Payload Manager (PLDMGR)](https://github.com/itsPLK/ps5-payload-manager).

## PLDMGR source URL

Use the **v2 source URL** below. It was introduced to bypass stale source caching from the original `payloads.json` URL:

```text
https://raw.githubusercontent.com/thatboialex/ps5-payload-source/main/payloads-v2.json
```

In Payload Manager, remove the old source that points to `payloads.json`, then add the v2 URL above. The source should display as **Jason's PS5 GitHub Payloads v2**.

## Catalog rules

- Only PLDMGR-loadable payload binaries are published in the catalog.
- `fetchpkg` and `pkg_install` have been removed from the catalog and their obsolete build workflow has been removed.
- ProsperoPlayer uses the official `KINGDKAK/ProsperoPlayer` v1.0 release asset `ProsperoPlayer_MediaLauncher.elf`.
- RetroArch PS5 and JTPlay remain tracked as package-style homebrew but are not exposed as standalone payloads because their ZIP bundles contain required supporting files.
- WBrowser remains tracked but is not exposed while upstream distributes PKG installers rather than a loadable ELF/BIN/LUA payload.

## Automatic updates

`.github/workflows/update-payloads.yml` runs every 6 hours and can also be run manually. It checks configured upstream GitHub releases, updates direct asset URLs and versions, calculates/records SHA-256 checksums, runs tests, and commits catalog changes.

`.github/workflows/mirror-elf-downloads.yml` mirrors every loadable ELF in the current catalog into the `pldmgr-elf-downloads` release. It verifies ELF headers and SHA-256 checksums, deletes stale release assets, verifies the exact release/catalog count, and keeps `payloads-v2.json` synchronized with `payloads.json`.

## Files

- `payloads.json` — internal generated PLDMGR catalog.
- `payloads-v2.json` — canonical fresh source URL for the PS5 Payload Manager.
- `sources.json` — tracked upstream projects and matching rules.
- `upstream_status.json` — diagnostic status for tracked projects.
- `mirror_status.json` — last verified ELF mirror count and canonical source URL.
- `self_built_sources.json` — source revision tracking for payloads that still require a self-hosted build.
- `scripts/update_payloads.py` — GitHub API updater.
- `.github/workflows/update-payloads.yml` — scheduled/manual catalog updater.
- `.github/workflows/mirror-elf-downloads.yml` — exact downloadable ELF mirror and v2 source synchronizer.
- `tests/test_updater.py` — catalog and asset-selection tests.
