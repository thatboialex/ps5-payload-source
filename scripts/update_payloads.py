#!/usr/bin/env python3
"""Update a PS5 Payload Manager catalog from upstream GitHub releases.

Uses only the Python standard library. Designed for GitHub Actions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "sources.json"
PAYLOADS_PATH = ROOT / "payloads.json"
STATUS_PATH = ROOT / "upstream_status.json"
API_VERSION = "2022-11-28"
USER_AGENT = "ps5-payload-source-updater/1.0"


def request(url: str, *, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(request(url), timeout=30) as response:
        return json.load(response)


def latest_release(repo: str) -> dict[str, Any]:
    return get_json(f"https://api.github.com/repos/{repo}/releases/latest")


def supported_asset(asset: dict[str, Any], source: dict[str, Any]) -> bool:
    name = str(asset.get("name") or "")
    lower = name.lower()
    allowed = tuple(ext.lower() for ext in source.get("allowed_extensions", [".elf", ".bin", ".lua"]))
    return lower.endswith(allowed)


def choose_asset(release: dict[str, Any], source: dict[str, Any]) -> dict[str, Any] | None:
    assets = [a for a in release.get("assets", []) if supported_asset(a, source)]
    if not assets:
        return None

    exact = [str(x).lower() for x in source.get("exact_assets", [])]
    for wanted in exact:
        for asset in assets:
            if str(asset.get("name", "")).lower() == wanted:
                return asset

    contains = [str(x).lower() for x in source.get("asset_name_contains", [])]
    if contains:
        for needle in contains:
            for asset in assets:
                if needle in str(asset.get("name", "")).lower():
                    return asset

    if len(assets) == 1:
        return assets[0]
    return None


def normalize_digest(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", value.strip())
    return match.group(1).lower() if match else None


def sha256_url(url: str) -> str:
    hasher = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as response:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def payload_from_release(source: dict[str, Any], release: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    url = asset.get("browser_download_url")
    name = asset.get("name")
    if not isinstance(url, str) or not isinstance(name, str):
        raise ValueError("Release asset is missing browser_download_url or name")

    item: dict[str, Any] = {
        "name": source["name"],
        "filename": name,
        "url": url,
        "description": source.get("description", ""),
        "version": str(release.get("tag_name") or release.get("name") or "latest"),
        "category": source.get("category", "Uncategorized"),
    }

    digest = normalize_digest(asset.get("digest"))
    if digest is None:
        try:
            digest = sha256_url(url)
        except Exception as exc:
            print(f"warning: could not hash {source['name']}: {exc}", file=sys.stderr)
    if digest:
        item["checksum"] = digest
    return item


def load_existing_payloads() -> dict[str, dict[str, Any]]:
    if not PAYLOADS_PATH.exists():
        return {}
    data = json.loads(PAYLOADS_PATH.read_text(encoding="utf-8"))
    return {p["name"]: p for p in data.get("payloads", []) if isinstance(p, dict) and p.get("name")}


def main() -> int:
    config = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    existing = load_existing_payloads()
    payloads: list[dict[str, Any]] = []
    status: dict[str, Any] = {}

    for source in config["sources"]:
        name = source["name"]
        repo = source["repo"]
        record: dict[str, Any] = {"repo": repo, "published": False}
        if source.get("manual_package_links"):
            record["manual_package_links"] = source["manual_package_links"]

        try:
            release = latest_release(repo)
            record["release_tag"] = str(release.get("tag_name") or release.get("name") or "")
            asset = choose_asset(release, source)
            if asset and source.get("publish_if_compatible", True):
                item = payload_from_release(source, release, asset)
                payloads.append(item)
                record.update({"published": True, "asset": item["filename"]})
            else:
                record["reason"] = "No unambiguous PLDMGR-compatible .elf/.bin/.lua asset found in the latest GitHub release."
                if name in existing and source.get("publish_if_compatible", True) and source.get("exact_assets"):
                    payloads.append(existing[name])
                    record["published"] = True
                    record["retained_previous_entry"] = True
        except urllib.error.HTTPError as exc:
            record["reason"] = f"GitHub API HTTP {exc.code} while checking latest release."
            if name in existing and source.get("exact_assets"):
                payloads.append(existing[name])
                record["published"] = True
                record["retained_previous_entry"] = True
        except Exception as exc:
            record["reason"] = f"Update check failed: {type(exc).__name__}: {exc}"
            if name in existing and source.get("exact_assets"):
                payloads.append(existing[name])
                record["published"] = True
                record["retained_previous_entry"] = True

        status[name] = record

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payloads:
        if item["name"] not in seen:
            seen.add(item["name"])
            deduped.append(item)

    catalog = {"name": config["repository_name"], "payloads": deduped}
    PAYLOADS_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Published {len(deduped)} compatible payload(s).")
    for item in deduped:
        print(f"- {item['name']}: {item.get('version', 'unversioned')} -> {item['filename']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
