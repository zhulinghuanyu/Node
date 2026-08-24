# 🛰️ 免费节点订阅 · 自动聚合

> 本项目通过 GitHub Actions 每 **6 小时**自动爬取多个公开分享站的订阅链接，
> 合并、去重后转换为 **Clash** 与 **V2Ray** 通用订阅，全程无人工维护。

<!-- AUTO-INFO START -->
- 🕒 最后更新：2026-08-24 13:23:36（北京时间）
- 📦 节点数量：Clash 11 个 / V2Ray 11 条
<!-- AUTO-INFO END -->

---

## 📥 订阅地址

| 适用客户端 | 订阅链接 |
| --- | --- |
| **Clash / Clash Verge / Mihomo / ClashX** | `https://raw.githubusercontent.com/zhulinghuanyu/dingyue/main/clash.yaml` |
| **V2RayN / V2RayNG / Shadowrocket / Loon** | `https://raw.githubusercontent.com/zhulinghuanyu/dingyue/main/v2ray.txt` |

🚀 **国内加速链接**（raw 直连失败时使用）：

```text
https://ghproxy.net/https://raw.githubusercontent.com/zhulinghuanyu/dingyue/main/clash.yaml
https://ghproxy.net/https://raw.githubusercontent.com/zhulinghuanyu/dingyue/main/v2ray.txt
```

---

## 📱 导入方法

### Clash Verge / ClashX Meta / Mihomo（Win / Mac）
1. 打开软件 →「订阅」/「Profiles」；
2. 粘贴上方 **Clash** 订阅链接 → 导入；
3. 选中该配置，开启「系统代理」即可。

### Clash for Android
1. 右上角「+」→ 类型选 **Url**；
2. 粘贴 Clash 订阅链接 → 保存 → 点击启用。

### V2RayN（Windows）
1. 菜单栏「订阅」→「添加订阅配置」；
2. 粘贴 **V2Ray** 订阅链接 → 确定；
3. 「订阅」→「更新订阅（不通过代理）」。

### V2RayNG（Android）
1. 右上角「⋮」→「手动输入订阅配置」；
2. 粘贴 V2Ray 订阅链接 → 保存 → 更新订阅。

### Shadowrocket / Loon（iOS）
1. 首页「+」→ 类型选 **Subscribe（订阅）**；
2. 粘贴 V2Ray 订阅链接 → 保存，自动拉取节点。

---

## 🔄 更新机制

- ⏰ 每 6 小时由 GitHub Actions 自动执行爬虫；
- 🧩 自动合并多个来源、去重重复节点；
- 🔁 同时生成 Clash（YAML）与 V2Ray（Base64）两种格式；
- 📊 本页面顶部的「最后更新 / 节点数量」由脚本自动刷新。

### 如何新增来源
编辑仓库根目录的 `sources.txt`，**一行一个**页面地址（支持 `#` 注释），提交后下次运行自动生效，无需改代码。

---

## ⚠️ 免责声明

本项目仅做**爬虫与订阅转换的技术演示**，所有节点均来自互联网公开页面，
不对其可用性、安全性负责。请遵守当地法律法规，仅限学习研究使用，
请勿用于任何非法用途。如有侵权，请联系删除。
