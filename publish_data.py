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
  1) 读取并校验 source（必须有 SNAP/REG/UP，关键字段齐全，UP.etf 非空）
  2) 陈旧保护：若新数据 asof 早于线上现有 asof，默认拒绝（--force 可强推）
  3) 写入本目录 data.json（自动备份旧版为 data.json.bak）
  4) 若内容与线上一致则直接报告“无变化”并退出，不再误报推送失败
  5) git add data.json && git commit && git push origin <当前分支>
  6) 打印结果；失败会明确告诉你卡在哪一步

注意：本脚本只动 data.json 一个文件，不碰你的算法/页面，零信号漂移。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
SOURCE_PATH = os.path.join(HERE, "data.source.json")  # 默认源落点
REPO_ROOT = HERE                                       # 本目录即仓库根

REQUIRED_ETF_FIELDS = ("code", "name", "upside_score", "pot_est_pct")
REQUIRED_REG_KEYS = ("SSE", "HS300", "DIV", "HSTECH")
EXPECTED_ETF_COUNT = 62  # 仅供参考：数量不符只告警，不阻断


def _asof_dt(s):
    """把 '2026/10/27 16:14:12' 解析为 datetime；解析失败返回 None。"""
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%Y/%m/%d %H:%M:%S")
    except Exception:
        return None


def _validate(d):
    """校验 data.json 结构，缺关键键/字段直接报错，避免写坏站点。"""
    if not isinstance(d, dict):
        raise ValueError("data.json 顶层必须是对象")
    for k in ("SNAP", "REG", "UP"):
        if k not in d:
            raise ValueError("缺少关键键: %s" % k)
    snap = d["SNAP"]
    if not isinstance(snap.get("asof"), str):
        raise ValueError("SNAP.asof 缺失或非字符串")
    if "pe" not in snap:
        raise ValueError("SNAP.pe 缺失（估值栏会崩）")
    etfs = d["UP"].get("etf")
    if not isinstance(etfs, list) or len(etfs) == 0:
        raise ValueError("UP.etf 必须是非空数组（基金数为 0 不正常）")
    for i, e in enumerate(etfs):
        if not isinstance(e, dict):
            raise ValueError("UP.etf[%d] 不是对象" % i)
        for fld in REQUIRED_ETF_FIELDS:
            if fld not in e:
                raise ValueError("UP.etf[%d] 缺少关键字段: %s" % (i, fld))
    reg = d["REG"]
    for k in REQUIRED_REG_KEYS:
        if not isinstance(reg.get(k), dict) or "px" not in reg[k]:
            raise ValueError("REG.%s.px 缺失" % k)
    # 数量不符仅告警
    if len(etfs) != EXPECTED_ETF_COUNT:
        print("[告警] 基金数=%d（预期 %d），请确认是否漏导。" % (len(etfs), EXPECTED_ETF_COUNT))
    return True


def _run(cmd, cwd):
    print("  $ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise RuntimeError("命令失败: " + " ".join(cmd))
    if r.stdout.strip():
        print(r.stdout.strip())
    return r


def _current_branch():
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=REPO_ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.stdout.strip() or "main"
    except Exception:
        return "main"


def main():
    ap = argparse.ArgumentParser(description="把本地新鲜 data.json 推送到 runlin 仓库")
    ap.add_argument("--src", help="本地算出的 data.json 路径；省略则用本目录 data.source.json")
    ap.add_argument("--msg", default=None, help="自定义 commit 说明")
    ap.add_argument("--force", action="store_true", help="即使新数据比线上更旧也强推")
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

    # 2) 陈旧保护：新数据不得早于线上现有数据
    if os.path.exists(DATA_PATH) and not args.force:
        try:
            old = json.load(open(DATA_PATH, encoding="utf-8"))
            old_asof = old.get("SNAP", {}).get("asof")
            new_dt, old_dt = _asof_dt(asof), _asof_dt(old_asof)
            if new_dt and old_dt and new_dt < old_dt:
                print("[拒绝] 新数据 asof=%s 早于线上 asof=%s，拒绝推送以免覆盖更新数据。" % (asof, old_asof))
                print("        若确认要回退，请加 --force。")
                sys.exit(1)
            if new_dt and old_dt and new_dt == old_dt:
                print("[提示] 新数据与线上 asof 相同（%s），将照常推送。" % asof)
        except Exception:
            pass  # 旧文件读不出时不阻断

    # 3) 写入 data.json（备份旧版）
    if os.path.exists(DATA_PATH):
        shutil.copy2(DATA_PATH, DATA_PATH + ".bak")
        print("[备份] 旧版已存为 data.json.bak")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("[写入] 已更新 data.json（asof=%s）" % asof)

    # 采纳后若用的是默认源文件，删除它，避免下次误用旧数据
    if src == SOURCE_PATH and os.path.exists(SOURCE_PATH):
        os.remove(SOURCE_PATH)

    # 4) git 提交 + 推送（先判等，避免误报“推送失败”）
    target_rel = os.path.relpath(DATA_PATH, REPO_ROOT).replace("\\", "/")
    try:
        _run(["git", "add", target_rel], REPO_ROOT)
        # 内容与线上一致则跳过提交/推送
        r = subprocess.run(["git", "diff", "--cached", "--quiet", target_rel],
                           cwd=REPO_ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print("[完成] 数据与线上一致，无需推送（asof=%s）。" % asof)
            sys.exit(0)
        msg = args.msg or ("auto: 更新 data.json (asof=%s)" % asof)
        _run(["git", "commit", "-m", msg], REPO_ROOT)
        branch = _current_branch()
        _run(["git", "push", "origin", branch], REPO_ROOT)
    except RuntimeError:
        print("[推送失败] 数据已写入 data.json，但 git 提交/推送未成功。")
        print("            请检查：1) 本目录是否在 git 仓库内  2) 是否有推送权限/网络")
        print("            手动补推：cd %s && git add %s && git commit -m \"...\" && git push origin %s"
              % (REPO_ROOT, target_rel, _current_branch()))
        sys.exit(1)

    print("[完成] 已推送到仓库（分支 %s），GitHub Pages 通常 1 分钟内生效，刷新网页即可看到 asof=%s 的数据。"
          % (_current_branch(), asof))


if __name__ == "__main__":
    main()
