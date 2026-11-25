# 客户端分流交付

新订阅默认使用下列优先级。改造已交付订阅时优先沿用原地址，按用户要求更新分流。

1. 国外 AI、登录、API 和专用资源域名先匹配到用户选中的代理节点。至少验证 ChatGPT、OpenAI API、Claude 和 Gemini。
2. 中国大陆常用服务直连，包括哔哩哔哩、淘宝、京东、微信、QQ、国内支付和国内 AI。核对主站及专用 CDN，按服务收录。客户端能识别时，可加桌面进程或安卓应用包名。国际 AI 的域名规则放在国内应用规则之前。
3. 局域网直连。其余流量走同一个节点选择策略。

优先复用交付网关已有的统一域名清单。公用云、共用 CDN 和整个 `.cn` 后缀的范围过宽。按服务判断国际版和大陆版，例如 `bilibili.tv` 和 `bilibili.com` 分别匹配代理和直连。

| 客户端 | 默认交付方式 |
| --- | --- |
| Clash Verge Rev、Clash Meta、FlClash、ClashX Meta、Stash | 在同一个 YAML 中提供节点、单一选择组和规则，启用规则模式。 |
| sing-box | 使用完整远程 JSON 配置，提供节点、选择组、直连出站和路由末项。 |
| Shadowrocket | 从「配置」导入同时带节点和分流的 Clash 兼容 YAML，启用「全局路由 → 配置」。 |
| Surge、Surfboard、Loon | 使用完整配置，包含兼容节点、策略组和优先匹配的规则。Loon 用远程配置导入，启用分流模式。 |
| Quantumult X | 从「下载配置」添加包含兼容节点、策略和分流的完整配置。协议按实际支持情况筛选，已有自定义配置时先备份。 |
| Hiddify、v2rayNG、NekoBox、Nekoray 的普通节点订阅 | 保持原生节点格式。使用客户端自带分流或额外规则导入。Hiddify 支持规则导入的版本可单独提供路由文件。 |

在新手页优先提供完整配置入口。用户需要兼容格式时再选择节点订阅。对不能直接套用规则的客户端，注明还需哪一步。通用 URL 的已有客户端格式仍须可刷新。

逐个验证完整配置是否包含可用节点、正确的策略名、AI 规则优先级和最终策略。验证下载和标准规则语法。有对应设备时，再实测一条国内直连和一条国外代理请求。已通过解析但还没有设备验证时，在交付说明中明确。

参考 [Mihomo 规则](https://wiki.metacubex.one/en/config/rules/)、[sing-box 路由](https://sing-box.sagernet.org/configuration/route/rule/)、[Loon 远程配置](https://nsloon.app/docs/Scheme/)、[Quantumult X 配置示例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)、[Shadowrocket 配置入口](https://github.com/LOWERTOP/Shadowrocket/wiki#配置文件)和 [Hiddify 路由](https://hiddify.com/app/Routing-in-Hiddify-app/)。
