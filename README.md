# 琅琊榜第一集 × XCanvas（灯虹）短剧制作方案

七牛第五届 1024 Hackathon · 非研发赛道 · 议题「用 XCanvas 制作琅琊榜第一集」

> 结论先行：本方案把第一集改编为 **9:16 竖屏、40 个镜头、音轨驱动 186.8 秒**的短剧，
> 采用「剧本/角色/场景/分镜全部结构化为数据文件 + 提示词由脚本拼装 + 生成执行」的
> 工程化产线。**2026-10-25 转向记录**：指定平台 XCanvas/灯虹在参赛网络环境下不可达
> （代理阻断 + 网关 key 无法登录，实测见 docs/sop_xcanvas.md），经 owner 决策改为
> **MiniMax API 直连自建产线**——工具链全部开源可复现，反而强化「AI 工程效率」叙事。

## 快速开始

```bash
python3 tools/build_prompts.py        # ① 拼装 37 份镜头提示词 → build/prompts/
python3 tools/make_animatic.py        # ② 动态分镜 v1（分镜卡+22条TTS音轨）→ build/animatic_v1.mp4
                                      #    音轨驱动时长对齐：分镜预设143.5s → 实际186.8s
# ③ MiniMax key 就位后（凭据只走环境变量）：
#    内部网关已探测确认 LLM-only、无图像/视频通道（docs/decisions.md D2），
#    外部 MiniMax key 是唯一生成路径：
export MINIMAX_API_KEY=... MINIMAX_GROUP_ID=...
python3 tools/minimax_pipeline.py probe            # 连通性/模型探测（先跑）
python3 tools/minimax_pipeline.py images --limit 4 # 关键帧试产4张，人工过一致性四查
python3 tools/minimax_pipeline.py videos --limit 4 # 图生视频试产
python3 tools/minimax_pipeline.py images && python3 tools/minimax_pipeline.py videos
python3 tools/minimax_pipeline.py assemble2        # ④ 成片 → build/final_v2.mp4
open player.html                      # ⑤ 交付网页（播放器+镜头时间线+产线看板）
open build/demo.mp4                   # ⑥ 比赛交付 demo（72s：成片高亮+方法论+降级叙事，tools/make_demo.py 可复跑）
```

## 目录结构

```
assets/
  script/ep1_script.md          # 短剧版第一集剧本（分场 + 钩子节奏 + 改编幅度说明）
  characters.json               # 12 张角色卡：外貌三锚点/服装锚/习惯动作/TTS 音色
  scenes.json                   # 7 张场景卡：固定视觉锚/时段/色板/一致性注意
  storyboard/ep1_storyboard.json# 40 镜头分镜表（景别/运镜/时长/台词/音效/生成模式）
  prompts/style_base.md         # 全局风格基石 + 负面词 + 一致性规则
docs/
  workflows_reference.md        # 调研到的三条短剧工作流（含来源）与本方案的映射
  sop_xcanvas.md                # XCanvas 操作 SOP + 失败重试策略 + 48 小时排期
  architecture.md               # 架构设计文档（模块规格/分工/数据流/风险降级）
  decisions.md                  # 决策记录（平台转向/网关探测证据/v0 tag 依据）
  demo_video_plan.md            # 比赛交付的 demo 视频录屏脚本
tools/
  build_prompts.py              # 提示词拼装器（角色锚+场景锚+动作 → 最终提示词）
build/                          # 生成产物目录（prompts/ 及后续镜头素材归档）
```

## 48 小时排期（冻结：10/26 周一 09:00）

| 时间 | 里程碑 |
|---|---|
| 周六上午 | 定稿剧本/分镜（本仓库已完成初稿）；登录灯虹建项目；角色定妆图 4 选 1 锁定 |
| 周六下午 | 跑通 30 秒全链路（S0 冷开场 + S1 前 2 镜：图→视频→TTS→粗剪） |
| 周六晚 | 铺完全部 40 镜的参考图并巡检一致性；repo 初版 PR |
| 周日 | 批量图生视频 + 分角色 TTS；失败镜头按重试策略处理；晚间粗剪全片 |
| 周日深夜 | 精剪 + 音效/BGM/字幕；录制 demo 视频；架构文档终稿 |
| 周一 8:00 前 | 最后 PR + tag + 提交；留 1 小时缓冲 |

## 评分对照（非研发赛道：产品设计 60% / AI 工程效率 30% / 架构 10%）

- **产品设计 60%**：成片质量与短剧钩子结构（每 20-30 秒一个钩子，见剧本「钩子标注」）；「短剧工厂可复制」的叙事。
- **AI 工程效率 30%**：分镜表即代码、提示词由 `build_prompts.py` 拼装可复跑、重试策略成文、demo 录屏展示全流程。
- **架构设计 10%**：见 `docs/architecture.md` 模块图与数据流。

## 版权与用途说明

《琅琊榜》原著版权归海宴及相关权利方，本作品为内部 Hackathon 演示用途的二创改编，
不对外发布、不商用。成片片尾加二创声明字卡。

## 致谢与来源

- 灯虹官网（一站式 AI 影像创作平台）：https://aicanvas.qnlinking.com
- zenstory-ai/drama-skills（MIT 开源短剧产线技能集）：https://github.com/zenstory-ai/drama-skills
- 纳逗 AI 短剧完整教程：https://www.nadou.ai/blog/zh-CN/qa-ai-short-drama-complete-tutorial-html
- 知乎·用 Seedance 2.0 做 AI 短剧：https://zhuanlan.zhihu.com/p/2011197758191730921
- 搜狐·AI 漫剧完整工作流：https://timeline.sohu.com/news/GCQFjAE4GS
- 百度百科·琅琊榜（分集剧情）：https://baike.baidu.com/item/琅琊榜/12700172
