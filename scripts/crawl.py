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

    # Common invitation/referral URLs are not subscription feeds.
    # Example: https://xxxx.example/i/AbCd1234
    if re.match(r"^/i(?:/|$)", p.path, re.I):
        return False

    return True


def extract_urls(text):
    """
    Prefer URLs inside Markdown fenced code blocks.

    The supplied README sources put actual subscription URLs inside
    ``` ... ``` blocks, while registration/referral URLs are inline.
    The old implementation collected both, which caused subconverter
    to receive referral URLs such as `/i/...` and return:
        HTTP 400: No nodes were found

    For generic README files, if no fenced subscription URLs are found,
    fall back to URLs on lines whose nearby text mentions subscription
    clients such as Clash/v2ray/iOS.
    """
    result = []

    # 1) Highest-confidence source: fenced code blocks.
    fenced = re.findall(r"```(?:[^\n]*)\n(.*?)```", text, flags=re.S)
    for block in fenced:
        for raw in URL_RE.findall(block):
            u = clean_url(raw)
            if is_candidate(u):
                result.append(u)

    if result:
        return unique(result)

    # 2) Fallback: inspect a small context window around subscription
    # headings. This supports sources that don't use fenced code blocks.
    lines = text.splitlines()
    keywords = (
        "clash",
        "v2ray",
        "v2rayn",
        "shadowrocket",
        "小火箭",
        "订阅",
        "subscription",
    )

    for i, line in enumerate(lines):
        lower = line.lower()

        if not any(k in lower for k in keywords):
            continue

        context = "\n".join(lines[i:i + 5])

        for raw in URL_RE.findall(context):
            u = clean_url(raw)
            if is_candidate(u):
                result.append(u)

    return unique(result)


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


def convert_one(target, url):
    """
    Convert ONE remote subscription at a time.

    Doing this instead of putting every URL into one very long `url=`
    parameter has two advantages:
      1. one broken source cannot make the whole conversion fail;
      2. we can identify exactly which source failed.
    """
    endpoint = f"{SUBCONVERTER}/sub"
    params = {
        "target": target,
        "url": url,
    }

    r = requests.get(
        endpoint,
        params=params,
        headers=HEADERS,
        timeout=CONVERT_TIMEOUT,
    )

    if not r.ok:
        body = r.text[:1000].replace("\n", " ")
        raise RuntimeError(
            f"HTTP {r.status_code} from subconverter: {body}"
        )

    if not r.text.strip():
        raise RuntimeError(
            f"subconverter returned empty output for {target}"
        )

    return r.text


def decode_v2ray_output(text):
    """
    subconverter's v2ray output is normally Base64. Decode it to
    node URI lines so multiple sources can be safely merged.
    """
    raw = text.strip()

    # It may already be plain URI lines depending on the backend/template.
    if any(raw.startswith(s) for s in NODE_SCHEMES):
        return [
            line.strip()
            for line in raw.splitlines()
            if line.strip().startswith(NODE_SCHEMES)
        ]

    compact = re.sub(r"\s+", "", raw)
    try:
        padded = compact + "=" * (-len(compact) % 4)
        decoded = base64.b64decode(
            padded,
            validate=False,
        ).decode("utf-8", errors="ignore")

        return [
            line.strip()
            for line in decoded.splitlines()
            if line.strip().startswith(NODE_SCHEMES)
        ]
    except Exception:
        return []


def merge_clash_outputs(outputs):
    """
    Merge Clash YAML files produced independently by subconverter.

    The first valid configuration supplies the general Clash settings
    (port, DNS, rules, rule-providers, etc.). All unique proxies from
    every successful source are inserted into `proxies`.

    For selectable proxy groups, all merged proxy names are appended so
    the newly merged nodes are actually usable.
    """
    configs = []

    for source_url, raw in outputs:
        try:
            data = yaml.safe_load(raw)
        except Exception as exc:
            log(f"[WARN] invalid Clash YAML: {source_url} :: {exc}")
            continue

        if not isinstance(data, dict):
            log(f"[WARN] Clash output is not a mapping: {source_url}")
            continue

        proxies = data.get("proxies")
        if not isinstance(proxies, list):
            log(f"[WARN] Clash output has no proxy list: {source_url}")
            continue

        configs.append((source_url, data))

    if not configs:
        raise RuntimeError("No valid Clash output was produced.")

    base = configs[0][1]

    merged = []
    seen = set()

    for _, data in configs:
        for proxy in data.get("proxies") or []:
            if not isinstance(proxy, dict):
                continue
            name = str(proxy.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            merged.append(proxy)

    base["proxies"] = merged

    # Make merged nodes available in normal selectable/test groups.
    group_types = {
        "select",
        "url-test",
        "fallback",
        "load-balance",
    }

    groups = base.get("proxy-groups")
    if isinstance(groups, list):
        all_names = [p["name"] for p in merged if p.get("name")]

        for group in groups:
            if not isinstance(group, dict):
                continue

            if group.get("type") not in group_types:
                continue

            current = group.get("proxies")
            if not isinstance(current, list):
                current = []
                group["proxies"] = current

            existing = set(str(x) for x in current)
            for name in all_names:
                if name not in existing:
                    current.append(name)

    return yaml.safe_dump(
        base,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def convert_all(target, urls):
    """
    Convert sources independently. Failed sources are isolated and
    returned to the caller for status reporting.
    """
    if not urls:
        raise RuntimeError(f"No subscription URLs available for target={target}")

    successful = []
    failed = []

    for i, url in enumerate(urls, 1):
        try:
            result = convert_one(target, url)
            successful.append((url, result))
            log(f"[CONVERT] {target} {i}/{len(urls)} OK  {url}")
        except Exception as exc:
            failed.append((url, str(exc)))
            log(f"[WARN] {target} {i}/{len(urls)} FAILED  {url}")
            log(f"       {exc}")

    if not successful:
        raise RuntimeError(
            f"All {target} conversions failed."
        )

    return successful, failed


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

    # Convert each subscription independently. A single broken source
    # therefore cannot cause the entire combined request to return 400.
    clash_outputs, clash_failed = convert_all(
        "clash",
        subscription_urls,
    )

    clash = merge_clash_outputs(clash_outputs)
    clash_count = validate_clash(clash)
    (OUTPUT / "clash.yaml").write_text(
        clash,
        encoding="utf-8",
    )

    # Convert V2Ray independently, decode each result, merge node links,
    # then encode the final subscription once.
    v2ray_outputs, v2ray_failed = convert_all(
        "v2ray",
        subscription_urls,
    )

    converted_nodes = []
    for source_url, converted in v2ray_outputs:
        found = decode_v2ray_output(converted)
        log(f"[V2RAY] {len(found):4d} nodes  {source_url}")
        converted_nodes.extend(found)

    converted_nodes = unique(converted_nodes)

    raw_v2ray = "\n".join(converted_nodes)
    if raw_v2ray:
        raw_v2ray += "\n"

    (OUTPUT / "v2ray-subconverter.txt").write_text(
        base64.b64encode(raw_v2ray.encode()).decode() + "\n",
        encoding="utf-8",
    )

    # Also keep direct node extraction for sources that expose standard
    # node URIs without requiring subconverter.
    nodes, failed_node_fetches = fetch_nodes(subscription_urls)
    nodes = unique(nodes + converted_nodes)
    save_nodes(nodes)

    write_meta(
        len(readme_sources),
        len(nodes),
        clash_count,
        failed_readmes,
        failed_node_fetches + len(clash_failed) + len(v2ray_failed),
    )

    log(f"[DONE] clash proxies = {clash_count}")
    log(f"[DONE] extracted/converted node links = {len(nodes)}")
    log(f"[DONE] clash conversion failures = {len(clash_failed)}")
    log(f"[DONE] v2ray conversion failures = {len(v2ray_failed)}")

    log(f"[DONE] clash proxies = {clash_count}")
    log(f"[DONE] extracted node links = {len(nodes)}")
    log(f"[DONE] output directory = {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"[FATAL] {exc}")
        sys.exit(1)
