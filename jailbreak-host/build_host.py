#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import shutil
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "jailbreak-host"
CATALOG = ROOT / "payloads-v2.json"
SITE = pathlib.Path(os.environ.get("SITE_DIR", ROOT / "_site"))
UPSTREAM = pathlib.Path(os.environ.get("UPSTREAM_DIR", ROOT / "_upstream"))
USER_AGENT = "thatboialex-ps5-jailbreak-host/2.1"
PLDMGR_API = "https://api.github.com/repos/itsPLK/ps5-payload-manager/releases/latest"
UPSTREAM_RUN_QUERY = "slopkit/poops.html?go=1&auto=1&trigger=netcontrol&payload=1&v=17"
CUSTOM_RUN_QUERY = "original/slopkit/poops.html?go=1&auto=1&trigger=netcontrol&payload=1&v=17"


def api_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.load(r)


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def verify_elf(name: str, data: bytes, expected: str | None = None):
    if len(data) < 4 or data[:4] != b"\x7fELF":
        raise RuntimeError(f"{name}: downloaded file is not an ELF")
    actual = hashlib.sha256(data).hexdigest()
    if expected and actual.lower() != expected.lower():
        raise RuntimeError(f"{name}: checksum mismatch: expected {expected}, got {actual}")
    return actual


def latest_pldmgr():
    release = api_json(PLDMGR_API)
    assets = [a for a in release.get("assets", []) if isinstance(a, dict)]
    asset = next((a for a in assets if str(a.get("name", "")).lower() == "pldmgr.elf"), None)
    if asset is None:
        elf_assets = [a for a in assets if str(a.get("name", "")).lower().endswith(".elf")]
        if len(elf_assets) != 1:
            raise RuntimeError("Could not identify a unique Payload Manager ELF asset")
        asset = elf_assets[0]
    return {
        "name": "Payload Manager",
        "filename": str(asset["name"]),
        "url": str(asset["browser_download_url"]),
        "description": "PS5 Payload Manager dashboard for installing, organizing and launching payloads.",
        "version": str(release.get("tag_name") or release.get("name") or "latest"),
        "category": "System & Jailbreak",
    }


def make_card(item: dict, featured: bool = False) -> str:
    filename = str(item["filename"])
    href = "payloads/" + urllib.parse.quote(filename, safe="")
    classes = "payload-card featured" if featured else "payload-card"
    return (
        f'<a class="{classes}" href="{html.escape(href, quote=True)}">\n'
        '  <div class="payload-card-top">\n'
        f'    <span class="payload-name">{html.escape(str(item["name"]))}</span>\n'
        f'    <span class="payload-version">{html.escape(str(item.get("version", "")))}</span>\n'
        '  </div>\n'
        f'  <div class="payload-category">{html.escape(str(item.get("category", "Uncategorized")))}</div>\n'
        f'  <p>{html.escape(str(item.get("description", "")))}</p>\n'
        '  <span class="payload-action">ELF file</span>\n'
        '</a>'
    )


def main():
    if not SITE.exists():
        raise RuntimeError(f"Site directory does not exist: {SITE}")
    if not (UPSTREAM / "index.html").is_file():
        raise RuntimeError(f"Upstream SlopKit checkout not found: {UPSTREAM}")

    # Fresh path that the PS5's previous AppCache groups have never seen.
    # Copy the complete upstream host without modification, then remove only Git metadata.
    original_dir = SITE / "original"
    if original_dir.exists():
        shutil.rmtree(original_dir)
    shutil.copytree(UPSTREAM, original_dir)
    shutil.rmtree(original_dir / ".git", ignore_errors=True)

    # Also retain a byte-for-byte standalone copy of upstream index.html for easy comparison.
    shutil.copy2(UPSTREAM / "index.html", SITE / "original-slopkit.html")

    upstream_index = (UPSTREAM / "index.html").read_text(encoding="utf-8")
    if UPSTREAM_RUN_QUERY.replace("&", "&amp;") not in upstream_index:
        raise RuntimeError("Upstream SlopKit RUN URL changed unexpectedly")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = list(catalog.get("payloads", []))
    manager = latest_pldmgr()
    all_items = [manager] + items

    payload_dir = SITE / "payloads"
    if payload_dir.exists():
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True)

    total = 0
    generated = []
    for item in all_items:
        data = download(str(item["url"]))
        digest = verify_elf(str(item["filename"]), data, item.get("checksum"))
        out = payload_dir / str(item["filename"])
        out.write_bytes(data)
        total += len(data)
        enriched = dict(item)
        enriched["checksum"] = digest
        enriched["size"] = len(data)
        generated.append(enriched)
        print(f"OK {item['name']}: {item['filename']} ({len(data)} bytes)")

    (SITE / "payload-menu.json").write_text(
        json.dumps({"payloads": generated}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    index_template = (OVERLAY / "index.html").read_text(encoding="utf-8")
    cards = "\n".join(make_card(item, i == 0) for i, item in enumerate(generated))
    build_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    replacements = {
        "{{PAYLOAD_COUNT}}": str(len(generated)),
        "{{PAYLOAD_CARDS}}": cards,
        "{{PLDMGR_VERSION}}": html.escape(manager["version"]),
        "{{BUILD_TIME}}": html.escape(build_time),
    }
    for key, value in replacements.items():
        index_template = index_template.replace(key, value)

    if CUSTOM_RUN_QUERY.replace("&", "&amp;") not in index_template:
        raise RuntimeError("Custom landing page is not using fresh untouched SlopKit path")

    (SITE / "index.html").write_text(index_template, encoding="utf-8")
    shutil.copy2(OVERLAY / "main.css", SITE / "main.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    upstream_sha = os.environ.get("SLOPKIT_SHA", "")
    status = {
        "status": "built",
        "built_at_utc": build_time,
        "slopkit_upstream": "jordyidk/slopkit",
        "slopkit_commit": upstream_sha,
        "slopkit_runtime_modified": False,
        "fresh_original_path": "/original/",
        "payload_count": len(generated),
        "payload_manager_version": manager["version"],
        "payload_bytes": total,
        "pages_branch": "gh-pages",
    }
    (ROOT / "jailbreak_host_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    (SITE / "build-status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Built UI with {len(generated)} hosted ELFs ({total} bytes)")
    print("SlopKit exploit/runtime files were not patched")
    print("Fresh untouched upstream copy published at /original/")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
