#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时抓取免费订阅链接，并尝试获取真实节点内容
使用 curl_cffi 绕过 Cloudflare 基础防护
"""

import re
import base64
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 优先使用 curl_cffi（对 Cloudflare 效果最好）
try:
    from curl_cffi import requests as cffi_requests
    USE_CFFI = True
    print("使用 curl_cffi")
except ImportError:
    import requests as cffi_requests
    USE_CFFI = False
    print("curl_cffi 未安装，回退到普通 requests（容易 403）")

SOURCES = [
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def extract_links(text: str) -> list[str]:
    pattern = r'https?://[a-zA-Z0-9.-]+\.(?:tosslk|absslk|mcsslk)\.xyz/[a-f0-9]{32}'
    return list(dict.fromkeys(re.findall(pattern, text)))

def fetch_sub_content(url: str) -> list[str]:
    """获取单个订阅的真实节点"""
    try:
        if USE_CFFI:
            # impersonate chrome 可以大幅提高过 Cloudflare 的概率
            r = cffi_requests.get(
                url,
                headers=HEADERS,
                timeout=20,
                impersonate="chrome120",
                allow_redirects=True,
            )
        else:
            r = cffi_requests.get(url, headers=HEADERS, timeout=20)

        if r.status_code != 200:
            print(f"  [{r.status_code}] {url}")
            return []

        content = r.text.strip()
        if not content:
            return []

        # 尝试 base64 解码
        nodes = []
        try:
            decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
            lines = decoded.splitlines()
        except Exception:
            lines = content.splitlines()

        for line in lines:
            line = line.strip()
            if line.startswith((
                "vmess://", "vless://", "ss://", "ssr://",
                "trojan://", "hysteria://", "hysteria2://",
                "tuic://", "wireguard://"
            )):
                nodes.append(line)

        print(f"  成功获取 {len(nodes)} 个节点 ← {url}")
        return nodes

    except Exception as e:
        print(f"  失败 {url}: {e}")
        return []

def main():
    print(f"[{datetime.now()}] 开始抓取...")
    all_nodes = []
    seen = set()
    sub_links = []

    # 1. 先抓 README 拿到最新订阅链接
    for src in SOURCES:
        try:
            print(f"Fetching README: {src}")
            if USE_CFFI:
                r = cffi_requests.get(src, headers=HEADERS, timeout=15, impersonate="chrome120")
            else:
                r = cffi_requests.get(src, headers=HEADERS, timeout=15)
            r.raise_for_status()
            links = extract_links(r.text)
            print(f"  找到链接: {links}")
            sub_links.extend(links)
        except Exception as e:
            print(f"Error: {src} → {e}")

    sub_links = list(dict.fromkeys(sub_links))
    print(f"\n共找到 {len(sub_links)} 个订阅链接，开始获取节点内容...\n")

    # 2. 并发获取节点（提高速度）
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_sub_content, url): url for url in sub_links}
        for future in as_completed(futures):
            nodes = future.result()
            for node in nodes:
                if node not in seen:
                    seen.add(node)
                    all_nodes.append(node)

    print(f"\n最终去重后节点数量: {len(all_nodes)}")

    # 3. 生成文件
    # v2ray 订阅（base64）
    v2ray_b64 = base64.b64encode("\n".join(all_nodes).encode("utf-8")).decode()
    Path("v2ray.txt").write_text(v2ray_b64, encoding="utf-8")

    # 原始节点列表
    Path("nodes_raw.txt").write_text("\n".join(all_nodes), encoding="utf-8")

    # 订阅链接列表（备用）
    Path("sub_links.txt").write_text("\n".join(sub_links) + "\n", encoding="utf-8")

    # 简单的 clash 提示文件
    Path("clash.yaml").write_text(
        f"""# 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 节点数量: {len(all_nodes)}
# 建议直接使用 v2ray.txt 或原订阅链接，效果更好

# 如果你想用完整 Clash 配置，推荐把 v2ray.txt 丢给 subconverter：
# https://sub.xeton.dev/sub?target=clash&url=你的v2ray.txt的raw地址
""",
        encoding="utf-8"
    )

    # 更新 README
    readme = f"""# 免费节点自动更新

- 更新时间：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
- 节点数量：`{len(all_nodes)}`

## 订阅地址

| 类型 | 地址 |
|------|------|
| **v2ray / 小火箭 / v2rayN** | [`v2ray.txt`](./v2ray.txt) |
| 原始节点列表 | [`nodes_raw.txt`](./nodes_raw.txt) |
| 原始订阅链接 | [`sub_links.txt`](./sub_links.txt) |

### 使用方法

1. 复制 `v2ray.txt` 的 raw 地址到客户端订阅
2. 或直接使用 `sub_links.txt` 里的原始链接（推荐，稳定性更高）

> 免费节点，请勿过度依赖，建议多备几个订阅源。
"""
    Path("README.md").write_text(readme, encoding="utf-8")

    print("文件已生成：v2ray.txt / nodes_raw.txt / sub_links.txt / README.md")

if __name__ == "__main__":
    main()
