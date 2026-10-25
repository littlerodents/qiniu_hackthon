# 决策记录（Decision Log）

> 本文档记录产线关键转折的证据与理由，供评审复核「AI 工程效率」与架构演进叙事。

## D1 · 2026-10-24：放弃灯虹平台 UI，转 MiniMax API 直连

**证据**：本机系统代理路径访问 `aicanvas.qnlinking.com` 挂死（12s 超时）；仅 DoH
解析真实 IP + 专用 Chrome 实例可打开站点；owner 侧实测网关 key 无法登录灯虹。
**决策**：资产层（剧本/角色/场景/分镜 JSON）零改动，切换生成执行层为 MiniMax
开放平台直连（`tools/minimax_pipeline.py`）。详见 `sop_xcanvas.md`。

## D2 · 2026-10-25：内部 AI 网关确认为 LLM-only，生成必须走外部 MiniMax key

用 `tools/probe_gateway.py`（DoH 直连 + 域名白名单 + 私网 IP 阻断）对本机可得的
两个七牛网关 key 探测 `api.qnaigc.com`，结果：

| 探测项 | 结果 |
|---|---|
| `GET /v1/models`（主 key） | HTTP 200，**89 个模型，全部为对话/推理 LLM**（doubao/qwen/deepseek/kimi/glm/minimax-m* 系列） |
| `GET /v1/models`（plan key） | HTTP 403：`subscription api key is only allowed for chat completions` |
| `POST /v1/chat/completions`（`minimax/minimax-h3-max`） | HTTP 502 upstream_error（上游已摘除该模型） |
| `POST /v1/images/generations`（`minimax/image-01`） | HTTP 400：`no available channels for model` |
| `POST /v1/video/generations` | HTTP 404 not found |
| `https://xapi.qiniu.io`（比赛 $500 网关） | TLS 握手失败（UNEXPECTED_EOF），与灯虹同款不可达 |

**结论**：本机可用的内部网关凭据只覆盖 LLM 对话，无图像/视频生成通道；
`minimax-h3-max` 已从网关摘除（同日从本地模型列表移除）。**图像/视频生成的
唯一可行路径 = 外部 MiniMax 开放平台 key（`MINIMAX_API_KEY`），待提供。**

**补偿性利用**：网关含免费 LLM（`z-ai/glm-4.5-air-free`、`moonshotai/kimi-k3-free`
等），可作为产线内的剧本校对/提示词优化引擎，零成本增强「AI 工程效率」叙事。

## D3 · 2026-10-25：v0 tag 放置于首个 commit（c4c8c78）

规则「已有 codebase 须先打 v0 tag」针对赛前已有代码。本仓库首 commit 于
10-24（赛中）。为覆盖任何口径的解释，仍将 `v0` 打在首 commit（方案包基线），
此后全部演进经 PR 合入，协同痕迹完整。
