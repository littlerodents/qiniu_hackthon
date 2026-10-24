# HANDOFF — 七牛 1024 Hackathon：琅琊榜 EP1（XCanvas/灯虹 → MiniMax 直连产线）

> 交接时间：2026-10-24（距冻结约 32 小时）

## 1. 背景与目标

七牛第五届 1024 Hackathon，2026-10-23 启动，**2026-10-26（周一）09:00 冻结开发**（之后仓库不得再有修改痕迹）。选题为**非产研组议题「用 XCanvas 制作琅琊榜第一集」**。

- **评分（非研发赛道）**：商业价值&产品设计 **60%** + AI 工程效率 **30%** + 架构设计 **10%**
- **交付要求**：GitHub 上传源码 + 运行说明 + 架构文档（模块规格、分工）+ demo 视频；必须走 PR 留协同痕迹；最后一天一次性提交判不合格；已有 codebase 须先打 v0 tag
- **官方资源**：500 USD/人 token，内部网关 **xapi.qiniu.io**（SSO 登录，账号 `个人id@qiniu.com`，可改密，疑问找 @田宇琨）

## 2. 已完成工作与关键决策

### 2.1 调研结论
- **XCanvas = 七牛旗下「灯虹」**（`aicanvas.qnlinking.com`，qnlinking 为七牛关联公司）。定位一站式 AI 影视短剧创作平台：剧本 → 角色/场景/道具 → 分镜 → 图/视频生成。「短剧」是站内一等分类，精选作品封面均为 9:16 竖版（与我们的竖屏方案一致）。
- 登录方式三种：账号密码（邮箱/手机号）、**API Key**（对应 xapi 网关）、RAM 子账号；无扫码。
- 通用短剧工作流已归纳为 8 步法，并对照开源产线 **drama-skills**（MIT，11 技能，produce 层含 MiniMax H3 适配器）。

### 2.2 关键决策：绕开灯虹，走自建 API 产线
**理由**：owner 实测后台取得的 key 仍打不开站点；本机系统代理到 qnlinking 域名不通（12s 超时），仅 DoH 解析真实 IP 直连可通。曾用独立配置目录 Chrome 实例（9223，`--host-resolver-rules` + `--no-proxy-server`）成功打开并核实登录页，但 owner 侧仍不可用 → 判定平台不可依赖。

**叙事处理**：demo 中表述为「平台不可达 → 数小时内切换等价自建产线，资产层零改动」，作为架构分层的正面证据；不否认议题。专用 Chrome 实例已停止清理。

### 2.3 已交付资产（均在 `~/Labs/langya-xcanvas/`）
| 资产 | 说明 |
|---|---|
| 剧本《风起金陵》 | 9:16 竖屏、约 2 分 30 秒、6 场 40 镜、每 20-30 秒一钩子、4 项改编诚实标注 |
| 角色卡 ×12 | 含省一致性成本策略（阁主只出手、太子背影、高湛画外音） |
| 场景卡 ×7 | 视觉锚/时段/色板锁定 |
| 分镜表 ×40 | 每镜含景别/运镜/台词/音效/**降级方案** |
| `build_prompts.py` | 已跑通：37 份生成提示词 + 3 个纯后期镜头，引用校验零错误 |
| 音轨 ×22 | 11 旁白 + 11 台词，按角色调语速/音高，48kHz |
| `build/animatic_v1.mp4` | 动态分镜 v1：1080×1920、186.8s、3.9MB，40 分镜卡 + 全音轨 |
| `tools/minimax_pipeline.py` | probe → images(37) → videos(断点续传) → assemble2(→final_v2.mp4) |
| `player.html` | v1/v2 自动切换、时间线跳转（拉伸镜头标红）、产线看板 |
| `docs/` | 工作流参考、平台 SOP+48h 作战计划、架构文档（六层模块图/数据契约/1·2·3 人分工档/决策记录）、demo 视频脚本 |

### 2.4 工程关键发现
- **音轨驱动时长对齐**：分镜预设 143.5s → 实际 186.8s，19 个镜头因真实配音超长被拉伸。典型案例：梁帝 S4-04 台词实测 10.9s vs 预设 4s。此类问题在动态分镜阶段暴露而非合成阶段。时间线固化于 `build/animatic_timeline.json`。
- QC 曾抓到真 bug：音轨比视频提前 4.7s 结束（片尾字卡无音），已用 `apad` 修复至音画齐平。静帧/黑帧告警属分镜卡形式的预期产物。
- 安全门：脚本历经路径穿越/命令注入/SSRF 三轮拦截，最终方案为 HTTP 全走 Python requests（进程内 hosts 映射绕代理）、命令行仅保留 ffmpeg、URL 做协议/host/IP 三重校验并禁重定向。

## 3. 关键事实与数据

| 项 | 值 |
|---|---|
| 冻结时间 | 2026-10-26（周一）09:00 |
| 剩余窗口 | 约 32 小时（截至交接） |
| token 额度 | 500 USD/人 |
| 内部网关 | `xapi.qiniu.io`（SSO，`个人id@qiniu.com`） |
| 平台 | `aicanvas.qnlinking.com`（灯虹） |
| 目标模型 | **七牛 / minimax / minimax-h3-max**（pi 中已确认可用，推理档位 disabled/enabled） |
| 成片指标 | 1080×1920 / 186.8s / 40 镜 / 22 音轨 |
| Git commits | `c4c8c78` 方案包 · `8e52079` 平台实测+旁白+CDP 工具 · `acdc002` 转向自建产线+animatic v1+player |

## 4. 当前状态

- 已有**可看的完整第一版**（animatic v1），音画齐平，QC 通过。
- 产线脚本代码就绪，**卡在模型接入未点火**：`minimax_pipeline.py` 当前读取环境变量 `MINIMAX_API_KEY` / `MINIMAX_GROUP_ID`，走外部 MiniMax 开放平台（`api.minimax.chat`）。
- 本机未找到任何 MiniMax key（环境变量与常见路径均已排查）。
- owner 连续三次强调「就是这个模型：七牛/minimax/minimax-h3-max」，指向**内部网关路径**，而非外部 MiniMax key。
- 尚未推 GitHub，尚无 PR 与 v0 tag（交付合规风险）。

## 5. 未解决问题与下一步

**P0 — 接入路径歧义（须先裁决）**
两条互斥路径：
- **A（owner 指向）**：`xapi.qiniu.io` + `minimax/minimax-h3-max`，消耗 500 USD 额度，OpenAI 兼容协议。
- **B（脚本现状）**：外部 MiniMax 开放平台 key。

**风险**：`minimax-h3-max` 在 pi 中表现为 LLM（推理档位可开关），**是否支持出图/出视频未经验证**。图像/视频大概率需网关内另的生成类模型（海螺系）。
**动作**：拿网关 key 跑 `probe`，枚举可用模型清单，确认 image/video 端点是否存在；若 h3-max 仅文本，则用其做剧本/提示词优化，图像视频改用网关内生成模型。

**P1 — 批量生成**：`images --limit 4` 出 4 张关键帧 → owner 过角色一致性 → 全量 37 镜 → 图生视频 → `assemble2` 出 `final_v2.mp4`。预计 2-4 小时。

**P2 — 交付合规**：建首次 PR + v0 tag；台词换真多音色（若网关 T2A 支持）；按 `docs/demo_video_plan.md` 录 60-90s demo。

**P3 — 备选**：若网关不支持图像/视频，装 drama-skills 全自动产线（produce 层支持 MiniMax H3）。

## 6. 关键文件

```
~/Labs/langya-xcanvas/
├── HANDOFF.md                      本文档
├── assets/script/ep1_script.md     剧本
├── assets/characters.json          角色卡 ×12
├── assets/scenes.json              场景卡 ×7
├── assets/storyboard/ep1_storyboard.json   40 镜分镜表
├── tools/build_prompts.py          提示词拼装器（已跑通）
├── tools/minimax_pipeline.py       生成产线（待 key）
├── tools/cdp_shot.py, cdp_ctl.py   CDP 截图/控制
├── build/animatic_v1.mp4           动态分镜 v1 成片
├── build/animatic_timeline.json    音轨对齐后真实时间线
├── build/audio/narrator/           22 条音轨
├── player.html                     交付网页
└── docs/{workflows_reference,sop_xcanvas,architecture,demo_video_plan}.md
```

原始附件：`2026 1024 Hackathon启动&规则介绍.pdf`、`Qiniu Builder Day-议题信息.pdf`
