#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

SOURCES = [
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
]

# 公共 subconverter 后端（可多备几个）
SUBCONVERTERS = [
    "https://url.v1.mk/sub",
    "https://sub.xeton.dev/sub",
    "https://api.dler.io/sub",
    "https://subapi.cmliussss.net/sub",
    "https://api.wcc.best/sub",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def extract_links(text: str) -> list[str]:
    pattern = r'https?://[a-zA-Z0-9.-]+\.(?:tosslk|absslk|mcsslk)\.xyz/[a-f0-9]{32}'
    return list(dict.fromkeys(re.findall(pattern, text)))

def convert_with_subconverter(links: list[str], target: str = "clash") -> str | None:
    """调用公共 subconverter 转换"""
    if not links:
        return None

    # 多个订阅用 | 连接
    url_param = "|".join(links)
    encoded_url = quote(url_param, safe="")

    for backend in SUBCONVERTERS:
        try:
            api = f"{backend}?target={target}&url={encoded_url}&list=true"
            print(f"  尝试后端: {backend}")
            r = requests.get(api, headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.text.strip():
                print(f"  ✅ 转换成功 ← {backend}")
                return r.text
            else:
                print(f"  ❌ 状态码 {r.status_code}")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
    return None

def main():
    print(f"[{datetime.now()}] 开始抓取...")
    all_links = []

    for src in SOURCES:
        try:
            print(f"Fetching README: {src}")
            r = requests.get(src, headers=HEADERS, timeout=15)
            r.raise_for_status()
            links = extract_links(r.text)
            print(f"  找到: {links}")
            all_links.extend(links)
        except Exception as e:
            print(f"  失败: {e}")

    unique_links = list(dict.fromkeys(all_links))
    print(f"\n共 {len(unique_links)} 个订阅链接")

    if not unique_links:
        print("没有找到任何链接，退出")
        return

    # 保存原始链接
    Path("sub_links.txt").write_text("\n".join(unique_links) + "\n", encoding="utf-8")

    # 调用 subconverter 生成 Clash 配置
    print("\n正在调用公共 subconverter 生成 Clash 配置...")
    clash_content = convert_with_subconverter(unique_links, target="clash")
    if clash_content:
        Path("clash.yaml").write_text(clash_content, encoding="utf-8")
        print("clash.yaml 已生成")
    else:
        Path("clash.yaml").write_text("# 转换失败，请稍后重试\n", encoding="utf-8")

    # 生成 v2ray 格式（base64）
    print("\n正在生成 v2ray 格式...")
    v2ray_content = convert_with_subconverter(unique_links, target="v2ray")
    if v2ray_content:
        Path("v2ray.txt").write_text(v2ray_content, encoding="utf-8")
        print("v2ray.txt 已生成")
    else:
        # 兜底：直接把链接列表 base64
        import base64
        Path("v2ray.txt").write_text(
            base64.b64encode("\n".join(unique_links).encode()).decode(),
            encoding="utf-8"
        )

    # 更新 README
    readme = f"""# 免费节点自动更新

> 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 订阅源数量：{len(unique_links)}

## 订阅地址

| 类型 | 地址 |
|------|------|
| **Clash / mihomo** | [`clash.yaml`](./clash.yaml) |
| **v2ray / 小火箭 / v2rayN** | [`v2ray.txt`](./v2ray.txt) |
| 原始订阅链接 | [`sub_links.txt`](./sub_links.txt) |

### 原始链接（可直接使用）

"""
    for i, link in enumerate(unique_links, 1):
        readme += f"{i}. `{link}`\n"

    readme += "\n> 由公共 subconverter 自动转换生成，免费节点请勿过度依赖。"
    Path("README.md").write_text(readme, encoding="utf-8")

    print("\n全部完成！")

if __name__ == "__main__":
    main()
