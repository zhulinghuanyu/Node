import requests
from bs4 import BeautifulSoup
import base64
import yaml
import json
import os
from github3 import login

# 配置信息
TARGET_REPOS = [
    'tolinkshare2/tolinkshare2.github.io',
    'abshare3/abshare3.github.io',
    'mkshare3/mkshare3.github.io',
    'toshare5/toshare5.github.io'
]
GITHUB_TOKEN = '你的GitHub个人访问令牌'  # 具有repo权限
OUTPUT_DIR = 'subscriptions'
CLASH_OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'clash_subscription.yaml')
V2RAY_OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'v2ray_subscription.json')

def get_readme_content(owner, repo):
    """通过GitHub API获取仓库的README.md内容"""
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    url = f'https://api.github.com/repos/{owner}/{repo}/readme'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        # README内容通常是Base64编码的
        content_base64 = response.json()['content']
        content = base64.b64decode(content_base64).decode('utf-8')
        return content
    else:
        print(f"Failed to fetch README for {owner}/{repo}: {response.status_code}")
        return None

def extract_subscription_links(readme_content):
    """从README内容中提取订阅链接"""
    soup = BeautifulSoup(readme_content, 'html.parser')
    # 这里需要根据实际README的HTML结构调整选择器
    # 示例是寻找所有code标签或pre标签中包含https的链接
    links = []
    for code in soup.find_all(['code', 'pre']):
        text = code.get_text()
        if 'https://' in text and '.xyz' in text:  # 这是一个简化的判断条件
            # 清理文本，提取URL
            url = text.strip()
            if url.startswith('https://'):
                links.append(url)
    return links

def convert_to_clash_subscription(raw_links):
    """将原始链接转换为Clash订阅格式（示例）"""
    # 注意：这是一个非常简化的示例。实际的Clash配置文件结构很复杂。
    # 你需要解析原始订阅（可能是Base64编码的SS/V2Ray链接），提取节点信息，
    # 然后构建完整的Clash YAML配置。这里只是生成一个包含所有链接的列表。
    clash_config = {
        'proxies': [],
        'proxy-groups': [
            {
                'name': 'Proxy',
                'type': 'select',
                'proxies': ['AUTO', 'DIRECT'] + [f"proxy_{i}" for i in range(len(raw_links))]
            }
        ],
        'rules': ['DOMAIN-SUFFIX,google.com,Proxy', 'DOMAIN-SUFFIX,github.com,DIRECT', 'GEOIP,CN,DIRECT', 'MATCH,Proxy']
    }
    
    for i, link in enumerate(raw_links):
        # 在实际应用中，这里需要解析link以获取节点信息（名称、类型、地址、端口等）
        # 例如：ss://base64(info) -> 解码后获取服务器地址、端口、密码、加密方法
        # 这部分解析逻辑非常复杂，通常需要专门的库，如 shadowsocks、v2ray-core 等。
        # 这里我们用一个占位符表示一个代理节点
        clash_config['proxies'].append({
            'name': f"proxy_{i}",
            'type': 'ss',  # 假设是Shadowsocks，实际需要判断
            'server': 'example.com',  # 从link中解析
            'port': 8388,  # 从link中解析
            'cipher': 'aes-256-gcm',  # 从link中解析
            'password': 'password'  # 从link中解析
        })
    
    return yaml.dump(clash_config, default_flow_style=False)

def convert_to_v2ray_subscription(raw_links):
    """将原始链接转换为V2Ray订阅格式（示例）"""
    # 同样，这是一个极度简化的示例。V2Ray配置是一个JSON结构。
    # 你需要解析原始链接，构建 outbounds 和 routing 等核心配置。
    v2ray_config = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{'port': 10808, 'protocol': 'socks', 'settings': {'udp': True}}],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': [
                {'type': 'field', 'outboundTag': 'direct', 'domain': ['geosite:cn']},
                {'type': 'field', 'outboundTag': 'proxy', 'network': 'tcp,udp'}
            ]
        }
    }
    
    for link in raw_links:
        # 解析link以获取V2Ray节点信息（vmess://... 等）
        # 这里只是添加一个占位符的 outbound
        v2ray_config['outbounds'].append({
            'protocol': 'vmess',  # 假设是VMess
            'settings': {'vnext': [{'address': 'example.com', 'port': 443, 'users': [{'id': 'uuid', 'alterId': 0}]}]},
            'tag': 'proxy'  # 所有节点共享同一个tag，实际需要更复杂的逻辑
        })
    
    return json.dumps(v2ray_config, indent=2)

def update_github_repo(owner, repo, file_path, content, message):
    """通过GitHub API更新仓库中的文件"""
    gh = login(token=GITHUB_TOKEN)
    repository = gh.repository(owner, repo)
    branch = 'main'  # 或 'master'
    
    # 获取文件的当前SHA（如果存在）
    contents = repository.contents(file_path, ref=branch)
    sha = contents.sha if contents else None
    
    # 提交新内容
    repository.create_file(
        path=file_path,
        message=message,
        content=content,
        branch=branch,
        sha=sha
    )
    print(f"Successfully updated {file_path} in {owner}/{repo}")

def main():
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_raw_links = []
    
    # 1. 爬取所有目标仓库的README并提取链接
    for repo_full_name in TARGET_REPOS:
        owner, repo = repo_full_name.split('/')
        readme = get_readme_content(owner, repo)
        if readme:
            links = extract_subscription_links(readme)
            all_raw_links.extend(links)
            print(f"Found {len(links)} links in {owner}/{repo}")
    
    # 去重
    all_raw_links = list(set(all_raw_links))
    print(f"Total unique raw links: {len(all_raw_links)}")
    
    if not all_raw_links:
        print("No links found, exiting.")
        return
    
    # 2. 转换为Clash和V2Ray订阅格式
    clash_yaml = convert_to_clash_subscription(all_raw_links)
    v2ray_json = convert_to_v2ray_subscription(all_raw_links)
    
    # 3. 将转换后的内容写入本地文件（用于调试）
    with open(CLASH_OUTPUT_FILE, 'w') as f:
        f.write(clash_yaml)
    with open(V2RAY_OUTPUT_FILE, 'w') as f:
        f.write(v2ray_json)
    
    # 4. 更新GitHub仓库中的订阅文件
    # 将你的GitHub仓库名和所有者名替换成你自己的
    update_github_repo('你的GitHub用户名', '你的仓库名', CLASH_OUTPUT_FILE, clash_yaml, 'Update Clash subscription')
    update_github_repo('你的GitHub用户名', '你的仓库名', V2RAY_OUTPUT_FILE, v2ray_json, 'Update V2Ray subscription')

if __name__ == '__main__':
    main()
