#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "jailbreak-host"
CATALOG = ROOT / "payloads-v2.json"
SITE = pathlib.Path(os.environ.get("SITE_DIR", ROOT / "_site"))
USER_AGENT = "thatboialex-ps5-jailbreak-host/1.0"
PLDMGR_API = "https://api.github.com/repos/itsPLK/ps5-payload-manager/releases/latest"


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
    href = (
        "slopkit/poops.html?go=1&auto=1&trigger=netcontrol&payload=1&v=17&autoload="
        + urllib.parse.quote(filename, safe="")
    )
    classes = "payload-card featured" if featured else "payload-card"
    return (
        f'<a class="{classes}" href="{html.escape(href, quote=True)}">\n'
        '  <div class="payload-card-top">\n'
        f'    <span class="payload-name">{html.escape(str(item["name"]))}</span>\n'
        f'    <span class="payload-version">{html.escape(str(item.get("version", "")))}</span>\n'
        '  </div>\n'
        f'  <div class="payload-category">{html.escape(str(item.get("category", "Uncategorized")))}</div>\n'
        f'  <p>{html.escape(str(item.get("description", "")))}</p>\n'
        '  <span class="payload-action">Jailbreak + Load</span>\n'
        '</a>'
    )


def make_slopkit_tile(item: dict, featured: bool = False) -> str:
    cls = "payloadTile customPayloadTile featured" if featured else "payloadTile customPayloadTile"
    return (
        f'  <a class="{cls}" href="#" data-name="{html.escape(str(item["filename"]), quote=True)}">\n'
        '    <span class="payloadText">\n'
        '      <span class="payloadTextTop">\n'
        f'        <strong>{html.escape(str(item["name"]))}</strong>\n'
        f'        <small>{html.escape(str(item.get("version", "")))}</small>\n'
        '      </span>\n'
        f'      <span class="payloadMeta">{html.escape(str(item.get("category", "Uncategorized")))}</span>\n'
        f'      <span class="payloadDesc">{html.escape(str(item.get("description", "")))}</span>\n'
        '      <span class="payloadState">LOAD</span>\n'
        '    </span>\n'
        '  </a>'
    )


def patch_slopkit(poops_path: pathlib.Path, items: list[dict], max_payload_size: int):
    text = poops_path.read_text(encoding="utf-8")

    menu = '<div id="payloadMenu">\n  <div class="menuTitleText">Payloads</div>\n'
    menu += "\n".join(make_slopkit_tile(item, i == 0) for i, item in enumerate(items))
    menu += '\n</div>\n<div id="nav"></div>'

    text, n = re.subn(
        r'<div id="payloadMenu">.*?</div>\s*<div id="nav"></div>',
        menu,
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise RuntimeError("Could not replace SlopKit payload menu")

    state_fn = '''function setPayloadTileState(tile, state) {
    try {
        tile.setAttribute("data-state", state || "idle");
        const label = tile.querySelector(".payloadState");
        if (label) {
            const map = { sending: "SENDING...", sent: "SENT", failed: "FAILED" };
            label.textContent = map[state] || "LOAD";
        }
    } catch (e) { }
}

function payloadIsListed'''
    text, n = re.subn(
        r'function setPayloadTileState\(tile, state\) \{.*?\n\}\n\nfunction payloadIsListed',
        state_fn,
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise RuntimeError("Could not patch SlopKit tile-state handler")

    old_focus = '    if (tiles.length) try { tiles[0].focus(); } catch (e) { }\n}'
    new_focus = '''    if (tiles.length) try { tiles[0].focus(); } catch (e) { }

    try {
        const autoName = Q.get("autoload") || "";
        if (autoName && !window.__slopkitAutoPayloadStarted && payloadIsListed(autoName)) {
            window.__slopkitAutoPayloadStarted = true;
            for (let i = 0; i < tiles.length; ++i) {
                if (tiles[i].getAttribute("data-name") === autoName) {
                    setTimeout(function () { sendPayloadInPlace(autoName, tiles[i]); }, 120);
                    break;
                }
            }
        }
    } catch (e) { }
}'''
    if old_focus not in text:
        raise RuntimeError("Could not patch SlopKit autoload hook")
    text = text.replace(old_focus, new_focus, 1)

    dynamic_limit = max(0x4000000, max_payload_size + 0x200000)
    text, n = re.subn(
        r'const PAYLOAD_MAX_SIZE = 0x[0-9A-Fa-f]+;',
        f'const PAYLOAD_MAX_SIZE = 0x{dynamic_limit:X};',
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError("Could not patch SlopKit payload size limit")

    css = r'''
  /* Custom idlesauce-inspired payload menu */
  body.loader-ready { background:#0c0c0f; }
  #payloadMenu {
    width:94vw !important;
    max-width:960px !important;
    display:none;
    grid-template-columns:repeat(2, minmax(0, 1fr));
    gap:14px;
    padding:0 0 28px;
  }
  #payloadMenu.on { display:grid !important; }
  #payloadMenu .menuTitleText {
    grid-column:1 / -1; color:#fff; font-family:Arial, sans-serif;
    font-size:28px; font-weight:800; text-align:center; padding:8px 0 6px;
  }
  #payloadMenu .customPayloadTile {
    width:100% !important; max-width:none !important; min-height:126px;
    margin:0 !important; padding:18px 20px !important; border-radius:20px !important;
    background:#202125 !important; color:#fff !important;
    border:2px solid transparent !important; box-sizing:border-box;
    text-align:left; font-family:Arial, sans-serif;
    transition:background-color .2s ease, color .2s ease;
  }
  #payloadMenu .customPayloadTile.featured { border-color:#555861 !important; }
  #payloadMenu .customPayloadTile:focus {
    outline:none !important; border-color:#fff !important;
    background:#a2a2a6 !important; color:#202020 !important;
  }
  #payloadMenu .customPayloadTile.busy { opacity:.42; }
  #payloadMenu .customPayloadTile[data-state="sent"] { border-color:#55d17d !important; }
  #payloadMenu .customPayloadTile[data-state="failed"] { border-color:#ff6666 !important; }
  .payloadText { display:block; }
  .payloadTextTop { display:flex; justify-content:space-between; gap:12px; align-items:center; }
  .payloadTextTop strong { font-size:20px; line-height:1.3; }
  .payloadTextTop small { color:#aaa; font-size:13px; }
  .customPayloadTile:focus .payloadTextTop small { color:#444; }
  .payloadMeta { display:block; color:#999; font-size:13px; margin-top:3px; }
  .payloadDesc {
    display:block; color:#ccc; font-size:14px; line-height:1.35; margin-top:8px;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  }
  .payloadState {
    display:inline-block; margin-top:11px; font-size:13px; font-weight:800;
    color:#fff; background:#15161a; border-radius:9px; padding:7px 10px;
  }
  .customPayloadTile:focus .payloadMeta,
  .customPayloadTile:focus .payloadDesc { color:#444; }
  @media (max-width:720px) { #payloadMenu { grid-template-columns:1fr; } }
'''
    idx = text.rfind("</style>")
    if idx < 0:
        raise RuntimeError("SlopKit style block not found")
    text = text[:idx] + css + "\n" + text[idx:]
    poops_path.write_text(text, encoding="utf-8")


def main():
    if not SITE.exists():
        raise RuntimeError(f"Site directory does not exist: {SITE}")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = list(catalog.get("payloads", []))
    manager = latest_pldmgr()
    all_items = [manager] + items

    payload_dir = SITE / "payloads"
    if payload_dir.exists():
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True)

    total = 0
    max_size = 0
    generated = []
    for item in all_items:
        data = download(str(item["url"]))
        digest = verify_elf(str(item["filename"]), data, item.get("checksum"))
        out = payload_dir / str(item["filename"])
        out.write_bytes(data)
        total += len(data)
        max_size = max(max_size, len(data))
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

    (SITE / "index.html").write_text(index_template, encoding="utf-8")
    shutil.copy2(OVERLAY / "main.css", SITE / "main.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    patch_slopkit(SITE / "slopkit" / "poops.html", generated, max_size)

    upstream_sha = os.environ.get("SLOPKIT_SHA", "")
    status = {
        "status": "built",
        "built_at_utc": build_time,
        "slopkit_upstream": "jordyidk/slopkit",
        "slopkit_commit": upstream_sha,
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

    print(f"Built host with {len(generated)} payloads ({total} bytes)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
