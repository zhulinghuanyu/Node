import requests
import re
import base64
import json
import urllib.parse
import yaml

README_URLS = [
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ================= 订阅链接精准提取 =================
EXCLUDE_DOMAINS = ['github.com', 'githubusercontent.com', 'jsdelivr.net',
                   't.me', 'telegram.me', 'youtube.com', 'twitter.com', 'x.com']
EXCLUDE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.ico', '.svg')
# 行内含这些词 => 推广/注册链接，跳过
EXCLUDE_LINE_KEYWORDS = ['注册', '试用', '邀请', '购买', '续费', '官网',
                         '机场', '下载', '教程', '客服', 'banner', '广告']
SUB_KEYWORDS = ['订阅', 'subscription']

def clean_url(u):
    return u.strip().rstrip('.,)!]\'"')

def is_bad_url(u):
    low = u.lower()
    return any(d in low for d in EXCLUDE_DOMAINS) or low.endswith(EXCLUDE_EXT)

def extract_sub_urls(text):
    """只提取真正的订阅链接，过滤注册/推广/图片等杂链"""
    sub_urls = set()

    # ① 代码块 ``` 内的链接（订阅链接通常单独放代码块里）
    for block in re.findall(r'```[\s\S]*?```', text):
        for u in re.findall(r'https?://[^\s<>"\']+', block):
            u = clean_url(u)
            if u and not is_bad_url(u):
                sub_urls.add(u)

    # ② “订阅”关键词 同行 / 下方4行内 的链接
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if any(k in line.lower() for k in SUB_KEYWORDS):
            for u in re.findall(r'https?://[^\s<>"\']+', line):
                u = clean_url(u)
                if u and not is_bad_url(u):
                    sub_urls.add(u)
            for nxt in lines[i + 1: i + 5]:
                nxt = nxt.strip()
                if nxt.startswith('#') or nxt.startswith('>') or nxt.startswith('!['):
                    break
                if any(k in nxt for k in EXCLUDE_LINE_KEYWORDS):
                    continue
                for u in re.findall(r'https?://[^\s<>"\']+', nxt):
                    u = clean_url(u)
                    if u and not is_bad_url(u):
                        sub_urls.add(u)

    # ③ 兜底：①②都没拿到时，逐行扫描但跳过推广行
    if not sub_urls:
        for line in lines:
            if any(k in line for k in EXCLUDE_LINE_KEYWORDS):
                continue
            for u in re.findall(r'https?://[^\s<>"\']+', line):
                u = clean_url(u)
                if u and not is_bad_url(u):
                    sub_urls.add(u)

    return sub_urls

# ================= 节点协议解析 =================
def decode_base64(s):
    try:
        s += '=' * (-len(s) % 4)
        return base64.b64decode(s).decode('utf-8')
    except Exception:
        return s

def parse_vmess(link):
    try:
        j = json.loads(decode_base64(link[8:]))
        return {
            'name': j.get('ps', j.get('add', 'VMess Node')), 'type': 'vmess',
            'server': j.get('add'), 'port': int(j.get('port')), 'uuid': j.get('id'),
            'alterId': int(j.get('aid', 0)), 'cipher': 'auto', 'udp': True,
            'tls': j.get('tls') == 'tls', 'network': j.get('net', 'tcp'),
            'ws-opts': ({'path': j.get('path', '/'), 'headers': {'Host': j.get('host', '')}}
                        if j.get('net') == 'ws' else None),
            'skip-cert-verify': True
        }
    except Exception:
        return None

def parse_vless(link):
    try:
        link = link[8:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'VLESS Node'
        main = link.split('#')[0]
        uuid = main.split('@')[0]
        addr_port = main.split('@')[1].split('?')[0]
        server, port = addr_port.split(':')[0], int(addr_port.split(':')[1])
        q = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        security = q.get('security', ['none'])[0]
        network = q.get('type', ['tcp'])[0]
        path = urllib.parse.unquote(q.get('path', ['/'])[0])
        host = urllib.parse.unquote(q.get('host', [''])[0])
        sni = urllib.parse.unquote(q.get('sni', [''])[0])
        flow = urllib.parse.unquote(q.get('flow', [''])[0])
        node = {'name': name, 'type': 'vless', 'server': server, 'port': port,
                'uuid': uuid, 'udp': True, 'network': network,
                'tls': security in ('tls', 'reality'), 'skip-cert-verify': True}
        if flow: node['flow'] = flow
        if security == 'reality':
            node['reality-opts'] = {'public-key': q.get('pbk', [''])[0], 'short-id': q.get('sid', [''])[0]}
            node['servername'] = sni
        if network == 'ws': node['ws-opts'] = {'path': path, 'headers': {'Host': host}}
        elif network == 'grpc': node['grpc-opts'] = {'grpc-service-name': q.get('serviceName', [''])[0]}
        return node
    except Exception:
        return None

def parse_trojan(link):
    try:
        link = link[9:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'Trojan Node'
        main = link.split('#')[0]
        password = main.split('@')[0]
        addr_port = main.split('@')[1].split('?')[0]
        server, port = addr_port.split(':')[0], int(addr_port.split(':')[1])
        q = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        sni = urllib.parse.unquote(q.get('sni', [''])[0])
        network = q.get('type', ['tcp'])[0]
        node = {'name': name, 'type': 'trojan', 'server': server, 'port': port,
                'password': password, 'udp': True, 'skip-cert-verify': True, 'network': network}
        if sni: node['sni'] = sni
        if network == 'ws':
            node['ws-opts'] = {'path': urllib.parse.unquote(q.get('path', ['/'])[0]),
                               'headers': {'Host': urllib.parse.unquote(q.get('host', [''])[0])}}
        elif network == 'grpc': node['grpc-opts'] = {'grpc-service-name': q.get('serviceName', [''])[0]}
        return node
    except Exception:
        return None

def parse_ss(link):
    try:
        link = link[5:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'SS Node'
        main = link.split('#')[0].split('?')[0]
        if '@' in main:
            b64, addr_port = main.split('@')
            decoded = decode_base64(b64)
            method, password = decoded.split(':', 1) if ':' in decoded else (decoded, '')
        else:
            decoded = decode_base64(main)
            method, password = decoded.split('@')[0].split(':', 1)
            addr_port = decoded.split('@')[1]
        server, port = addr_port.split(':')[0], int(addr_port.split(':')[1])
        return {'name': name, 'type': 'ss', 'server': server, 'port': port,
                'cipher': method, 'password': password, 'udp': True}
    except Exception:
        return None

def parse_node(link):
    if link.startswith('vmess://'):  return parse_vmess(link)
    if link.startswith('vless://'):  return parse_vless(link)
    if link.startswith('trojan://'): return parse_trojan(link)
    if link.startswith('ss://'):     return parse_ss(link)
    return None

def generate_clash_config(proxies):
    names = [p['name'] for p in proxies]
    return {
        'port': 7890, 'socks-port': 7891, 'allow-lan': False, 'mode': 'Rule',
        'log-level': 'info', 'external-controller': '127.0.0.1:9090',
        'dns': {'enabled': True, 'ipv6': False, 'enhanced-mode': 'fake-ip',
                'fake-ip-range': '198.18.0.1/16',
                'nameserver': ['https://doh.pub/dns-query', 'https://dns.alidns.com/dns-query'],
                'fallback': ['https://doh.dns.sb/dns-query', 'https://dns.cloudflare.com/dns-query']},
        'proxies': proxies,
        'proxy-groups': [
            {'name': '🚀 节点选择', 'type': 'select', 'proxies': names + ['DIRECT']},
            {'name': '🎯 全球直连', 'type': 'select', 'proxies': ['DIRECT', '🚀 节点选择']},
        ],
        'rules': ['GEOIP,CN,🎯 全球直连', 'MATCH,🚀 节点选择'],
    }

# ================= 主流程 =================
def main():
    print("开始爬取任务...")
    sub_urls, direct_nodes = set(), []

    # 1) 读 README，精准提取订阅链接
    for url in README_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            found = extract_sub_urls(r.text)
            print(f"[README] {url}\n       -> 提取到 {len(found)} 个订阅链接: {found}")
            sub_urls |= found
            direct_nodes.extend(m.rstrip('.,)!]') for m in
                                re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', r.text))
        except Exception as e:
            print(f"读取 README 出错 {url}: {e}")

    v2ray_nodes = list(set(direct_nodes))
    clash_proxies = []

    # 2) 请求每个订阅链接，解析节点
    for url in sub_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            content = r.text.strip()

            # 直接返回 Clash YAML 的情况
            if 'proxies:' in content or 'port:' in content:
                try:
                    data = yaml.safe_load(content)
                    if data and data.get('proxies'):
                        print(f"[SUB] {url} -> Clash YAML, {len(data['proxies'])} 个节点")
                        clash_proxies.extend(data['proxies'])
                        continue
                except Exception:
                    pass

            # Base64 / 明文节点
            decoded = decode_base64(content)
            matches = re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', decoded)
            matches += re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', content)
            print(f"[SUB] {url} -> 提取到 {len(matches)} 条节点链接")
            for m in matches:
                m = m.rstrip('.,)!]')
                if m not in v2ray_nodes:
                    v2ray_nodes.append(m)
        except Exception as e:
            print(f"抓取订阅出错 {url}: {e}")

    # 3) V2Ray 节点 -> Clash 代理，并按名称去重
    for node in v2ray_nodes:
        p = parse_node(node)
        if p:
            clash_proxies.append(p)
    clash_proxies = list({p['name']: p for p in clash_proxies if p.get('name')}.values())

    if not clash_proxies and not v2ray_nodes:
        print("未发现任何节点，本次不更新文件。")
        return

    # 4) 输出订阅文件
    if v2ray_nodes:
        with open('v2ray.txt', 'w') as f:
            f.write(base64.b64encode('\n'.join(v2ray_nodes).encode()).decode())
    if clash_proxies:
        with open('clash.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(generate_clash_config(clash_proxies), f, allow_unicode=True, sort_keys=False)

    print(f"完成！v2ray 节点 {len(v2ray_nodes)} 条，clash 节点 {len(clash_proxies)} 个。")

if __name__ == '__main__':
    main()
