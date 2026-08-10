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
MANIFEST_NAME = "cache-lite-v3.appcache"
MAX_CACHE_BYTES = 4_500_000

STATUS_BLOCK = r'''
<div id="offline-cache-status" role="status">Offline cache: preparing...</div>
<script>
(function () {
  var box = document.getElementById('offline-cache-status');
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
      setStatus('Offline cache: downloading original SlopKit + Payload Manager...', '');
    });
    ac.addEventListener('progress', function (e) {
      if (e && e.total) setStatus('Offline cache: ' + e.loaded + ' / ' + e.total + ' files', '');
    });
    ac.addEventListener('cached', function () {
      setStatus('Offline jailbreak ready ✓ Original SlopKit + Payload Manager cached', 'ready');
    });
    ac.addEventListener('noupdate', function () {
      setStatus('Offline jailbreak ready ✓', 'ready');
    });
    ac.addEventListener('updateready', function () {
      try { ac.swapCache(); } catch (e) {}
      setStatus('Offline cache updated ✓ Reload once', 'ready');
    });
    ac.addEventListener('error', function () {
      if (typeof navigator !== 'undefined' && navigator.onLine === false)
        setStatus('Offline mode ✓ Using cached original SlopKit', 'ready');
      else
        setStatus('Offline cache incomplete — keep internet on and reload', 'warn');
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


def patch_root_only() -> None:
    path = SITE / "index.html"
    text = path.read_text(encoding="utf-8")
    if re.search(r"<html\b[^>]*\bmanifest\s*=", text, flags=re.I):
        text = re.sub(
            r'(<html\b[^>]*\bmanifest\s*=\s*["\'])[^"\']*(["\'])',
            lambda m: m.group(1) + MANIFEST_NAME + m.group(2),
            text,
            count=1,
            flags=re.I,
        )
    else:
        text, n = re.subn(r"<html\b", f'<html manifest="{MANIFEST_NAME}"', text, count=1, flags=re.I)
        if n != 1:
            raise RuntimeError("Could not attach AppCache to custom landing page")

    if "offline-cache-status" not in text:
        head_pos = text.lower().rfind("</head>")
        body_pos = text.lower().rfind("</body>")
        if head_pos < 0 or body_pos < 0:
            raise RuntimeError("Custom landing page is missing head/body terminators")
        text = text[:head_pos] + STATUS_CSS + "\n" + text[head_pos:]
        body_pos = text.lower().rfind("</body>")
        text = text[:body_pos] + STATUS_BLOCK + "\n" + text[body_pos:]

    path.write_text(text, encoding="utf-8")


def file_digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_tree(paths: list[pathlib.Path], directory: pathlib.Path) -> None:
    if not directory.is_dir():
        return
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            paths.append(p)


def query_urls_from_file(path: pathlib.Path) -> set[str]:
    out: set[str] = set()
    attr = re.compile(r'(?:src|href)\s*=\s*["\']([^"\']+\?[^"\']*)["\']', re.I)
    text = path.read_text(encoding="utf-8", errors="ignore")
    base = path.relative_to(SITE).parent.as_posix()
    for raw in attr.findall(text):
        raw = html.unescape(raw)
        if raw.startswith(("http://", "https://", "//", "data:", "javascript:", "#")):
            continue
        target = raw
        if base and base != "." and not raw.startswith("/"):
            target = f"{base}/{raw}"
        out.add(target)
    return out


def main() -> None:
    if not SITE.is_dir():
        raise RuntimeError(f"Site directory does not exist: {SITE}")

    # Critical rule: only the custom top-level UI gets a manifest attribute.
    # Files under slopkit/ are upstream exploit/runtime and must remain byte-for-byte unchanged.
    patch_root_only()

    menu = json.loads((SITE / "payload-menu.json").read_text(encoding="utf-8"))["payloads"]
    if not menu or menu[0].get("name") != "Payload Manager":
        raise RuntimeError("Payload Manager must be first in payload-menu.json")
    manager_path = SITE / "payloads" / str(menu[0]["filename"])
    if not manager_path.is_file():
        raise RuntimeError("Payload Manager ELF is missing")

    files: list[pathlib.Path] = [
        SITE / "index.html",
        SITE / "main.css",
        SITE / "original-slopkit.html",
        SITE / "payload-menu.json",
        manager_path,
    ]
    add_tree(files, SITE / "slopkit")
    add_tree(files, SITE / "offsets")

    unique: list[pathlib.Path] = []
    seen_paths: set[pathlib.Path] = set()
    for p in files:
        p = p.resolve()
        if p not in seen_paths:
            seen_paths.add(p)
            unique.append(p)

    cached_bytes = sum(p.stat().st_size for p in unique)
    if cached_bytes > MAX_CACHE_BYTES:
        raise RuntimeError(
            f"Offline cache would be {cached_bytes} bytes, above safe ceiling {MAX_CACHE_BYTES}"
        )

    version = hashlib.sha256()
    urls: list[str] = ["./"]
    for path in unique:
        rel = path.relative_to(SITE.resolve()).as_posix()
        version.update(rel.encode("utf-8") + b"\0")
        version.update(file_digest(path).encode("ascii") + b"\n")
        urls.append(urllib.parse.quote(rel, safe="/._-~"))

    query_urls: set[str] = set()
    for html_path in (SITE / "original-slopkit.html", SITE / "slopkit" / "poops.html"):
        query_urls.update(query_urls_from_file(html_path))
    for url in sorted(query_urls):
        version.update(b"QUERY\0" + url.encode("utf-8") + b"\n")
        urls.append(url.replace(" ", "%20"))

    seen: set[str] = set()
    cache_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            cache_urls.append(url)

    manifest = [
        "CACHE MANIFEST",
        f"# version: {version.hexdigest()}",
        f"# Original upstream SlopKit + Payload Manager only ({cached_bytes} bytes)",
        "",
        "CACHE:",
        *cache_urls,
        "",
        "FALLBACK:",
        "slopkit/poops.html slopkit/poops.html",
        "",
        "NETWORK:",
        "*",
        "",
    ]
    (SITE / MANIFEST_NAME).write_text("\n".join(manifest), encoding="utf-8")

    print(
        f"Offline cache ready: {len(cache_urls)} URLs, {cached_bytes} bytes, "
        f"original SlopKit untouched, version {version.hexdigest()[:12]}"
    )


if __name__ == "__main__":
    main()
