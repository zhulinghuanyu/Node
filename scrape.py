#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import requests
import base64
from datetime import datetime
from pathlib import Path

SOURCES = [
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def extract_links(text: str) -> list[str]:
    # 匹配 https://xxx.xxx.xyz/xxxxxxxx 这种订阅链接
    pattern = r'https?://[a-zA-Z0-9.-]+\.(?:tosslk|absslk|mcsslk)\.xyz/[a-f0-9]{32}'
    return list(set(re.findall(pattern, text)))

def fetch_nodes(sub_url: str) -> list[str]:
    """获取单个订阅内容，返回节点列表（vmess/ss/trojan 等）"""
    try:
        r = requests.get(sub_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        content = r.text.strip()
        # 有的是 base64，有的是明文
        try:
            decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
            lines = [line.strip() for line in decoded.splitlines() if line.strip()]
        except Exception:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        # 只保留协议开头的节点
        return [l for l in lines if l.startswith(('vmess://', 'ss://', 'ssr://', 'trojan://', 'vless://', 'hysteria://', 'hysteria2://', 'tuic://'))]
    except Exception as e:
        print(f"Failed to fetch {sub_url}: {e}")
        return []

def main():
    all_nodes = []
    seen = set()

    print(f"[{datetime.now()}] Start scraping...")

    for src in SOURCES:
        try:
            print(f"Fetching README: {src}")
            r = requests.get(src, headers=HEADERS, timeout=10)
            r.raise_for_status()
            links = extract_links(r.text)
            print(f"  Found links: {links}")

            for link in links:
                nodes = fetch_nodes(link)
                for node in nodes:
                    if node not in seen:
                        seen.add(node)
                        all_nodes.append(node)
        except Exception as e:
            print(f"Error processing {src}: {e}")

    print(f"Total unique nodes: {len(all_nodes)}")

    # 生成 v2ray 订阅（base64）
    v2ray_content = base64.b64encode('\n'.join(all_nodes).encode()).decode()
    Path("v2ray.txt").write_text(v2ray_content, encoding='utf-8')

    # 生成简单 Clash 订阅（proxies 列表）
    # 注意：这里只做最基础转换，复杂配置建议用 subconverter
    clash_proxies = []
    for i, node in enumerate(all_nodes, 1):
        # 简化处理：直接把原始链接当作 proxy 名称
        # 实际生产环境建议用 subconverter 或 mihomo 转换
        name = f"节点{i}"
        clash_proxies.append(f"  - name: \"{name}\"\n    type: http\n    # raw: {node}")

    clash_yaml = f"""# 自动生成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 节点数量: {len(all_nodes)}
# 建议配合 subconverter 使用更完整的转换

proxies:
{chr(10).join(clash_proxies) if clash_proxies else '  []'}

proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - DIRECT
{chr(10).join(f'      - 节点{i}' for i in range(1, len(all_nodes)+1))}

rules:
  - MATCH,PROXY
"""
    Path("clash.yaml").write_text(clash_yaml, encoding='utf-8')

    # 同时生成原始节点列表方便调试
    Path("nodes_raw.txt").write_text('\n'.join(all_nodes), encoding='utf-8')

    print("Generated: v2ray.txt / clash.yaml / nodes_raw.txt")

if __name__ == "__main__":
    main()
