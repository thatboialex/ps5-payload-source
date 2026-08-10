# PS5 Payload Source

Self-updating custom source for [PS5 Payload Manager (PLDMGR)](https://github.com/itsPLK/ps5-payload-manager), plus a SlopKit-based PS5 jailbreak host.

## PLDMGR source URL

Use the **v2 source URL** below. It was introduced to bypass stale source caching from the original `payloads.json` URL:

```text
https://raw.githubusercontent.com/thatboialex/ps5-payload-source/main/payloads-v2.json
```

In Payload Manager, remove the old source that points to `payloads.json`, then add the v2 URL above. The source should display as **Jason's PS5 GitHub Payloads v2**.

## PS5 SlopKit jailbreak host

The repository contains an automated PS5 jailbreak page built from the full upstream [jordyidk/slopkit](https://github.com/jordyidk/slopkit) host. The landing page and post-jailbreak payload menu use an idlesauce/UMTX2-inspired dark card layout.

Expected public URL:

```text
https://thatboialex.github.io/ps5-payload-source/
```

### One-time GitHub Pages setup

GitHub blocks first-time Pages enablement from the repository workflow token, so the repository owner must enable it once:

1. Open this repository on GitHub.
2. Go to **Settings** -> **Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Save/confirm the setting if GitHub presents a confirmation.
5. Run the **Publish PS5 SlopKit jailbreak page** workflow from the **Actions** tab, or make a relevant host/catalog change to trigger it.

After that one-time setting, `.github/workflows/publish-jailbreak-pages.yml` builds and deploys the site automatically.

### What the jailbreak page contains

- A **Jailbreak** button that enters the SlopKit exploit flow.
- **Payload Manager** pinned as the first payload.
- Every loadable payload currently in `payloads-v2.json`.
- Local copies of the ELF files inside the generated Pages artifact, validated for the ELF signature.
- A **Jailbreak + Load** action for each payload. The build patches SlopKit so the selected `autoload=<filename>` ELF is sent to SlopKit's localhost ELF loader after it becomes ready.
- Dynamic validation: the expected page payload count is always `1 + the current payloads-v2.json count`, so future payload additions do not require a hard-coded count change.

The build currently validates Payload Manager plus the full active PLDMGR catalog and rejects removed `fetchpkg` / `pkg_install` entries if they ever reappear.

## Catalog rules

- Only PLDMGR-loadable payload binaries are published in the catalog.
- `fetchpkg` and `pkg_install` have been removed from the catalog and their obsolete build workflow has been removed.
- ProsperoPlayer uses the official `KINGDKAK/ProsperoPlayer` v1.0 release asset `ProsperoPlayer_MediaLauncher.elf`.
- RetroArch PS5 and JTPlay remain tracked as package-style homebrew but are not exposed as standalone payloads because their ZIP bundles contain required supporting files.
- WBrowser remains tracked but is not exposed while upstream distributes PKG installers rather than a loadable ELF/BIN/LUA payload.

## Automatic updates

`.github/workflows/update-payloads.yml` runs every 6 hours and can also be run manually. It checks configured upstream GitHub releases, updates direct asset URLs and versions, calculates/records SHA-256 checksums, runs tests, and commits catalog changes.

`.github/workflows/mirror-elf-downloads.yml` mirrors every loadable ELF in the current catalog into the `pldmgr-elf-downloads` release. It verifies ELF headers and SHA-256 checksums, deletes stale release assets, verifies the exact release/catalog count, and keeps `payloads-v2.json` synchronized with `payloads.json`.

`.github/workflows/deploy-jailbreak-host.yml` also maintains a complete static `gh-pages` branch copy of the SlopKit host as a build/mirror artifact.

`.github/workflows/publish-jailbreak-pages.yml` is the canonical GitHub Pages deployment. It rebuilds the host from upstream SlopKit, bundles Payload Manager and the live payload catalog, validates every ELF and menu entry, uploads the Pages artifact, and deploys it through GitHub Pages.

## Files

- `payloads.json` — internal generated PLDMGR catalog.
- `payloads-v2.json` — canonical fresh source URL for the PS5 Payload Manager.
- `sources.json` — tracked upstream projects and matching rules.
- `upstream_status.json` — diagnostic status for tracked projects.
- `mirror_status.json` — last verified ELF mirror count and canonical source URL.
- `self_built_sources.json` — source revision tracking for payloads that still require a self-hosted build.
- `scripts/update_payloads.py` — GitHub API updater.
- `jailbreak-host/build_host.py` — SlopKit host builder and payload-menu patcher.
- `jailbreak-host/index.html` / `main.css` — idlesauce-inspired landing-page overlay.
- `.github/workflows/update-payloads.yml` — scheduled/manual catalog updater.
- `.github/workflows/mirror-elf-downloads.yml` — exact downloadable ELF mirror and v2 source synchronizer.
- `.github/workflows/deploy-jailbreak-host.yml` — static `gh-pages` branch builder/mirror.
- `.github/workflows/publish-jailbreak-pages.yml` — native GitHub Pages publisher.
- `tests/test_updater.py` — catalog and asset-selection tests.
