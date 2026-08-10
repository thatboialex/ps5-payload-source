# PS5 SlopKit jailbreak host

This directory contains the custom presentation/build layer for the GitHub Pages host.

The deployment workflow:

1. Clones `jordyidk/slopkit` at its current `main` commit.
2. Copies the full upstream host into the generated site.
3. Downloads every ELF from `payloads-v2.json` and validates its ELF header and SHA-256.
4. Adds the latest official `itsPLK/ps5-payload-manager` `pldmgr.elf` release asset.
5. Replaces SlopKit's small built-in payload menu with the generated catalog.
6. Publishes the complete static host to the `gh-pages` branch and GitHub Pages.

The upstream exploit code is kept intact except for the generated payload menu, auto-load hook, visual styling, and payload-size cap needed to support the larger catalog files.
