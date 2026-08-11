#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import requests
from datetime import datetime
from pathlib import Path

SOURCES = {
    "toshare5": "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "abshare3": "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "mkshare3": "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "tolinkshare2": "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def extract_link(text: str) -> str | None:
    """每个 README 只取第一个匹配的订阅链接"""
    pattern = r'https?://[a-zA-Z0-9.-]+\.(?:tosslk|absslk|mcsslk)\.xyz/[a-f0-9]{32}'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def main():
    print(f"[{datetime.now()}] 开始抓取...")
    results = {}

    for name, url in SOURCES.items():
        try:
            print(f"Fetching: {name}")
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            link = extract_link(r.text)
            if link:
                results[name] = link
                print(f"  → {link}")
            else:
                print(f"  → 未找到链接")
        except Exception as e:
            print(f"  → 失败: {e}")

    print(f"\n成功获取 {len(results)} 个链接")

    # 生成 sub_links.txt（每行一个）
    lines = [f"{name}: {link}" for name, link in results.items()]
    Path("sub_links.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 生成纯链接列表（方便复制）
    pure_links = list(results.values())
    Path("links.txt").write_text("\n".join(pure_links) + "\n", encoding="utf-8")

    # 更新 README.md
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    readme = f"""# 免费订阅链接自动更新

> 最后更新时间：`{now}`

## 最新订阅链接（每个源一个）

| 来源 | 订阅链接（Clash / v2ray / 小火箭 通用） |
|------|----------------------------------------|
"""
    for name, link in results.items():
        readme += f"| **{name}** | `{link}` |\n"

    readme += f"""
## 使用方法

直接复制上面任意一个链接，添加到：

- **Clash / Clash Verge / mihomo / Stash**
- **v2rayN / v2rayNG**
- **小火箭 / Shadowrocket**

## 文件说明

- [`sub_links.txt`](./sub_links.txt) - 带来源标注的链接
- [`links.txt`](./links.txt) - 纯链接列表

> 这些是公共免费节点，稳定性有限，建议多备几个源，定期更新。
"""
    Path("README.md").write_text(readme, encoding="utf-8")

    # 占位文件（避免旧文件干扰）
    Path("clash.yaml").write_text(
        f"# 请直接使用上方原订阅链接\n# 更新时间: {now}\n", encoding="utf-8"
    )
    Path("v2ray.txt").write_text("", encoding="utf-8")

    print("已生成: README.md / sub_links.txt / links.txt")

if __name__ == "__main__":
    main()
