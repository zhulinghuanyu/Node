#!/usr/bin/env python3
"""
Subscription crawler.

Pipeline:

README pages
    -> extract real subscription URLs
    -> Python downloads each subscription
    -> inspect returned content
    -> convert via subconverter using data URI
    -> merge Clash configs
    -> merge V2Ray node links
    -> write output files

The important design choice is that Python downloads the subscription
first. subconverter does not need to access third-party source servers.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.txt"
OUTPUT = ROOT / "output"

FETCH_TIMEOUT = int(os.getenv("FETCH_TIMEOUT", "30"))
CONVERT_TIMEOUT = int(os.getenv("CONVERT_TIMEOUT", "180"))
SUBCONVERTER = os.getenv(
    "SUBCONVERTER_URL",
    "http://127.0.0.1:25500",
)

HEADERS = {
    "User-Agent": (
        "clash.meta/1.19.8 "
        "(https://github.com/MetaCubeX/mihomo)"
    ),
    "Accept": "*/*",
}

URL_RE = re.compile(
    r"https?://[^\s<>\]\"'`()]+",
    re.IGNORECASE,
)

IMAGE_EXT = re.compile(
    r"\.(?:png|jpe?g|gif|webp|svg|ico)(?:\?.*)?$",
    re.IGNORECASE,
)

NODE_SCHEMES = (
    "vmess://",
    "vless://",
    "trojan://",
    "ss://",
    "ssr://",
    "hysteria://",
    "hysteria2://",
    "hy2://",
    "tuic://",
)

SKIP_HOSTS = {
    "github.com",
    "www.github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
    "www.google.com",
    "google.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
}


def log(message: str) -> None:
    print(message, flush=True)


def unique(items: list[str]) -> list[str]:
    result = []
    seen = set()

    for item in items:
        item = item.strip()

        if item and item not in seen:
            seen.add(item)
            result.append(item)

    return result


def read_sources() -> list[str]:
    if not CONFIG.exists():
        raise FileNotFoundError(
            f"Missing source file: {CONFIG}"
        )

    sources = []

    for line in CONFIG.read_text(
        encoding="utf-8"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        sources.append(line)

    return unique(sources)


def clean_url(url: str) -> str:
    return url.rstrip(
        ".,;:!?)]}>`\"'"
    )


def is_candidate(url: str) -> bool:
    """
    Reject obvious non-subscription URLs.

    The supplied README files contain invitation URLs such as:
        https://example.com/i/XXXX

    Those are not subscription feeds and make subconverter return
    'No nodes were found'.
    """

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return False

    host = (
        parsed.hostname or ""
    ).lower()

    path = (
        parsed.path or ""
    )

    if not host:
        return False

    if host in SKIP_HOSTS:
        return False

    if host.endswith(".github.com"):
        return False

    if IMAGE_EXT.search(path):
        return False

    # Invitation / referral / registration URLs.
    bad_path_patterns = (
        r"^/i(?:/|$)",
        r"^/invite(?:/|$)",
        r"^/invitation(?:/|$)",
        r"^/register(?:/|$)",
        r"^/signup(?:/|$)",
        r"^/sign-up(?:/|$)",
        r"^/ref(?:/|$)",
        r"^/referral(?:/|$)",
    )

    for pattern in bad_path_patterns:
        if re.match(
            pattern,
            path,
            re.IGNORECASE,
        ):
            return False

    return True


def extract_urls(text: str) -> list[str]:
    """
    Extract subscription URLs.

    Priority:
      1. URLs inside Markdown fenced code blocks.
      2. URLs near subscription-related headings.

    We deliberately do NOT scan the entire README first, because
    registration/referral URLs are often present in the same document.
    """

    result = []

    # ------------------------------------------------------------
    # 1. Fenced code blocks
    # ------------------------------------------------------------
    fenced_blocks = re.findall(
        r"```(?:[^\n]*)\n(.*?)```",
        text,
        flags=re.S,
    )

    for block in fenced_blocks:
        for raw in URL_RE.findall(block):
            url = clean_url(raw)

            if is_candidate(url):
                result.append(url)

    if result:
        return unique(result)

    # ------------------------------------------------------------
    # 2. Fallback: subscription-related context
    # ------------------------------------------------------------
    lines = text.splitlines()

    keywords = (
        "clash",
        "v2ray",
        "v2rayn",
        "shadowrocket",
        "surge",
        "loon",
        "sing-box",
        "singbox",
        "小火箭",
        "订阅",
        "subscription",
    )

    for i, line in enumerate(lines):
        lower = line.lower()

        if not any(
            keyword in lower
            for keyword in keywords
        ):
            continue

        context = "\n".join(
            lines[i:i + 6]
        )

        for raw in URL_RE.findall(context):
            url = clean_url(raw)

            if is_candidate(url):
                result.append(url)

    return unique(result)


def fetch_readme(url: str) -> str:
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=FETCH_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


def fetch_subscription_payload(
    url: str,
) -> bytes:
    """
    Download subscription content directly from Python.

    This avoids making subconverter access the third-party source.
    """

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=FETCH_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    content = response.content

    if not content:
        raise RuntimeError(
            "subscription returned empty body"
        )

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    log(
        f"[SOURCE] status={response.status_code} "
        f"bytes={len(content)} "
        f"type={content_type}"
    )

    if response.url != url:
        log(
            f"[SOURCE] redirected to: "
            f"{response.url}"
        )

    preview = content[:160].decode(
        "utf-8",
        errors="replace",
    )

    preview = (
        preview
        .replace("\r", " ")
        .replace("\n", " ")
    )

    log(
        f"[SOURCE] preview: {preview}"
    )

    return content


def decode_base64_text(
    text: str,
) -> str | None:
    """
    Decode common Base64 / URL-safe Base64 content.
    """

    compact = re.sub(
        r"\s+",
        "",
        text.strip(),
    )

    if not compact:
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9+/=_-]+",
        compact,
    ):
        return None

    try:
        padded = (
            compact
            + "=" * (-len(compact) % 4)
        )

        decoded = base64.urlsafe_b64decode(
            padded
        ).decode(
            "utf-8",
            errors="ignore",
        )

        if any(
            scheme in decoded
            for scheme in NODE_SCHEMES
        ):
            return decoded

    except Exception:
        pass

    return None


def detect_format(
    content: bytes,
) -> str:
    """
    Detect common subscription formats.
    """

    text = content.decode(
        "utf-8",
        errors="ignore",
    ).strip()

    if not text:
        return "empty"

    # Clash / Mihomo YAML
    try:
        data = yaml.safe_load(text)

        if isinstance(data, dict):
            if isinstance(
                data.get("proxies"),
                list,
            ):
                return "clash-yaml"

    except Exception:
        pass

    # Direct URI nodes
    if any(
        line.strip().startswith(
            NODE_SCHEMES
        )
        for line in text.splitlines()
    ):
        return "node-uri"

    # Base64 node list
    decoded = decode_base64_text(text)

    if decoded:
        return "base64-node-list"

    # JSON
    if (
        text.startswith("{")
        or text.startswith("[")
    ):
        return "json"

    # HTML
    lower = text[:2000].lower()

    if (
        "<html" in lower
        or "<!doctype" in lower
        or "<head" in lower
    ):
        return "html"

    return "unknown"


def normalize_node_text(text: str) -> str:
    """
    Normalize common subscription text before extracting node URIs.
    """

    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Some providers return percent-encoded node links.
    try:
        from urllib.parse import unquote
        decoded = unquote(text)
        if any(
            scheme in decoded
            for scheme in NODE_SCHEMES
        ):
            text = decoded
    except Exception:
        pass

    return text.strip()


def extract_node_links(content: bytes) -> list[str]:
    """
    Extract node URI lines from:
      - plain text
      - Base64 subscription
      - subconverter V2Ray output

    The old implementation could miss valid output when the response
    contained surrounding whitespace/BOM or slightly different Base64
    formatting.
    """

    raw_text = content.decode(
        "utf-8",
        errors="ignore",
    )

    candidates = [
        normalize_node_text(raw_text)
    ]

    # Try normal Base64 and URL-safe Base64.
    compact = re.sub(
        r"\s+",
        "",
        raw_text.strip(),
    )

    if compact:
        try:
            padded = (
                compact
                + "=" * (-len(compact) % 4)
            )

            decoded = base64.b64decode(
                padded,
                altchars=b"-_",
                validate=False,
            ).decode(
                "utf-8",
                errors="ignore",
            )

            decoded = normalize_node_text(
                decoded
            )

            if decoded:
                candidates.append(decoded)

        except Exception:
            pass

    nodes = []

    for candidate in candidates:

        for line in candidate.splitlines():

            line = line.strip()

            if not line:
                continue

            # Remove accidental Markdown list markers.
            line = re.sub(
                r"^[-*+]\s+",
                "",
                line,
            ).strip()

            if line.startswith(
                NODE_SCHEMES
            ):
                nodes.append(line)

    return unique(nodes)


def is_base64_subscription(text: str) -> bool:
    """
    Check whether text is a Base64-encoded node subscription.
    """

    compact = re.sub(
        r"\s+",
        "",
        text.strip(),
    )

    if not compact:
        return False

    try:
        padded = (
            compact
            + "=" * (-len(compact) % 4)
        )

        decoded = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=False,
        ).decode(
            "utf-8",
            errors="ignore",
        )

        return bool(
            extract_node_links(
                decoded.encode("utf-8")
            )
        )

    except Exception:
        return False



def make_data_uri(
    content: bytes,
) -> str:
    """
    Convert raw subscription bytes to a data URI.

    subconverter accepts data URI input.
    """

    encoded = base64.b64encode(
        content
    ).decode("ascii")

    return (
        "data:text/plain;base64,"
        + encoded
    )


def convert_one(
    target: str,
    url: str,
) -> str:
    """
    1. Python downloads the subscription.
    2. Convert the downloaded bytes to data URI.
    3. Send data URI to subconverter.

    This is the key fix for sources that can be downloaded by
    GitHub Runner but cannot be fetched by the subconverter container.
    """

    content = fetch_subscription_payload(
        url
    )

    detected = detect_format(
        content
    )

    log(
        f"[SOURCE] detected format: "
        f"{detected}"
    )

    # If source is already Clash YAML and Clash is requested,
    # use it directly instead of converting it again.
    if (
        target == "clash"
        and detected == "clash-yaml"
    ):
        return content.decode(
            "utf-8",
            errors="ignore",
        )

    data_uri = make_data_uri(
        content
    )

    log(
        f"[CONVERT] target={target} "
        f"source_bytes={len(content)} "
        f"data_uri_bytes={len(data_uri)}"
    )

    response = requests.get(
        f"{SUBCONVERTER}/sub",
        params={
            "target": target,
            "url": data_uri,
        },
        headers=HEADERS,
        timeout=CONVERT_TIMEOUT,
    )

    if not response.ok:

        body = (
            response.text[:2000]
            .replace("\n", " ")
        )

        raise RuntimeError(
            f"HTTP {response.status_code} "
            f"from subconverter: {body}"
        )

    if not response.text.strip():

        raise RuntimeError(
            "subconverter returned empty output"
        )

    return response.text


def convert_all(
    target: str,
    urls: list[str],
):
    """
    Convert each source independently.

    A failed source does not stop the other sources.
    """

    successful = []
    failed = []

    for index, url in enumerate(
        urls,
        1,
    ):

        try:

            result = convert_one(
                target,
                url,
            )

            successful.append(
                (
                    url,
                    result,
                )
            )

            log(
                f"[CONVERT] "
                f"{target} "
                f"{index}/{len(urls)} "
                f"OK  {url}"
            )

        except Exception as exc:

            failed.append(
                (
                    url,
                    str(exc),
                )
            )

            log(
                f"[WARN] "
                f"{target} "
                f"{index}/{len(urls)} "
                f"FAILED  {url}"
            )

            log(
                f"       {exc}"
            )

    return successful, failed


def validate_clash(
    text: str,
) -> int:
    data = yaml.safe_load(text)

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Clash output is not a YAML mapping"
        )

    proxies = data.get(
        "proxies"
    )

    if not isinstance(
        proxies,
        list,
    ):
        raise RuntimeError(
            "Clash output has no 'proxies' list"
        )

    return len(proxies)


def merge_clash_outputs(
    outputs,
) -> tuple[str, int]:
    """
    Merge independently converted Clash configs.

    The first valid config supplies general settings.
    Proxy definitions from all configs are deduplicated by name.
    """

    configs = []

    for source_url, raw in outputs:

        try:
            data = yaml.safe_load(
                raw
            )

        except Exception as exc:

            log(
                f"[WARN] invalid Clash YAML: "
                f"{source_url} :: {exc}"
            )

            continue

        if not isinstance(
            data,
            dict,
        ):
            log(
                f"[WARN] Clash output is not "
                f"a mapping: {source_url}"
            )
            continue

        proxies = data.get(
            "proxies"
        )

        if not isinstance(
            proxies,
            list,
        ):
            log(
                f"[WARN] no proxies in "
                f"Clash output: {source_url}"
            )
            continue

        configs.append(
            (
                source_url,
                data,
            )
        )

    if not configs:
        raise RuntimeError(
            "No valid Clash configurations were produced."
        )

    base = configs[0][1]

    merged = []
    seen_names = set()

    for _, data in configs:

        for proxy in (
            data.get("proxies")
            or []
        ):

            if not isinstance(
                proxy,
                dict,
            ):
                continue

            name = str(
                proxy.get("name", "")
            ).strip()

            if not name:
                continue

            if name in seen_names:
                continue

            seen_names.add(name)
            merged.append(proxy)

    base["proxies"] = merged

    # Add merged proxy names to standard selectable groups.
    groups = base.get(
        "proxy-groups"
    )

    selectable_types = {
        "select",
        "url-test",
        "fallback",
        "load-balance",
    }

    if isinstance(
        groups,
        list,
    ):

        all_proxy_names = [
            p["name"]
            for p in merged
            if p.get("name")
        ]

        for group in groups:

            if not isinstance(
                group,
                dict,
            ):
                continue

            if group.get(
                "type"
            ) not in selectable_types:
                continue

            current = group.get(
                "proxies"
            )

            if not isinstance(
                current,
                list,
            ):
                current = []

            existing = set(
                str(x)
                for x in current
            )

            for name in all_proxy_names:

                if name not in existing:
                    current.append(name)

            group["proxies"] = current

    output = yaml.safe_dump(
        base,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    return output, len(merged)


def save_nodes(nodes: list[str]) -> None:
    raw = "\n".join(nodes)

    if raw:
        raw += "\n"

    (
        OUTPUT / "nodes.txt"
    ).write_text(
        raw,
        encoding="utf-8",
    )

    encoded = base64.b64encode(
        raw.encode("utf-8")
    ).decode("ascii")

    (
        OUTPUT / "v2ray.txt"
    ).write_text(
        encoded + "\n" if encoded else "",
        encoding="utf-8",
    )


def save_v2ray_output(
    outputs,
    nodes: list[str],
) -> None:
    """
    Save the actual subconverter V2Ray output.

    v2ray-subconverter.txt:
        Raw output returned by subconverter. If it is already a
        Base64 subscription, keep it exactly as returned.

    v2ray.txt:
        Preferred normalized Base64 subscription built from extracted
        node URIs. If node extraction finds nothing but subconverter
        returned valid Base64, fall back to the raw converted output.
    """

    raw_outputs = []

    for source_url, converted in outputs:

        converted = (
            converted
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

        if converted:
            raw_outputs.append(
                converted
            )

    raw_combined = ""

    if raw_outputs:
        # If there are multiple V2Ray conversions, they may each be
        # Base64 subscriptions. Decode them and merge the node URIs.
        raw_combined = "\n".join(
            raw_outputs
        ) + "\n"

    (
        OUTPUT / "v2ray-subconverter.txt"
    ).write_text(
        raw_combined,
        encoding="utf-8",
    )

    if nodes:
        normalized = "\n".join(nodes) + "\n"

        encoded = base64.b64encode(
            normalized.encode("utf-8")
        ).decode("ascii")

        (
            OUTPUT / "v2ray.txt"
        ).write_text(
            encoded + "\n",
            encoding="utf-8",
        )

        return

    # Fallback:
    # If subconverter successfully returned a valid Base64
    # subscription but our node parser could not extract it,
    # publish that output instead of creating an empty file.
    for converted in raw_outputs:

        if is_base64_subscription(
            converted
        ):
            (
                OUTPUT / "v2ray.txt"
            ).write_text(
                converted.strip() + "\n",
                encoding="utf-8",
            )
            return

    # Last fallback: raw V2Ray URI text.
    for converted in raw_outputs:

        if extract_node_links(
            converted.encode("utf-8")
        ):
            (
                OUTPUT / "v2ray.txt"
            ).write_text(
                base64.b64encode(
                    converted.encode("utf-8")
                ).decode("ascii")
                + "\n",
                encoding="utf-8",
            )
            return

    (
        OUTPUT / "v2ray.txt"
    ).write_text(
        "",
        encoding="utf-8",
    )



def save_sources(
    urls: list[str],
) -> None:

    (
        OUTPUT / "sources.txt"
    ).write_text(
        "\n".join(urls) + "\n",
        encoding="utf-8",
    )


def write_status(
    *,
    readme_count: int,
    subscription_count: int,
    clash_success: int,
    clash_failed: list,
    v2ray_success: int,
    v2ray_failed: list,
    node_count: int,
    failed_readmes: int,
    failed_node_fetches: int,
    clash_proxy_count: int,
) -> None:

    status = {
        "updated_at_utc": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),

        "readme_sources": readme_count,

        "subscription_urls": subscription_count,

        "clash": {
            "successful_sources": clash_success,
            "failed_sources": len(
                clash_failed
            ),
            "proxies": clash_proxy_count,
            "failed": [
                {
                    "url": url,
                    "error": error,
                }
                for url, error
                in clash_failed
            ],
        },

        "v2ray": {
            "successful_sources": v2ray_success,
            "failed_sources": len(
                v2ray_failed
            ),
            "failed": [
                {
                    "url": url,
                    "error": error,
                }
                for url, error
                in v2ray_failed
            ],
        },

        "nodes": {
            "unique": node_count,
            "direct_fetch_failures": (
                failed_node_fetches
            ),
        },

        "failed_readmes": failed_readmes,
    }

    (
        OUTPUT / "status.json"
    ).write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    readme_sources = read_sources()

    log(
        f"[INFO] README sources = "
        f"{len(readme_sources)}"
    )

    subscription_urls = []
    failed_readmes = 0

    # ------------------------------------------------------------
    # Read all README pages.
    # ------------------------------------------------------------

    for index, source in enumerate(
        readme_sources,
        1,
    ):

        try:

            text = fetch_readme(
                source
            )

            found = extract_urls(
                text
            )

            log(
                f"[README] "
                f"{index}/{len(readme_sources)} "
                f"{len(found)} "
                f"{source}"
            )

            for url in found:
                log(
                    f"         -> {url}"
                )

            subscription_urls.extend(
                found
            )

        except Exception as exc:

            failed_readmes += 1

            log(
                f"[WARN] README failed: "
                f"{source}"
            )

            log(
                f"       {exc}"
            )

    subscription_urls = unique(
        subscription_urls
    )

    log(
        f"[INFO] unique subscription URLs "
        f"= {len(subscription_urls)}"
    )

    if not subscription_urls:
        raise RuntimeError(
            "No subscription URLs were found."
        )

    save_sources(
        subscription_urls
    )

    # ------------------------------------------------------------
    # Clash
    # ------------------------------------------------------------

    clash_outputs, clash_failed = (
        convert_all(
            "clash",
            subscription_urls,
        )
    )

    clash_proxy_count = 0

    if clash_outputs:

        clash_yaml, clash_proxy_count = (
            merge_clash_outputs(
                clash_outputs
            )
        )

        (
            OUTPUT / "clash.yaml"
        ).write_text(
            clash_yaml,
            encoding="utf-8",
        )

        log(
            f"[DONE] Clash proxies = "
            f"{clash_proxy_count}"
        )

    else:

        log(
            "[WARN] No Clash source "
            "converted successfully."
        )

    # ------------------------------------------------------------
    # V2Ray
    # ------------------------------------------------------------

    v2ray_outputs, v2ray_failed = (
        convert_all(
            "v2ray",
            subscription_urls,
        )
    )

    log(
        f"[INFO] successful V2Ray conversions = "
        f"{len(v2ray_outputs)}"
    )

    v2ray_nodes = []

    for source_url, converted in (
        v2ray_outputs
    ):

        nodes = extract_node_links(
            converted.encode(
                "utf-8"
            )
        )

        log(
            f"[V2RAY] "
            f"{len(nodes):4d} nodes "
            f"{source_url}"
        )

        v2ray_nodes.extend(
            nodes
        )

    v2ray_nodes = unique(
        v2ray_nodes
    )

    # ------------------------------------------------------------
    # Direct node extraction
    # ------------------------------------------------------------

    direct_nodes = []
    failed_node_fetches = 0

    for index, url in enumerate(
        subscription_urls,
        1,
    ):

        try:

            content = (
                fetch_subscription_payload(
                    url
                )
            )

            nodes = extract_node_links(
                content
            )

            log(
                f"[NODES] "
                f"{index}/{len(subscription_urls)} "
                f"{len(nodes):4d} "
                f"{url}"
            )

            direct_nodes.extend(
                nodes
            )

        except Exception as exc:

            failed_node_fetches += 1

            log(
                f"[WARN] direct node fetch "
                f"failed: {url}"
            )

            log(
                f"       {exc}"
            )

    all_nodes = unique(
        v2ray_nodes + direct_nodes
    )

    # Save normalized node list and V2Ray Base64 subscription.
    save_nodes(
        all_nodes
    )

    # IMPORTANT:
    # Keep the actual output returned by subconverter. The previous
    # version accidentally overwrote this file with the already
    # extracted node list, which could become empty.
    save_v2ray_output(
        v2ray_outputs,
        all_nodes,
    )

    write_status(
        readme_count=len(
            readme_sources
        ),
        subscription_count=len(
            subscription_urls
        ),
        clash_success=len(
            clash_outputs
        ),
        clash_failed=clash_failed,
        v2ray_success=len(
            v2ray_outputs
        ),
        v2ray_failed=v2ray_failed,
        node_count=len(
            all_nodes
        ),
        failed_readmes=failed_readmes,
        failed_node_fetches=(
            failed_node_fetches
        ),
        clash_proxy_count=(
            clash_proxy_count
        ),
    )

    log(
        f"[DONE] unique node links = "
        f"{len(all_nodes)}"
    )

    # ------------------------------------------------------------
    # Failure policy:
    #
    # Only fail the GitHub job if ALL subscription conversions
    # failed. A single dead source should not prevent publication.
    # ------------------------------------------------------------

    if (
        not clash_outputs
        and not v2ray_outputs
        and not all_nodes
    ):
        raise RuntimeError(
            "All subscription conversions "
            "and node extraction failed."
        )


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        log(
            f"[FATAL] {exc}"
        )

        sys.exit(1)
