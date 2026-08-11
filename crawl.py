#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import base64
import requests
from pathlib import Path
from datetime import datetime, timezone

SOURCES_FILE = Path("sources.txt")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 匹配订阅链接的正则（覆盖常见域名）
SUB_PATTERN = re.compile(
    r'https?://[a-zA-Z0-9\-]+\.(?:tosslk|absslk|mcsslk|tolink)\.xyz/[a-f0-9]{32}',
    re.IGNORECASE
)

def fetch_text(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[ERROR] 获取失败 {url}: {e}")
        return ""

def extract_subs(text: str) -> list[str]:
    return list(set(SUB_PATTERN.findall(text)))

def fetch_sub_content(url: str) -> str:
    """获取订阅内容（通常是 base64 或 yaml）"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        print(f"[ERROR] 订阅内容获取失败 {url}: {e}")
        return ""

def main():
    sources = [line.strip() for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    all_links = []
    for src in sources:
        print(f"正在爬取: {src}")
        text = fetch_text(src)
        links = extract_subs(text)
        print(f"  → 找到 {len(links)} 个订阅链接")
        all_links.extend(links)

    # 去重
    all_links = sorted(set(all_links))
    print(f"\n最终去重后共 {len(all_links)} 个订阅链接")

    # 保存原始链接
    result = {
        "update_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "count": len(all_links),
        "links": all_links
    }
    (OUTPUT_DIR / "links.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 合并订阅内容
    combined_nodes = []
    for link in all_links:
        content = fetch_sub_content(link)
        if not content:
            continue
        # 尝试 base64 解码
        try:
            decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
            # 按行拆分节点
            for line in decoded.splitlines():
                line = line.strip()
                if line and (line.startswith("vmess://") or 
                             line.startswith("vless://") or 
                             line.startswith("ss://") or 
                             line.startswith("trojan://") or
                             line.startswith("hysteria")):
                    combined_nodes.append(line)
        except Exception:
            # 不是 base64，可能是 yaml（Clash），这里简单跳过或自行处理
            pass

    # 去重节点
    combined_nodes = list(dict.fromkeys(combined_nodes))  # 保持顺序去重
    print(f"合并后有效节点数: {len(combined_nodes)}")

    # 生成 v2ray 订阅（base64）
    v2ray_raw = "\n".join(combined_nodes)
    v2ray_b64 = base64.b64encode(v2ray_raw.encode("utf-8")).decode("utf-8")
    (OUTPUT_DIR / "v2ray.txt").write_text(v2ray_b64, encoding="utf-8")

    # 生成简单 Clash 订阅（把节点转成 proxies 列表，这里只做示例）
    # 真正完整的 Clash 配置需要更复杂的转换，推荐直接用订阅链接
    clash_content = f"""# 自动生成 - 更新时间: {result['update_time']}
# 建议直接使用下面的原始订阅链接，效果更稳定

proxies: []
proxy-groups: []
rules: []
"""
    (OUTPUT_DIR / "clash.txt").write_text(
        base64.b64encode(clash_content.encode("utf-8")).decode("utf-8"),
        encoding="utf-8"
    )

    # 额外输出纯文本链接文件，方便直接复制
    (OUTPUT_DIR / "raw_links.txt").write_text("\n".join(all_links), encoding="utf-8")

    print("\n完成！文件已写入 output/ 目录")

if __name__ == "__main__":
    main()
