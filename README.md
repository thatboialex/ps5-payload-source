# PS5 Payload Source

Self-updating custom source for [PS5 Payload Manager (PLDMGR)](https://github.com/itsPLK/ps5-payload-manager).

## PLDMGR source URL

After making this repository **public**, add this URL in **Payload Manager → Settings → Manage Sources → Add Source**:

```text
https://raw.githubusercontent.com/thatboialex/ps5-payload-source/main/payloads.json
```

## Tracked projects

| Project | Upstream | PLDMGR catalog behavior |
|---|---|---|
| CheatRunner | `notmaj0r/CheatRunner` | Published when `CheatRunner.elf` is available |
| Pegasus DL | `pegasus-ps5/pegasus-dl` | Published when `pegasus_dl.elf` is available |
| Kylin Core | `aydencharles/kylin-core-release` | Published when `kylin-core.elf` is available |
| Ghostpad | `StonedModder/Ghostpad` | Published when `ghostpad.elf` is available |
| WBrowser | `ps5xploit/WBrowser` | Tracked, but not published while upstream only provides PKG installers; automatically becomes eligible if a compatible ELF/BIN/LUA release asset appears |
| Save Sync PS-PC | `DIYTechnologist/SaveSyncPSPC` | Track-only PC companion app; release/version/assets are recorded in diagnostics but its Windows/Linux archives are never exposed to PLDMGR as PS5 payloads |

## Automatic updates

`.github/workflows/update-payloads.yml` runs every 6 hours and can also be run manually. It:

1. Calls GitHub's release API for each tracked repository. Payload projects use `releases/latest`; configured track-only projects can follow the newest published release including prereleases.
2. Selects the configured `.elf`, `.bin`, or `.lua` release asset for PLDMGR-compatible projects.
3. Updates the direct download URL and release version.
4. Uses GitHub's SHA-256 asset digest when available; otherwise downloads the asset and calculates SHA-256.
5. Records diagnostic release metadata for track-only/non-payload projects without adding incompatible files to `payloads.json`.
6. Runs unit tests.
7. Commits only if `payloads.json` or `upstream_status.json` actually changed.

The updater is fail-safe: if GitHub is temporarily unavailable or an expected asset disappears, a previously working payload entry is retained instead of being silently removed.

## Non-payload notes

### WBrowser

WBrowser currently documents Game and Media `.pkg` installers hosted outside GitHub. A PKG is not a PLDMGR payload, so it is tracked in `upstream_status.json` rather than being presented as a loadable payload. This prevents the source from offering a file PLDMGR cannot execute as a payload.

### Save Sync PS-PC

Save Sync PS-PC is a PC-side save bridge that communicates with Garlic Save Manager running on the PS5. Its GitHub Releases package Windows/Linux binaries as `.zip`/`.tar.gz` archives. Those releases are tracked in `upstream_status.json` (including prereleases), but are intentionally excluded from `payloads.json` because they are not PS5 payload binaries.

## Files

- `payloads.json` — the PLDMGR-compatible source file.
- `sources.json` — tracked upstream projects and matching rules.
- `upstream_status.json` — diagnostic status for all tracked projects, including non-payload projects.
- `scripts/update_payloads.py` — GitHub API updater.
- `.github/workflows/update-payloads.yml` — scheduled/manual updater workflow.
- `tests/test_updater.py` — catalog and asset-selection tests.
