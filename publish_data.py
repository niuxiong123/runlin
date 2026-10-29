# -*- coding: utf-8 -*-
"""
润林 · 本地→云端 数据推送桥（publish_data.py）
================================================
用途：你本机 realtime_app.html 算出新数据后，用这一条命令把新鲜 data.json
      推送到 runlin 的 GitHub 仓库，网页立刻变新。

前置条件（一次性准备）：
  1) 本机已安装 git，且本目录就是 niuxiong123/runlin 仓库（含 .git）。
  2) 已配置好 git 推送权限（SSH 密钥，或 GitHub CLI，或已登录的凭证）。
  3) 网络可访问 github.com。

用法（二选一）：
  A) 直接指定本地算出的 data.json 路径：
       python publish_data.py --src "D:/xxx/新鲜data.json"
  B) 先把本地数据复制/命名为本目录的 data.source.json，再：
       python publish_data.py
     （publish 会校验、采纳，并复用 generate_data.py 的校验逻辑）

它会做：
  1) 读取并校验 source（必须有 SNAP/REG/UP，UP.etf 非空，REG.HS300.px 存在）
  2) 写入本目录 data.json（自动备份旧版为 data.json.bak）
  3) git add data.json && git commit && git push
  4) 打印结果；失败会明确告诉你卡在哪一步

注意：本脚本只动 data.json 一个文件，不碰你的算法/页面，零信号漂移。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
SOURCE_PATH = os.path.join(HERE, "data.source.json")  # 默认源落点
REPO_ROOT = HERE                                       # 本目录即仓库根


def _validate(d):
    if not isinstance(d, dict):
        raise ValueError("data.json 顶层必须是对象")
    for k in ("SNAP", "REG", "UP"):
        if k not in d:
            raise ValueError("缺少关键键: %s" % k)
    if not isinstance(d["UP"].get("etf"), list) or len(d["UP"]["etf"]) == 0:
        raise ValueError("UP.etf 必须是非空数组（基金数为 0 不正常）")
    if not isinstance(d["REG"].get("HS300"), dict) or "px" not in d["REG"]["HS300"]:
        raise ValueError("REG.HS300.px 缺失")
    return True


def _run(cmd, cwd):
    print("  $ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise RuntimeError("命令失败: " + " ".join(cmd))
    if r.stdout.strip():
        print(r.stdout.strip())
    return r


def main():
    ap = argparse.ArgumentParser(description="把本地新鲜 data.json 推送到 runlin 仓库")
    ap.add_argument("--src", help="本地算出的 data.json 路径；省略则用本目录 data.source.json")
    ap.add_argument("--msg", default=None, help="自定义 commit 说明")
    args = ap.parse_args()

    src = args.src or SOURCE_PATH
    if not os.path.exists(src):
        print("[错误] 找不到数据源：%s" % src)
        print("        请先用 --src 指定本地算出的 data.json，或把数据放到 data.source.json。")
        sys.exit(1)

    # 1) 读取 + 校验
    try:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        _validate(data)
    except Exception as e:
        print("[错误] 数据源校验未通过，未做任何改动：%s" % e)
        sys.exit(1)
    asof = data.get("SNAP", {}).get("asof", "?")
    etf_n = len(data.get("UP", {}).get("etf", []))
    print("[校验通过] asof=%s，基金数=%d" % (asof, etf_n))

    # 2) 写入 data.json（备份旧版）
    if os.path.exists(DATA_PATH):
        shutil.copy2(DATA_PATH, DATA_PATH + ".bak")
        print("[备份] 旧版已存为 data.json.bak")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("[写入] 已更新 data.json（asof=%s）" % asof)

    # 采纳后若用的是默认源文件，删除它，避免下次误用旧数据
    if src == SOURCE_PATH and os.path.exists(SOURCE_PATH):
        os.remove(SOURCE_PATH)

    # 3) git 提交 + 推送
    target_rel = os.path.relpath(DATA_PATH, REPO_ROOT).replace("\\", "/")
    try:
        _run(["git", "add", target_rel], REPO_ROOT)
        msg = args.msg or ("auto: 更新 data.json (asof=%s)" % asof)
        _run(["git", "commit", "-m", msg], REPO_ROOT)
        _run(["git", "push"], REPO_ROOT)
    except RuntimeError:
        print("[推送失败] 数据已写入 data.json，但 git 提交/推送未成功。")
        print("            请检查：1) 本目录是否在 git 仓库内  2) 是否有推送权限/网络")
        print("            手动补推：cd %s && git add %s && git commit -m \"...\" && git push" % (REPO_ROOT, target_rel))
        sys.exit(1)

    print("[完成] 已推送到仓库，GitHub Pages 通常 1 分钟内生效，刷新网页即可看到 asof=%s 的数据。" % asof)


if __name__ == "__main__":
    main()
