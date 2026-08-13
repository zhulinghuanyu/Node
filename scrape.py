import requests
import re
import base64
import json
import urllib.parse
import yaml
import os
import time
from datetime import datetime, timezone, timedelta

# ======================= 自定义 YAML Dumper 以实现 proxies 单行输出 =======================
class FlowDict(dict):
    pass
class FlowDumper(yaml.SafeDumper):
    pass
def _represent_flow_dict(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data.items(), flow_style=True)
FlowDumper.add_representer(FlowDict, _represent_flow_dict)
def convert_to_flow(obj):
    if isinstance(obj, dict):
        return FlowDict({k: convert_to_flow(v) for k, v in obj.items()})
    elif isinstance(obj, list):
        return [convert_to_flow(i) for i in obj]
    return obj

# ======================= 配置 =======================
SOURCES_FILE = 'sources.txt' 
DEFAULT_SOURCES = [  # sources.txt 不存在时的兜底列表
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md",
]
UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'clash-verge/v1.7.3', 'v2rayN/6.45', 'Shadowrocket/2.2.44', 'Quantumult/601',
]
def load_sources():
    urls = []
    try:
        with open(SOURCES_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                if line.startswith('http'):
                    urls.append(line)
    except FileNotFoundError:
        pass
    return urls or DEFAULT_SOURCES

# ======================= 抗封锁抓取 =======================
def is_cf_block(text):
    t = (text or '')[:3000].lower()
    return any(k in t for k in [
        'just a moment', 'cf-browser-verification', 'sorry, you have been blocked',
        'attention required!', 'cloudflare ray id', 'enable cookies',
        'security service to protect', 'error 521', 'error 522', 'error 523',
    ])
def _try_get(url, ua, proxies=None, timeout=15):
    try:
        r = requests.get(url, headers={'User-Agent': ua, 'Accept': '*/*'},
                         timeout=timeout, proxies=proxies)
        if r.status_code == 200 and not is_cf_block(r.text):
            return r.text
    except Exception:
        pass
    return None
def fetch(url, retries=2):
    proxy = os.environ.get('PROXY_URL', '').strip()
    if proxy:
        proxies = {'http': proxy, 'https': proxy}
        for _ in range(retries):
            text = _try_get(url, UA_LIST[0], proxies)
            if text is not None:
                return text
            time.sleep(1)
    for ua in UA_LIST:
        text = _try_get(url, ua)
        if text is not None:
            return text
        time.sleep(0.5)
    enc = urllib.parse.quote(url, safe='')
    relays = [
        f'https://api.allorigins.win/raw?url={enc}',
        f'https://api.codetabs.com/v1/proxy?quest={enc}',
        f'https://corsproxy.io/?url={enc}',
    ]
    for relay in relays:
        for _ in range(retries):
            text = _try_get(relay, UA_LIST[0], timeout=20)
            if text is not None:
                return text
            time.sleep(1)
    return None

# ======================= 订阅链接精准提取 =======================
EXCLUDE_DOMAINS = ['github.com', 'githubusercontent.com', 'jsdelivr.net',
                   't.me', 'telegram.me', 'youtube.com', 'twitter.com', 'x.com']
EXCLUDE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.ico', '.svg')
EXCLUDE_LINE_KEYWORDS = ['注册', '试用', '邀请', '购买', '续费', '官网',
                         '机场', '下载', '教程', '客服', 'banner', '广告']
SUB_KEYWORDS = ['订阅', 'subscription']
def clean_url(u):
    return u.strip().rstrip('.,)!]\'"')
def is_bad_url(u):
    low = u.lower()
    return any(d in low for d in EXCLUDE_DOMAINS) or low.endswith(EXCLUDE_EXT)
def extract_sub_urls(text):
    sub_urls = set()
    for block in re.findall(r'```[\s\S]*?```', text):
        for u in re.findall(r'https?://[^\s<>"\']+', block):
            u = clean_url(u)
            if u and not is_bad_url(u):
                sub_urls.add(u)
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
    if not sub_urls:
        for line in lines:
            if any(k in line for k in EXCLUDE_LINE_KEYWORDS):
                continue
            for u in re.findall(r'https?://[^\s<>"\']+', line):
                u = clean_url(u)
                if u and not is_bad_url(u):
                    sub_urls.add(u)
    return sub_urls

# ======================= 节点协议解析（URI -> Clash） =======================
def decode_base64(s):
    try:
        s += '=' * (-len(s) % 4)
        return base64.b64decode(s).decode('utf-8')
    except Exception:
        return s
def parse_vmess(link):
    try:
        j = json.loads(decode_base64(link[8:]))
        return {'name': j.get('ps', j.get('add', 'VMess')), 'type': 'vmess',
                'server': j.get('add'), 'port': int(j.get('port')), 'uuid': j.get('id'),
                'alterId': int(j.get('aid', 0)), 'cipher': 'auto', 'udp': True,
                'tls': j.get('tls') == 'tls', 'network': j.get('net', 'tcp'),
                'ws-opts': ({'path': j.get('path', '/'), 'headers': {'Host': j.get('host', '')}}
                            if j.get('net') == 'ws' else None), 'skip-cert-verify': True}
    except Exception:
        return None
def parse_vless(link):
    try:
        link = link[8:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'VLESS'
        main = link.split('#')[0]
        uuid = main.split('@')[0]
        ap = main.split('@')[1].split('?')[0]
        server, port = ap.split(':')[0], int(ap.split(':')[1])
        q = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        sec, net = q.get('security', ['none'])[0], q.get('type', ['tcp'])[0]
        path = urllib.parse.unquote(q.get('path', ['/'])[0])
        host = urllib.parse.unquote(q.get('host', [''])[0])
        sni = urllib.parse.unquote(q.get('sni', [''])[0])
        node = {'name': name, 'type': 'vless', 'server': server, 'port': port, 'uuid': uuid,
                'udp': True, 'network': net, 'tls': sec in ('tls', 'reality'), 'skip-cert-verify': True}
        flow = urllib.parse.unquote(q.get('flow', [''])[0])
        if flow:
            node['flow'] = flow
        if sec == 'reality':
            node['reality-opts'] = {'public-key': q.get('pbk', [''])[0], 'short-id': q.get('sid', [''])[0]}
            node['servername'] = sni
        if net == 'ws':
            node['ws-opts'] = {'path': path, 'headers': {'Host': host}}
        elif net == 'grpc':
            node['grpc-opts'] = {'grpc-service-name': q.get('serviceName', [''])[0]}
        return node
    except Exception:
        return None
def parse_trojan(link):
    try:
        link = link[9:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'Trojan'
        main = link.split('#')[0]
        ap = main.split('@')[1].split('?')[0]
        server, port = ap.split(':')[0], int(ap.split(':')[1])
        q = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        sni, net = urllib.parse.unquote(q.get('sni', [''])[0]), q.get('type', ['tcp'])[0]
        node = {'name': name, 'type': 'trojan', 'server': server, 'port': port,
                'password': main.split('@')[0], 'udp': True, 'skip-cert-verify': True, 'network': net}
        if sni:
            node['sni'] = sni
        if net == 'ws':
            node['ws-opts'] = {'path': urllib.parse.unquote(q.get('path', ['/'])[0]),
                               'headers': {'Host': urllib.parse.unquote(q.get('host', [''])[0])}}
        elif net == 'grpc':
            node['grpc-opts'] = {'grpc-service-name': q.get('serviceName', [''])[0]}
        return node
    except Exception:
        return None
def parse_ss(link):
    try:
        link = link[5:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'SS'
        main = link.split('#')[0].split('?')[0]
        if '@' in main:
            b64, ap = main.split('@')
            d = decode_base64(b64)
            method, password = d.split(':', 1) if ':' in d else (d, '')
        else:
            d = decode_base64(main)
            method, password = d.split('@')[0].split(':', 1)
            ap = d.split('@')[1]
        server, port = ap.split(':')[0], int(ap.split(':')[1])
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

# ======================= 反向转换（Clash -> URI） =======================
def clash_to_uri(p):
    try:
        t, server, port = p.get('type'), p.get('server'), p.get('port')
        name = urllib.parse.quote(p.get('name', ''))
        ws = p.get('ws-opts') or {}
        ws_path, ws_host = ws.get('path', '/'), (ws.get('headers') or {}).get('Host', '')
        if t == 'vmess':
            obj = {'v': '2', 'ps': p.get('name', ''), 'add': server, 'port': str(port),
                   'id': p.get('uuid'), 'aid': str(p.get('alterId', 0)), 'type': 'auto',
                   'net': p.get('network', 'tcp'), 'tls': 'tls' if p.get('tls') else '',
                   'sni': p.get('servername') or ws_host}
            if p.get('network') == 'ws':
                obj['path'], obj['host'] = ws_path, ws_host
            elif p.get('network') == 'grpc':
                obj['path'] = (p.get('grpc-opts') or {}).get('grpc-service-name', '')
            return 'vmess://' + base64.b64encode(json.dumps(obj).encode()).decode()
        if t == 'vless':
            params = {'type': p.get('network', 'tcp'),
                      'security': 'tls' if p.get('tls') else 'none'}
            if p.get('flow'):
                params['flow'] = p.get('flow')
            if p.get('servername') or ws_host:
                params['sni'] = p.get('servername') or ws_host
            if p.get('network') == 'ws':
                params['path'], params['host'] = ws_path, ws_host
            elif p.get('network') == 'grpc':
                params['serviceName'] = (p.get('grpc-opts') or {}).get('grpc-service-name', '')
            if p.get('reality-opts'):
                params.update({'security': 'reality',
                               'pbk': p['reality-opts'].get('public-key', ''),
                               'sid': p['reality-opts'].get('short-id', '')})
            return f"vless://{p.get('uuid')}@{server}:{port}?{urllib.parse.urlencode(params)}#{name}"
        if t == 'trojan':
            params = {}
            if p.get('sni'):
                params['sni'] = p.get('sni')
            if p.get('network') == 'ws':
                params.update({'type': 'ws', 'path': ws_path, 'host': ws_host})
            elif p.get('network') == 'grpc':
                params.update({'type': 'grpc', 'serviceName':
                               (p.get('grpc-opts') or {}).get('grpc-service-name', '')})
            pwd = urllib.parse.quote(p.get('password', ''), safe='')
            q = urllib.parse.urlencode(params)
            return f"trojan://{pwd}@{server}:{port}?{q}#{name}" if q else f"trojan://{pwd}@{server}:{port}#{name}"
        if t == 'ss':
            b64 = base64.b64encode(f"{p.get('cipher')}:{p.get('password')}".encode()).decode()
            return f"ss://{b64}@{server}:{port}#{name}"
    except Exception:
        return None
    return None

# ======================= Clash 配置生成 =======================
def generate_clash_config(proxies):
    names = [p['name'] for p in proxies]
    return {
        'port': 7890, 'socks-port': 7891, 'allow-lan': False, 'mode': 'Rule',
        'log-level': 'info', 'external-controller': '127.0.0.1:9090',
        'dns': {'enabled': True, 'ipv6': False, 'enhanced-mode': 'fake-ip',
                'fake-ip-range': '198.18.0.1/16',
                'nameserver': ['https://doh.pub/dns-query', 'https://doh.dns.sb/dns-query'],
                'fallback': ['https://doh.dns.sb/dns-query', 'https://dns.cloudflare.com/dns-query']},
        'proxies': convert_to_flow(proxies),
        'proxy-groups': [
            {'name': '🚀 节点选择', 'type': 'select', 'proxies': names + ['DIRECT']},
            {'name': '🎯 全球直连', 'type': 'select', 'proxies': ['DIRECT', '🚀 节点选择']},
        ],
        'rules': ['GEOIP,CN,🎯 全球直连', 'MATCH,🚀 节点选择'],
    }

# ======================= README 自动刷新 =======================
def update_readme(v2_count, clash_count):
    try:
        with open('README.md', encoding='utf-8') as f:
            text = f.read()
        now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        block = (f"- 🕒 最后更新：{now}（北京时间）\n"
                 f"- 📦 节点数量：Clash {clash_count} 个 / V2Ray {v2_count} 条")
        new_text, n = re.subn(
            r'<!-- AUTO-INFO START -->.*?<!-- AUTO-INFO END -->',
            lambda m: f'<!-- AUTO-INFO START -->\n{block}\n<!-- AUTO-INFO END -->',
            text, flags=re.S)
        if n == 0: 
            new_text = text + f'\n<!-- AUTO-INFO START -->\n{block}\n<!-- AUTO-INFO END -->\n'
        with open('README.md', 'w', encoding='utf-8') as f:
            f.write(new_text)
        print("README 统计信息已刷新。")
    except Exception as e:
        print(f"更新 README 失败：{e}")

# ======================= 主流程 =======================
def main():
    print("开始爬取任务...")
    sub_urls, direct_nodes = set(), []
    for url in load_sources():
        try:
            r = requests.get(url, headers={'User-Agent': UA_LIST[0]}, timeout=15)
            r.raise_for_status()
            found = extract_sub_urls(r.text)
            print(f"[README] {url}\n       -> 提取到 {len(found)} 个订阅链接: {found}")
            sub_urls |= found
            direct_nodes.extend(m.rstrip('.,)!]') for m in
                                re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', r.text))
        except Exception as e:
            print(f"读取来源出错 {url}: {e}")
    v2ray_nodes = list(set(direct_nodes))
    clash_proxies = []
    for url in sub_urls:
        content = fetch(url)
        if content is None:
            print(f"[SUB] {url} -> 所有通道均失败(源站保护或宕机)")
            continue
        content = content.strip()
        if 'proxies:' in content or 'port:' in content:
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict) and data.get('proxies'):
                    print(f"[SUB] {url} -> Clash YAML, {len(data['proxies'])} 个节点")
                    clash_proxies.extend(data['proxies'])
                    continue
            except Exception:
                pass
        decoded = decode_base64(content)
        matches = re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', decoded)
        matches += re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', content)
        print(f"[SUB] {url} -> 提取到 {len(matches)} 条节点链接")
        for m in matches:
            m = m.rstrip('.,)!]')
            if m not in v2ray_nodes:
                v2ray_nodes.append(m)
    parsed_from_uri = set()
    for node in v2ray_nodes:
        p = parse_node(node)
        if p:
            clash_proxies.append(p)
            parsed_from_uri.add(p['name'])
    clash_proxies = list({p['name']: p for p in clash_proxies if p.get('name')}.values())
    for p in clash_proxies:
        if p['name'] not in parsed_from_uri:
            uri = clash_to_uri(p)
            if uri and uri not in v2ray_nodes:
                v2ray_nodes.append(uri)
    if not clash_proxies and not v2ray_nodes:
        print("本次未发现任何节点，不更新文件，保留上一版订阅。")
        return
    if v2ray_nodes:
        with open('v2ray.txt', 'w') as f:
            f.write(base64.b64encode('\n'.join(v2ray_nodes).encode()).decode())         
    if clash_proxies:
        with open('clash.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(
                generate_clash_config(clash_proxies), 
                f, 
                Dumper=FlowDumper, 
                allow_unicode=True, 
                sort_keys=False, 
                default_flow_style=False, 
                width=4096
            )
    update_readme(len(v2ray_nodes), len(clash_proxies))
    print(f"完成！v2ray 节点 {len(v2ray_nodes)} 条，clash 节点 {len(clash_proxies)} 个。")

if __name__ == '__main__':
    main()
