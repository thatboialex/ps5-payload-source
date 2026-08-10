#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = pathlib.Path(os.environ.get("SITE_DIR", ROOT / "_site"))
MANIFEST_NAME = "cache-lite-v2.appcache"
# Older/mobile WebKit AppCache implementations are commonly constrained around 5 MB.
# Stay below that instead of letting one large ELF invalidate the entire offline host.
SAFE_CACHE_BYTES = 4_500_000

STATUS_BLOCK = r'''
<div id="offline-cache-status" role="status">Offline cache: preparing SlopKit + Payload Manager...</div>
<script>
(function () {
  var box = document.getElementById('offline-cache-status');
  var loaded = 0, total = 0;
  function setStatus(text, cls) {
    if (!box) return;
    box.textContent = text;
    box.className = cls || '';
  }
  try {
    var ac = window.applicationCache;
    if (!ac) {
      setStatus('Offline cache unavailable in this browser', 'warn');
      return;
    }
    ac.addEventListener('checking', function () {
      setStatus('Offline cache: checking...', '');
    });
    ac.addEventListener('downloading', function () {
      setStatus('Offline cache: downloading SlopKit + Payload Manager...', '');
    });
    ac.addEventListener('progress', function (e) {
      loaded = e && typeof e.loaded === 'number' ? e.loaded : loaded + 1;
      total = e && typeof e.total === 'number' ? e.total : total;
      setStatus(total ? ('Offline cache: ' + loaded + ' / ' + total + ' files')
                      : ('Offline cache: ' + loaded + ' files'), '');
    });
    ac.addEventListener('cached', function () {
      setStatus('Offline jailbreak ready ✓ SlopKit + Payload Manager cached', 'ready');
    });
    ac.addEventListener('noupdate', function () {
      setStatus('Offline jailbreak ready ✓ SlopKit + Payload Manager cached', 'ready');
    });
    ac.addEventListener('updateready', function () {
      try { ac.swapCache(); } catch (e) {}
      setStatus('Offline cache updated ✓ Reload once, then you can disconnect', 'ready');
    });
    ac.addEventListener('obsolete', function () {
      setStatus('Offline cache was reset; reconnect and reload', 'warn');
    });
    ac.addEventListener('error', function () {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        setStatus('Offline mode ✓ Using cached SlopKit + Payload Manager', 'ready');
      } else {
        var progress = total ? (' after ' + loaded + '/' + total + ' files') : '';
        setStatus('Offline cache failed' + progress + ' — reload while online', 'warn');
      }
    });
  } catch (e) {
    setStatus('Offline cache status unavailable', 'warn');
  }
})();
</script>
'''.strip()

STATUS_CSS = r'''
<style>
#offline-cache-status {
  position: fixed; right: 18px; bottom: 16px; z-index: 99999;
  max-width: 560px; padding: 10px 14px; border-radius: 10px;
  font: 700 13px/1.35 Arial, sans-serif; color: #d8dee9;
  background: rgba(21,22,26,.94); border: 1px solid #4d515a;
  box-shadow: 0 8px 30px rgba(0,0,0,.32);
}
#offline-cache-status.ready { color: #c9f7d5; border-color: #55d17d; }
#offline-cache-status.warn { color: #ffe4a8; border-color: #d8a84e; }
</style>
'''.strip()


def patch_html(path: pathlib.Path, manifest_rel: str, *, add_status: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    manifest = html.escape(manifest_rel, quote=True)
    if re.search(r"<html\b[^>]*\bmanifest\s*=", text, flags=re.I):
        text = re.sub(
            r"(<html\b[^>]*\bmanifest\s*=\s*[\"'])[^\"']*([\"'])",
            lambda m: m.group(1) + manifest + m.group(2),
            text,
            count=1,
            flags=re.I,
        )
    else:
        text, n = re.subn(r"<html\b", f'<html manifest="{manifest}"', text, count=1, flags=re.I)
        if n != 1:
            raise RuntimeError(f"Could not add AppCache manifest to {path}")

    if add_status and "offline-cache-status" not in text:
        head_pos = text.lower().rfind("</head>")
        if head_pos >= 0:
            text = text[:head_pos] + STATUS_CSS + "\n" + text[head_pos:]
        body_pos = text.lower().rfind("</body>")
        if body_pos < 0:
            raise RuntimeError("Root index has no </body> for offline status UI")
        text = text[:body_pos] + STATUS_BLOCK + "\n" + text[body_pos:]

    path.write_text(text, encoding="utf-8")


def file_digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_if_file(paths: list[pathlib.Path], path: pathlib.Path) -> None:
    if path.is_file() and path not in paths:
        paths.append(path)


def required_runtime_files() -> tuple[list[pathlib.Path], pathlib.Path, pathlib.Path]:
    index = SITE / "index.html"
    poops = SITE / "slopkit" / "poops.html"
    if not index.is_file() or not poops.is_file():
        raise RuntimeError("Generated host is missing index.html or slopkit/poops.html")

    menu = json.loads((SITE / "payload-menu.json").read_text(encoding="utf-8"))["payloads"]
    if not menu or menu[0].get("name") != "Payload Manager":
        raise RuntimeError("Payload Manager is not first in payload-menu.json")
    manager = SITE / "payloads" / str(menu[0]["filename"])
    if not manager.is_file():
        raise RuntimeError(f"Payload Manager ELF missing: {manager}")

    paths: list[pathlib.Path] = []
    for rel in ("index.html", "main.css", "payload-menu.json"):
        add_if_file(paths, SITE / rel)
    for p in sorted((SITE / "offsets").glob("*.js")):
        add_if_file(paths, p)
    for p in sorted((SITE / "slopkit").iterdir()):
        if p.is_file() and p.suffix.lower() in {".html", ".js", ".jpg"}:
            add_if_file(paths, p)

    # Payload Manager is the only ELF in AppCache. Large direct payloads remain on the
    # page for online use but cannot be allowed to make the whole offline jailbreak fail.
    add_if_file(paths, manager)

    # The animated GIF is cosmetic. Include it only if the cache still stays safely below quota.
    gif = SITE / "slopkit" / "mmhmm-cats-ps5.gif"
    base_bytes = sum(p.stat().st_size for p in paths)
    if gif.is_file() and base_bytes + gif.stat().st_size <= SAFE_CACHE_BYTES:
        add_if_file(paths, gif)

    return paths, index, poops


def query_aliases(paths: list[pathlib.Path]) -> list[str]:
    """Collect versioned JS/CSS request URLs without duplicating HTML query pages."""
    aliases: set[str] = set()
    rx = re.compile(r"([A-Za-z0-9_./-]+\.(?:js|css)\?[^\"'\\\s<>]+)", re.I)
    for path in paths:
        if path.suffix.lower() not in {".html", ".js"}:
            continue
        text = html.unescape(path.read_text(encoding="utf-8", errors="ignore"))
        parent = path.relative_to(SITE).parent
        for raw in rx.findall(text):
            raw = raw.strip()
            base, query = raw.split("?", 1)
            if base.startswith("/"):
                rel = pathlib.PurePosixPath(base.lstrip("/"))
            else:
                rel = pathlib.PurePosixPath(parent.as_posix()) / base
            # Collapse ./ and ../ safely.
            parts: list[str] = []
            for part in rel.parts:
                if part in ("", "."):
                    continue
                if part == "..":
                    if parts:
                        parts.pop()
                    continue
                parts.append(part)
            normalized = "/".join(parts)
            target_file = SITE / normalized
            if target_file.is_file():
                aliases.add(normalized + "?" + query)
    return sorted(aliases)


def main() -> None:
    if not SITE.is_dir():
        raise RuntimeError(f"Site directory does not exist: {SITE}")

    files, index, poops = required_runtime_files()

    # Fresh manifest name avoids reusing the failed oversized AppCache group.
    patch_html(index, MANIFEST_NAME, add_status=True)
    patch_html(poops, "../" + MANIFEST_NAME)

    # HTML changed after patching; recalculate final cache size.
    cache_bytes = sum(p.stat().st_size for p in files)
    if cache_bytes > SAFE_CACHE_BYTES:
        raise RuntimeError(
            f"quota-safe AppCache would be {cache_bytes} bytes, above {SAFE_CACHE_BYTES}; "
            "reduce runtime assets before publishing"
        )

    version = hashlib.sha256()
    urls: list[str] = ["./"]
    for path in sorted(files, key=lambda p: p.relative_to(SITE).as_posix()):
        rel = path.relative_to(SITE).as_posix()
        version.update(rel.encode("utf-8") + b"\0")
        version.update(file_digest(path).encode("ascii") + b"\n")
        urls.append(urllib.parse.quote(rel, safe="/._-~"))

    aliases = query_aliases(files)
    for url in aliases:
        version.update(b"QUERY\0" + url.encode("utf-8") + b"\n")
        urls.append(url)

    seen: set[str] = set()
    cache_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            cache_urls.append(url)

    manager_urls = [u for u in cache_urls if u.startswith("payloads/")]
    if len(manager_urls) != 1 or not pathlib.PurePosixPath(manager_urls[0]).name.lower().startswith("pldmgr"):
        raise RuntimeError(f"Expected exactly one cached ELF (Payload Manager), got: {manager_urls}")

    manifest = [
        "CACHE MANIFEST",
        f"# version: {version.hexdigest()}",
        f"# Quota-safe offline SlopKit + Payload Manager ({cache_bytes} bytes)",
        "",
        "CACHE:",
        *cache_urls,
        "",
        "FALLBACK:",
        # All Jailbreak/Jailbreak+Load query variants reuse the one cached SlopKit page.
        "slopkit/poops.html slopkit/poops.html",
        "",
        "NETWORK:",
        "*",
        "",
    ]
    (SITE / MANIFEST_NAME).write_text("\n".join(manifest), encoding="utf-8")

    print(
        f"Quota-safe AppCache ready: {len(cache_urls)} cache URLs, "
        f"{cache_bytes} cached bytes, Payload Manager only, "
        f"version {version.hexdigest()[:12]}"
    )


if __name__ == "__main__":
    main()
