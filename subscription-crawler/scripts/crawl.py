#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.txt"
OUTPUT = ROOT / "output"

TIMEOUT = int(os.getenv("FETCH_TIMEOUT", "30"))
CONVERT_TIMEOUT = int(os.getenv("CONVERT_TIMEOUT", "180"))
SUBCONVERTER = os.getenv("SUBCONVERTER_URL", "http://127.0.0.1:25500")

HEADERS = {
    "User-Agent": "Mozilla/5.0 SubscriptionCrawler/1.0 (+GitHub Actions)"
}

# URLs which are clearly not subscription sources.
SKIP_HOSTS = {
    "github.com",
    "www.github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
    "www.google.com",
    "google.com",
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "t.me",
    "telegram.me",
}

IMAGE_EXT = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|ico)(?:\?.*)?$", re.I)

NODE_SCHEMES = (
    "vmess://", "vless://", "trojan://", "ss://", "ssr://",
    "hysteria://", "hysteria2://", "hy2://", "tuic://"
)

URL_RE = re.compile(r"https?://[^\s<>\]\"'`()]+", re.I)


def log(msg):
    print(msg, flush=True)


def read_sources():
    if not CONFIG.exists():
        raise FileNotFoundError(CONFIG)
    return [
        line.strip()
        for line in CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def clean_url(url):
    return url.rstrip(".,;:!?)]}>`\"'")


def is_candidate(url):
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
    except Exception:
        return False

    if p.scheme not in ("http", "https") or not host:
        return False
    if host in SKIP_HOSTS or host.endswith(".github.com"):
        return False
    if IMAGE_EXT.search(p.path):
        return False
    return True


def extract_urls(text):
    result = []
    for raw in URL_RE.findall(text):
        u = clean_url(raw)
        if is_candidate(u):
            result.append(u)
    return result


def unique(items):
    out, seen = [], set()
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def download_subscription(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text.strip()


def decode_base64_if_possible(text):
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None
    # Avoid treating ordinary YAML/HTML as base64.
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        return None
    try:
        padded = compact + "=" * (-len(compact) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        if any(s in decoded for s in NODE_SCHEMES):
            return decoded
    except Exception:
        return None
    return None


def extract_node_links(text):
    decoded = decode_base64_if_possible(text)
    candidates = [decoded] if decoded else [text]
    nodes = []
    for content in candidates:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(NODE_SCHEMES):
                nodes.append(line)
    return unique(nodes)


def fetch_nodes(urls):
    nodes = []
    failed = 0
    for i, url in enumerate(urls, 1):
        try:
            content = download_subscription(url)
            found = extract_node_links(content)
            log(f"[NODES] {i}/{len(urls)} {len(found):4d}  {url}")
            nodes.extend(found)
        except Exception as e:
            failed += 1
            log(f"[WARN] node fetch failed: {url} :: {e}")
    return unique(nodes), failed


def save_sources(urls):
    (OUTPUT / "sources.txt").write_text(
        "\n".join(urls) + "\n", encoding="utf-8"
    )


def save_nodes(nodes):
    raw = "\n".join(nodes) + ("\n" if nodes else "")
    (OUTPUT / "nodes.txt").write_text(raw, encoding="utf-8")
    encoded = base64.b64encode(raw.encode()).decode()
    (OUTPUT / "v2ray.txt").write_text(encoded + "\n", encoding="utf-8")


def convert(target, urls):
    if not urls:
        raise RuntimeError(f"No subscription URLs available for target={target}")

    # subconverter accepts multiple URLs separated by |.
    joined = "|".join(urls)
    endpoint = f"{SUBCONVERTER}/sub?target={quote(target)}&url={quote(joined, safe='')}"
    r = requests.get(endpoint, headers=HEADERS, timeout=CONVERT_TIMEOUT)
    r.raise_for_status()
    if not r.text.strip():
        raise RuntimeError(f"subconverter returned empty output for {target}")
    return r.text


def validate_clash(text):
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Clash output is not a YAML mapping")
    if "proxies" not in data:
        raise ValueError("Clash output has no 'proxies' field")
    return len(data.get("proxies") or [])


def write_meta(source_count, node_count, clash_count, failed_sources, failed_node_fetches):
    import datetime as dt
    meta = {
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_readmes": source_count,
        "subscription_urls": len(read_sources()),
        "unique_node_links": node_count,
        "clash_proxies": clash_count,
        "failed_readmes": failed_sources,
        "failed_subscription_fetches": failed_node_fetches,
    }
    (OUTPUT / "status.json").write_text(
        json_dumps(meta), encoding="utf-8"
    )


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    readme_sources = read_sources()

    subscription_urls = []
    failed_readmes = 0

    for i, source in enumerate(readme_sources, 1):
        try:
            text = fetch(source)
            found = extract_urls(text)
            log(f"[README] {i}/{len(readme_sources)} {len(found):4d}  {source}")
            subscription_urls.extend(found)
        except Exception as e:
            failed_readmes += 1
            log(f"[WARN] README fetch failed: {source} :: {e}")

    subscription_urls = unique(subscription_urls)
    if not subscription_urls:
        raise RuntimeError("No subscription URLs were found.")

    save_sources(subscription_urls)
    log(f"[INFO] unique subscription URLs = {len(subscription_urls)}")

    # Generate Clash and V2Ray from the same normalized source set.
    clash = convert("clash", subscription_urls)
    clash_count = validate_clash(clash)
    (OUTPUT / "clash.yaml").write_text(clash, encoding="utf-8")

    # Ask subconverter for V2Ray output as the authoritative conversion.
    v2ray = convert("v2ray", subscription_urls)
    (OUTPUT / "v2ray-subconverter.txt").write_text(v2ray, encoding="utf-8")

    # Also keep a simple node-link Base64 subscription when the source format
    # exposes standard URI links.
    nodes, failed_node_fetches = fetch_nodes(subscription_urls)
    save_nodes(nodes)

    write_meta(
        len(readme_sources),
        len(nodes),
        clash_count,
        failed_readmes,
        failed_node_fetches,
    )

    log(f"[DONE] clash proxies = {clash_count}")
    log(f"[DONE] extracted node links = {len(nodes)}")
    log(f"[DONE] output directory = {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"[FATAL] {exc}")
        sys.exit(1)
