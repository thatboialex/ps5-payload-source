#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import os
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = pathlib.Path(os.environ.get("SITE_DIR", ROOT / "_site"))
MANIFEST_NAME = "cache.appcache"

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
      setStatus('Offline cache: downloading site + payloads...', '');
    });
    ac.addEventListener('progress', function (e) {
      if (e && e.total) {
        setStatus('Offline cache: ' + e.loaded + ' / ' + e.total + ' files', '');
      }
    });
    ac.addEventListener('cached', function () {
      setStatus('Offline cache ready ✓ You can disconnect from the internet', 'ready');
    });
    ac.addEventListener('noupdate', function () {
      setStatus('Offline cache ready ✓', 'ready');
    });
    ac.addEventListener('updateready', function () {
      try { ac.swapCache(); } catch (e) {}
      setStatus('Offline cache updated ✓ Reload once to use the newest files', 'ready');
    });
    ac.addEventListener('obsolete', function () {
      setStatus('Offline cache was reset; reconnect and reload', 'warn');
    });
    ac.addEventListener('error', function () {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        setStatus('Offline mode ✓ Using cached jailbreak files', 'ready');
      } else {
        setStatus('Offline cache incomplete — keep internet on and reload', 'warn');
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
  max-width: 540px; padding: 10px 14px; border-radius: 10px;
  font: 700 13px/1.35 Arial, sans-serif; color: #d8dee9;
  background: rgba(21,22,26,.94); border: 1px solid #4d515a;
  box-shadow: 0 8px 30px rgba(0,0,0,.32);
}
#offline-cache-status.ready { color: #c9f7d5; border-color: #55d17d; }
#offline-cache-status.warn { color: #ffe4a8; border-color: #d8a84e; }
</style>
'''.strip()


def rel_manifest_for(html_path: pathlib.Path) -> str:
    rel = os.path.relpath(SITE / MANIFEST_NAME, html_path.parent)
    return pathlib.PurePosixPath(rel).as_posix()


def patch_html(path: pathlib.Path, *, add_status: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    manifest = html.escape(rel_manifest_for(path), quote=True)
    if re.search(r"<html\b[^>]*\bmanifest\s*=", text, flags=re.I):
        text = re.sub(
            r"(<html\b[^>]*\bmanifest\s*=\s*[\"'])[^\"']*([\"'])",
            lambda m: m.group(1) + manifest + m.group(2),
            text,
            count=1,
            flags=re.I,
        )
    else:
        text, n = re.subn(
            r"<html\b",
            f'<html manifest="{manifest}"',
            text,
            count=1,
            flags=re.I,
        )
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


def query_urls_from_html() -> set[str]:
    out: set[str] = set()
    attr = re.compile(r"(?:src|href)\s*=\s*[\"']([^\"']+\?[^\"']*)[\"']", re.I)
    for path in SITE.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        base = path.relative_to(SITE).parent.as_posix()
        for raw in attr.findall(text):
            if raw.startswith(("http://", "https://", "//", "data:", "javascript:", "#")):
                continue
            target = raw
            if base and base != "." and not raw.startswith("/"):
                target = f"{base}/{raw}"
            target = pathlib.PurePosixPath(target.split("?", 1)[0]).as_posix() + "?" + target.split("?", 1)[1]
            out.add(target)
    return out


def main() -> None:
    if not SITE.is_dir():
        raise RuntimeError(f"Site directory does not exist: {SITE}")

    html_files = sorted(SITE.rglob("*.html"))
    if not html_files:
        raise RuntimeError("No HTML files found in generated site")
    for path in html_files:
        patch_html(path, add_status=(path == SITE / "index.html"))

    files: list[pathlib.Path] = []
    for path in sorted(SITE.rglob("*")):
        if not path.is_file():
            continue
        if path.name == MANIFEST_NAME:
            continue
        files.append(path)

    version = hashlib.sha256()
    urls: list[str] = ["./"]
    for path in files:
        rel = path.relative_to(SITE).as_posix()
        version.update(rel.encode("utf-8") + b"\0")
        version.update(file_digest(path).encode("ascii") + b"\n")
        urls.append(urllib.parse.quote(rel, safe="/._-~"))

    query_urls = sorted(query_urls_from_html())
    for url in query_urls:
        version.update(b"QUERY\0" + url.encode("utf-8") + b"\n")
        urls.append(url.replace(" ", "%20"))

    # Preserve order while removing duplicates.
    seen: set[str] = set()
    cache_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            cache_urls.append(url)

    manifest = [
        "CACHE MANIFEST",
        f"# version: {version.hexdigest()}",
        "# Full offline SlopKit host + bundled ELF payloads",
        "",
        "CACHE:",
        *cache_urls,
        "",
        "NETWORK:",
        "*",
        "",
    ]
    (SITE / MANIFEST_NAME).write_text("\n".join(manifest), encoding="utf-8")

    payload_count = len(list((SITE / "payloads").glob("*.elf"))) if (SITE / "payloads").is_dir() else 0
    payload_bytes = sum(p.stat().st_size for p in (SITE / "payloads").glob("*.elf")) if (SITE / "payloads").is_dir() else 0
    print(
        f"Offline AppCache ready: {len(cache_urls)} URLs, "
        f"{payload_count} ELF payloads, {payload_bytes} payload bytes, "
        f"version {version.hexdigest()[:12]}"
    )


if __name__ == "__main__":
    main()
