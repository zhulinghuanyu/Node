# Subscription Crawler

定时读取多个公开 README，提取其中的订阅 URL，使用 subconverter 生成 Clash / V2Ray 输出，并将结果提交回 GitHub。

> 请只处理你有权抓取、转换和再发布的订阅内容。不要把本项目当作绕过服务商限制或再分发未授权内容的工具。

## 功能

- 从多个 README 自动提取 HTTP/HTTPS 订阅链接
- 自动去重
- GitHub Actions 每 30 分钟自动更新
- 使用 `tindy2013/subconverter` **逐个源转换**，再在本地合并：
  - `output/clash.yaml`
  - `output/v2ray-subconverter.txt`
- 尝试提取标准节点 URI，并生成：
  - `output/nodes.txt`
  - `output/v2ray.txt`（Base64）
- 生成 `output/status.json` 记录运行结果
- 某个 README 或单个订阅转换失败不会导致全部任务失败；脚本会记录失败源并继续处理其他源，但最终没有任何有效转换结果时任务失败

## 目录

```text
.
├── .github/workflows/update.yml
├── config/sources.txt
├── scripts/crawl.py
├── output/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 一键使用

1. 在 GitHub 新建一个空仓库。
2. 将本项目全部文件上传到仓库根目录。
3. 打开 `Actions`，确认工作流可用。
4. 手动执行一次 `Update subscriptions`。
5. 成功后订阅地址为：

```text
https://raw.githubusercontent.com/你的用户名/你的仓库/main/output/clash.yaml
https://raw.githubusercontent.com/你的用户名/你的仓库/main/output/v2ray.txt
https://raw.githubusercontent.com/你的用户名/你的仓库/main/output/v2ray-subconverter.txt
```

如果仓库是 private，Raw 地址不能作为公开订阅地址使用。

## 修改数据源

编辑：

```text
config/sources.txt
```

一行一个 README / 页面 URL，例如：

```text
https://example.com/readme.md
https://example.com/subscriptions
```

脚本会从页面中寻找 `http://` / `https://` 链接，并排除 GitHub 自身页面、图片等明显非订阅链接。

## 定时频率

默认：

```yaml
- cron: "*/30 * * * *"
```

也就是每 30 分钟。

例如每天北京时间 04:00：

```yaml
- cron: "0 20 * * *"
```

GitHub Actions 的 cron 使用 UTC。

## 本地运行

需要 Python 3.12+ 和 Docker。

启动转换器：

```bash
docker compose up -d
```

安装依赖：

```bash
python -m pip install -r requirements.txt
```

执行：

```bash
python scripts/crawl.py
```

输出：

```text
output/
├── clash.yaml
├── nodes.txt
├── sources.txt
├── status.json
├── v2ray-subconverter.txt
└── v2ray.txt
```

## 重要说明

### 1. Clash 输出

`clash.yaml` 是通过 subconverter 的 `target=clash` 生成，而不是 Python 自己拼接 YAML。

### 2. V2Ray 输出

`v2ray-subconverter.txt` 是通过 subconverter 的 `target=v2ray` 生成。

`v2ray.txt` 是另一份简单的 Base64 节点 URI 订阅，仅在源内容能直接暴露 `vmess://`、`vless://`、`trojan://`、`ss://`、`ssr://`、`hysteria://`、`hysteria2://`、`tuic://` 等 URI 时生成。

### 3. 节点测速

本项目默认**不在 GitHub Actions 上做节点测速**。测速会显著增加运行时间、失败率以及对第三方服务器的连接次数。

如果确实需要测速，建议后续增加可选的自有测试环境，而不是默认对所有公开节点进行并发探测。

### 4. 数据源授权

README 中出现一个 URL，并不代表你拥有该订阅内容的再发布权。使用前请确认来源的授权和服务条款。

## 上游项目

本项目使用 `tindy2013/subconverter` 做格式转换：

https://github.com/tindy2013/subconverter

Docker 镜像：

https://hub.docker.com/r/tindy2013/subconverter


## 为什么是“逐个转换”

不要把几十个订阅 URL 一次性拼进一个 `url=` 参数。某一个源返回异常内容时，可能导致 subconverter 整个请求返回 `400 Bad Request`，同时也会让问题源很难定位。

当前版本改为：

```text
订阅 A → subconverter → Clash
订阅 B → subconverter → Clash
订阅 C → subconverter → 失败（记录）
订阅 D → subconverter → Clash
                      ↓
                 本地合并
```

这样即使某个源失效，其余源仍然可以正常生成。

如果 Actions 日志出现：

```text
[WARN] clash ... FAILED
```

后面会继续处理其他源；只有全部源都失败才会退出。
