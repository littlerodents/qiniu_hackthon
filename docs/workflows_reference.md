# 短剧制作相关工作流调研（2026-10-24）

结论先行：业界已存在三类可复用的工作流——① 开源技能产线（drama-skills，可直接装进
Claude Code / Codex 类智能体，支持 MiniMax H3 生成后端）；② 画布节点流（纳逗 Pro /
灯虹 XCanvas 这类一站式平台内置）；③ 通用八步法。本方案 = 用 ② 做生成执行，用 ① 的
分层思想管理创作资产，全部落在本仓库数据文件里。

## 1. drama-skills：开源 AI 短剧产线（MIT，最值得直接复用）

仓库：https://github.com/zenstory-ai/drama-skills

11 个技能，覆盖「原著/点子 → 成片」全流程，核心思想是**用多份 Markdown 创作文档
（剧本、视觉设定、分镜、图/视频提示词、剪辑单）保证跨镜一致性，先预览确认再花钱生产**：

| 技能 | 职责 |
|---|---|
| short-drama | 项目初始化、路由、Look Development、Dashboard |
| short-drama-novel-analyze | 原著抽样快评、章节索引、分集候选 |
| short-drama-develop | 可追溯改编、故事引擎、分集地图、导演阐述 |
| short-drama-write | 单集目标、因果节拍、可拍剧本 |
| short-drama-assets | 人物/造型、地点/视图、道具、连续性决策 |
| short-drama-image-prompts | 风格帧与角色/场景/道具参考图提示词 |
| short-drama-storyboard | 镜头、边界、冻结关键帧 |
| short-drama-video-prompts | 单镜动作、摄影、声音、起止状态的图生视频提示词 |
| short-drama-produce | 预览任务、确认后经 adapter 执行生成（**支持 Seedance、MiniMax H3 等**） |
| short-drama-edit | 剪辑单、入出点、字幕响度，渲染成片 |
| short-drama-review | 结构/内容审查与修订 |

推荐顺序：原著分析(可选) → 故事开发 → 分集剧本 → 资产决策 → 图片提示词+分镜 →
视频提示词 → 确认后生产 → 剪辑 → 审查。

与我们的关系：`short-drama-produce` 的 adapter 明确支持 MiniMax H3——比赛内网关里的
`minimax/minimax-h3-max`（已在 ZCode 七牛 provider 下可用）可以作为剧本/提示词层的
生成后端。若后续想把本仓库升级为全自动产线，可 `npx skills add zenstory-ai/drama-skills -y -g`
安装（需 Python 3.9+，剪辑需 ffmpeg；本仓库暂未安装，按需再装）。

## 2. 画布节点流：纳逗 Pro / 灯虹（XCanvas）

来源：https://www.nadou.ai/blog/zh-CN/qa-ai-short-drama-complete-tutorial-html

主路径：文本节点 → 图片节点(含融图) → 分镜节点 → 视频节点(3D 导演台预演运镜) →
音频节点 → 剪辑节点导出。三阶段：剧本决策(定故事/锁剧本/拆分镜) →
视觉生产(定妆/逐镜生成/查一致性) → 收尾(配音/剪辑/导出检查)。

关键实操纪律（灯虹同样适用）：

- 锁剧本检查：陌生人能否两句话说清「谁、要什么、卡在哪」。
- 分镜即「镜头合同」：景别、角度、运镜、动作、声音齐全；单镜只服务一个叙事目的。
- 角色当资产：融图/多参考锁面部结构，全片引用同一设定；服装状态变化单独出设定图。
- 生成顺序：先图生后文生；先低成本试拍确认动作方向，再提品质重跑；相邻镜互为参考帧。
- 检查法：关声音看画面是否清楚；关画面听声音是否成立。
- 片子长就分段生成再拼接——「这是正常工作方式，不是失败」。

失败对策表：

| 问题 | 对策 |
|---|---|
| 角色变脸 | 回融图/多参考；删掉互相打架的动作描述 |
| 镜头跳戏 | 统一参考光线色调；相邻镜互为参考；事后调色收敛 |
| 生成随机 | 先图生后文生；每次只改一个变量复测 |
| 单镜太复杂 | 宁少勿杂，一次只做一件事 |

## 3. 通用八步法（多来源综合）

来源：知乎 Seedance 2.0 实操（https://zhuanlan.zhihu.com/p/2011197758191730921）、
搜狐漫剧工作流（https://timeline.sohu.com/news/GCQFjAE4GS）等。

剧本改编 → 角色资产卡 → 分镜表 → 关键帧(首尾帧) → 图生视频 → AI 配音 →
剪辑合成 → 资产沉淀。共识：先跑通 30 秒–2 分钟片段验证链路，再批量铺开。

## 4. 本方案的映射

| 八步法 | 本仓库落点 | 执行位置 |
|---|---|---|
| 剧本改编 | `assets/script/ep1_script.md` | 本仓库 |
| 角色资产卡 | `assets/characters.json` | 本仓库（参考图在灯虹生成后回链） |
| 场景资产卡 | `assets/scenes.json` | 同上 |
| 分镜表 | `assets/storyboard/ep1_storyboard.json` | 本仓库 |
| 关键帧/图生视频 | `build/prompts/*.txt`（脚本拼装） | 灯虹画布 |
| AI 配音 | 角色卡 `tts` 字段 | 灯虹音频/TTS |
| 剪辑合成 | `docs/sop_xcanvas.md` 第 6 步 | 灯虹剪辑或本地 |
| 资产沉淀 | 本仓库 git 全量管理 | 本仓库 |
