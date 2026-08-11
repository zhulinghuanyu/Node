import requests
import re
import base64
import json
import urllib.parse
import yaml
import os
from datetime import datetime

# 目标 README 链接
README_URLS = [
    "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md",
    "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md",
    "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def decode_base64(s):
    try:
        s += '=' * (-len(s) % 4)
        return base64.b64decode(s).decode('utf-8')
    except:
        return s

def parse_vmess(link):
    try:
        b64 = link[8:]
        j = json.loads(decode_base64(b64))
        return {
            'name': j.get('ps', j.get('add', 'VMess Node')),
            'type': 'vmess',
            'server': j.get('add'),
            'port': int(j.get('port')),
            'uuid': j.get('id'),
            'alterId': int(j.get('aid', 0)),
            'cipher': 'auto',
            'udp': True,
            'tls': j.get('tls') == 'tls',
            'network': j.get('net', 'tcp'),
            'ws-opts': {'path': j.get('path', '/'), 'headers': {'Host': j.get('host', '')}} if j.get('net') == 'ws' else None,
            'skip-cert-verify': True
        }
    except: return None

def parse_vless(link):
    try:
        link = link[8:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'VLESS Node'
        main = link.split('#')[0]
        uuid = main.split('@')[0]
        addr_port = main.split('@')[1].split('?')[0]
        server = addr_port.split(':')[0]
        port = int(addr_port.split(':')[1])
        
        query = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        security = query.get('security', ['none'])[0]
        network = query.get('type', ['tcp'])[0]
        path = urllib.parse.unquote(query.get('path', ['/'])[0])
        host = urllib.parse.unquote(query.get('host', [''])[0])
        sni = urllib.parse.unquote(query.get('sni', [''])[0])
        flow = urllib.parse.unquote(query.get('flow', [''])[0])
        
        node = {
            'name': name,
            'type': 'vless',
            'server': server,
            'port': port,
            'uuid': uuid,
            'udp': True,
            'network': network,
            'tls': security in ['tls', 'reality'],
            'skip-cert-verify': True
        }
        if flow: node['flow'] = flow
        if security == 'reality':
            node['reality-opts'] = {'public-key': query.get('pbk', [''])[0], 'short-id': query.get('sid', [''])[0]}
            node['servername'] = sni
        if network == 'ws': node['ws-opts'] = {'path': path, 'headers': {'Host': host}}
        elif network == 'grpc': node['grpc-opts'] = {'grpc-service-name': query.get('serviceName', [''])[0]}
        return node
    except: return None

def parse_trojan(link):
    try:
        link = link[9:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'Trojan Node'
        main = link.split('#')[0]
        password = main.split('@')[0]
        addr_port = main.split('@')[1].split('?')[0]
        server = addr_port.split(':')[0]
        port = int(addr_port.split(':')[1])
        
        query = urllib.parse.parse_qs(main.split('?')[1] if '?' in main else '')
        sni = urllib.parse.unquote(query.get('sni', [''])[0])
        network = query.get('type', ['tcp'])[0]
        
        node = {
            'name': name, 'type': 'trojan', 'server': server, 'port': port,
            'password': password, 'udp': True, 'skip-cert-verify': True, 'network': network
        }
        if sni: node['sni'] = sni
        if network == 'ws':
            path = urllib.parse.unquote(query.get('path', ['/'])[0])
            host = urllib.parse.unquote(query.get('host', [''])[0])
            node['ws-opts'] = {'path': path, 'headers': {'Host': host}}
        elif network == 'grpc': node['grpc-opts'] = {'grpc-service-name': query.get('serviceName', [''])[0]}
        return node
    except: return None

def parse_ss(link):
    try:
        link = link[5:]
        name = urllib.parse.unquote(link.split('#')[1]) if '#' in link else 'SS Node'
        main = link.split('#')[0]
        if '?' in main: main = main.split('?', 1)[0]
            
        if '@' in main:
            b64, addr_port = main.split('@')
            decoded = decode_base64(b64)
            if ':' in decoded: method, password = decoded.split(':', 1)
            else: method, password = decoded, ''
            server = addr_port.split(':')[0]
            port = int(addr_port.split(':')[1])
        else:
            decoded = decode_base64(main)
            method, password = decoded.split('@')[0].split(':', 1)
            addr_port = decoded.split('@')[1]
            server = addr_port.split(':')[0]
            port = int(addr_port.split(':')[1])
            
        return {'name': name, 'type': 'ss', 'server': server, 'port': port, 'cipher': method, 'password': password, 'udp': True}
    except: return None

def parse_node(link):
    if link.startswith('vmess://'): return parse_vmess(link)
    elif link.startswith('vless://'): return parse_vless(link)
    elif link.startswith('trojan://'): return parse_trojan(link)
    elif link.startswith('ss://'): return parse_ss(link)
    return None

def generate_clash_config(proxies):
    proxy_names = [p['name'] for p in proxies]
    return {
        'port': 7890, 'socks-port': 7891, 'allow-lan': False, 'mode': 'Rule',
        'log-level': 'info', 'external-controller': '127.0.0.1:9090',
        'dns': {
            'enabled': True, 'listen': '0.0.0.0:53', 'ipv6': False,
            'default-nameserver': ['223.5.5.5', '114.114.114.114'],
            'enhanced-mode': 'fake-ip', 'fake-ip-range': '198.18.0.1/16',
            'use-hosts': True,
            'nameserver': ['https://doh.pub/dns-query', 'https://dns.alidns.com/dns-query'],
            'fallback': ['https://doh.dns.sb/dns-query', 'https://dns.cloudflare.com/dns-query'],
            'fallback-filter': {'geoip': True, 'ipcidr': ['240.0.0.0/4', '0.0.0.0/32']}
        },
        'proxies': proxies,
        'proxy-groups': [
            {'name': '🚀 节点选择', 'type': 'select', 'proxies': proxy_names + ['DIRECT']},
            {'name': '🎯 全球直连', 'type': 'select', 'proxies': ['DIRECT', '🚀 节点选择']}
        ],
        'rules': ['GEOIP,CN,🎯 全球直连', 'MATCH,🚀 节点选择']
    }

def main():
    print("开始爬取任务...")
    sub_urls, direct_nodes = set(), []
    
    # 1. 提取 README 中的链接和直接暴露的节点
    for url in README_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                urls = re.findall(r'https?://[^\s<>"\']+', r.text)
                for u in urls:
                    u = u.strip().rstrip('.,)!]')
                    if not any(x in u for x in ['github.com', 'githubusercontent.com', '.jpg', '.png', '.jpeg', '.gif']):
                        sub_urls.add(u)
                direct_nodes.extend(re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', r.text))
        except Exception as e: print(f"读取 README 出错 {url}: {e}")

    v2ray_nodes = [n.rstrip('.,)!]') for n in list(set(direct_nodes))]
    clash_proxies = []

    # 2. 遍历获取到的订阅链接
    for url in list(sub_urls):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                content = r.text.strip()
                # 判断是否直接返回了 Clash YAML
                if 'proxies:' in content or 'port:' in content:
                    try:
                        data = yaml.safe_load(content)
                        if data and 'proxies' in data:
                            clash_proxies.extend(data['proxies'])
                            continue
                    except: pass
                
                # Base64 解码并提取节点
                decoded = decode_base64(content)
                matches = re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', decoded)
                matches.extend(re.findall(r'(vmess|vless|trojan|ss|ssr)://[^\s<>"\'，]+', content))
                for match in matches:
                    clean_match = match.rstrip('.,)!]')
                    if clean_match not in v2ray_nodes: v2ray_nodes.append(clean_match)
        except Exception as e: print(f"抓取订阅出错 {url}: {e}")

    # 3. 解析节点生成 Clash 配置
    v2ray_nodes = list(set(v2ray_nodes))
    for node in v2ray_nodes:
        parsed = parse_node(node)
        if parsed: clash_proxies.append(parsed)

    # 去重
    unique_proxies = {p.get('name', ''): p for p in clash_proxies if p.get('name')}
    clash_proxies = list(unique_proxies.values())

    if not clash_proxies: print("未发现可用节点，终止生成。") ; return

    # 4. 保存输出文件
    with open('v2ray.txt', 'w') as f:
        f.write(base64.b64encode('\n'.join(v2ray_nodes).encode('utf-8')).decode('utf-8'))
        
    with open('clash.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(generate_clash_config(clash_proxies), f, allow_unicode=True, sort_keys=False)
        
    print(f"成功！提取并解析了 {len(clash_proxies)} 个节点。")

if __name__ == '__main__':
    main()
