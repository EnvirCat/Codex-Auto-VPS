# Codex-Auto-VPS

面向中文用户的 Codex 自动化 VPS 节点交付 Skill。

你只需要准备：

- 一台可 SSH 登录的 VPS
- 一个干净的后端出口 IP / SOCKS5 住宅代理，非必须

剩下的部署、优化、安全加固、订阅生成、测试和小白交付文档，都交给 Codex-Auto-VPS 来完成。

## 这个项目能做什么

Codex-Auto-VPS 是一个 Codex Skill，用来把一台独立 VPS 从“刚买回来”处理到“可以交付给普通用户使用”：

- SSH 接入与系统检查
- BBR/fq 网络优化
- 3x-ui 面板安装与隔离部署
- VLESS Reality / Hysteria2 节点预设
- 可选住宅 SOCKS5 后端出口
- 一键订阅链接生成
- Hiddify / Shadowrocket 导入友好命名
- 节点速度、出口 IP、AI 网站与常用网站连通性检查
- 防火墙、SSH、fail2ban、安全端口收敛
- 面向小白用户的交付说明文档

## 适合谁

- 自己有 VPS，但不想手动敲一堆命令的人
- 想快速部署个人备用节点的人
- 需要把 VPS 整理成可交付、可识别、少暴露服务状态的人
- 想把“直连高速”和“干净后端 IP”分开管理的人

## 你需要准备什么

最低配置：

```text
VPS IP
SSH 端口
SSH 用户名
SSH 密码或私钥
```

可选配置：

```text
干净后端 IP / SOCKS5 代理
后端代理用户名
后端代理密码
```

如果没有干净后端 IP，也可以只部署高速直连节点。

## 目录结构

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   └── deployment-runbook.md
└── scripts/
    └── subscription_server.py
```

## 安装方式

把仓库克隆到 Codex skills 目录：

```powershell
git clone https://github.com/EnvirCat/Codex-Auto-VPS.git "$env:USERPROFILE\.codex\skills\codex-auto-vps"
```

然后在 Codex 里调用：

```text
$codex-auto-vps
```

## 典型工作流

你提供 VPS 登录信息后，Skill 会引导或直接完成：

1. 连接 VPS，确认系统、内存、磁盘、监听端口
2. 开启 BBR/fq 等基础网络优化
3. 安装或调整 3x-ui / Xray / Hysteria2
4. 生成速度优先节点和可选后端出口节点
5. 创建 Hiddify / Shadowrocket 可导入的一键订阅
6. 验证出口 IP、网站可达性、端口暴露和服务状态
7. 输出一份普通用户能看懂的交付说明

## 安全模式

当你要减少暴露面时，Codex-Auto-VPS 会倾向于：

- 只保留必要 SSH、订阅端口、Hy2 UDP 端口
- 关闭不需要的 3x-ui 公网面板
- 关闭不用的 VLESS / Reality / Xray 服务
- 使用 UFW 默认拒绝入站
- 禁用 SSH 密码登录，只保留密钥登录
- 启用 fail2ban
- 旧订阅泄露时轮换端口、认证密码和混淆密码

## 重要安全提醒

这个仓库不包含任何真实 VPS 密码、私钥、订阅链接、住宅代理账号或生产 IP。

你在实际使用时，请不要把下面这些内容提交到 GitHub：

- SSH 私钥
- VPS 密码
- 面板账号密码
- 住宅代理账号密码
- 真实订阅链接
- 交付文档中的真实 IP、UUID、token、端口和密码

## 合规说明

本项目是 VPS 自动化运维与交付工作流。请只在你拥有或被授权管理的服务器上使用，并遵守所在地区法律、服务商条款和网络使用政策。

## License

MIT
