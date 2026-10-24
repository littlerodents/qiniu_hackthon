#!/usr/bin/env python3
"""提示词拼装器：把 风格基石+场景锚+角色锚+镜头动作 合成为每个镜头的最终提示词。

用法: python3 tools/build_prompts.py   （在仓库根目录执行）
输出: build/prompts/<镜头号>.txt 与 build/prompts/manifest.json
规则见 assets/prompts/style_base.md：前三段一字不动，只追加本镜可变段。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE_BASE = ("中国古装正剧质感，电影级画面，低饱和青灰色调配暖烛金点缀，自然光效，"
              "织物与甲胄材质细节，9:16竖构图人物中置，上三分之一留天光、下三分之一留字幕位")
NEGATIVE = ("负面：现代元素、错朝代服饰、塑料质感、过曝、多余手指、肢体畸变、人脸畸变、"
            "背景文字乱码、水印、logo、多余人物")

SIZE_CN = {
    "extreme_wide": "大远景", "wide": "全景", "medium": "中景", "medium_close": "近景",
    "close": "特写", "medium_two_shot": "中景双人同框", "full_frame": "全画面",
}
CAMERA_CN = {
    "slow_push_in": "镜头缓慢推近", "slow_push": "镜头缓慢推近", "static": "固定机位",
    "lateral_dolly": "横向移动镜头", "slow_fade": "缓慢淡出", "aerial_slow_orbit": "航拍缓慢环绕",
    "low_angle": "仰拍", "static_two_shot": "固定机位双人同框", "slow_fall": "跟随下坠慢镜",
    "insert_x2": "两段特写快切", "snap_zoom": "急推变焦", "slow_motion_action": "慢动作动作镜头",
    "crane_up": "镜头缓缓升起", "crane_down": "镜头缓缓下降", "aerial_push": "航拍推进",
    "rack_focus": "焦点由远及近转移", "static_high": "固定高机位俯拍", "flash_cut": "闪回快切",
    "symmetric_push": "对称构图缓慢推进", "slow_push_in_hero": "英雄式缓慢推近",
    "over_shoulder_x2": "过肩镜头两段快切", "static_silhouette": "固定机位剪影",
}


def cn(mapping: dict, key: str) -> str:
    return mapping.get(key, key)


def main() -> int:
    chars_raw = json.loads((ROOT / "assets/characters.json").read_text(encoding="utf-8"))
    scenes_raw = json.loads((ROOT / "assets/scenes.json").read_text(encoding="utf-8"))
    board = json.loads((ROOT / "assets/storyboard/ep1_storyboard.json").read_text(encoding="utf-8"))

    chars = {c["id"]: c for c in chars_raw["characters"]}
    scenes = {s["id"]: s for s in scenes_raw["scenes"]}
    out_dir = ROOT / "build" / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)

    errors, manifest = [], []
    for shot in board["shots"]:
        sid = shot["id"]
        if shot.get("gen_mode") == "post_only":
            manifest.append({"id": sid, "type": "post_only", "note": shot.get("post", "")})
            continue
        scene = scenes.get(shot["scene"])
        if scene is None:
            errors.append(f"{sid}: 未知场景 {shot['scene']}")
            continue
        parts = [STYLE_BASE, scene["scene_prompt"]]
        for cid in shot.get("chars", []):
            c = chars.get(cid)
            if c is None:
                errors.append(f"{sid}: 未知角色 {cid}")
                continue
            parts.append(c["appearance_prompt"])
        parts.append(f"{cn(SIZE_CN, shot['size'])}，{cn(CAMERA_CN, shot['camera'])}，{shot['action']}")
        parts.append(NEGATIVE)
        prompt = "，".join(p.strip("，") for p in parts if p)
        (out_dir / f"{sid}.txt").write_text(prompt + "\n", encoding="utf-8")
        manifest.append({"id": sid, "type": "gen", "chars": shot.get("chars", []),
                         "scene": shot["scene"], "dur": shot["dur"],
                         "prompt_file": f"build/prompts/{sid}.txt"})

    (out_dir / "manifest.json").write_text(
        json.dumps({"project": board["project"], "total": len(board["shots"]),
                    "generated": len(manifest), "manifest": manifest},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    gen_count = sum(1 for m in manifest if m["type"] == "gen")
    print(f"镜头总数 {len(board['shots'])}，生成类提示词 {gen_count} 份，纯后期 {len(manifest) - gen_count} 份")
    print(f"输出目录: {out_dir}")
    if errors:
        print("校验错误:", *errors, sep="\n  - ")
        return 1
    print("校验通过：所有镜头的场景与角色引用均有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
