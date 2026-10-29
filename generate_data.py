# -*- coding: utf-8 -*-
"""
润林 · A股港股贵贱指南 —— 数据生成器（云端版）
================================================

【重要：先读这段，搞清楚“为什么刷新不实时”】
------------------------------------------------
本站点（niuxiong123.github.io/runlin）的 data.json 是一套复杂产物：
  - SNAP 32 个字段（含 pe/pb 估值、六线、市场冷热、恒科三档……）
  - REG 四大指数月线
  - UP 62 只基金的因子模型（upside_score / pot_est_pct / factors 等 46 字段）
  - 实证统计、回测、top_buy/sell 等

这套模型的“数据大脑”在【你本机】：
  extract_data.py 的第一行就写死了
  SRC = C:\\Users\\76751\\Documents\\xwechat_files\\...\\realtime_app.html
即：实时行情是在你电脑上的 realtime_app.html（本地应用）里抓取并算出来的，
GitHub 仓库只是被动托管一份静态快照。云端没有任何程序能复现这套模型，
因此：

  ❌ 本脚本（云端跑）无法凭空算出新的 data.json —— 它只认“已经算好的结果”。
  ❌ 给小程序用的 refreshData 云函数是【简化版】（仅 30 只 ETF、无因子模型、无 PE），
     直接套到本页会缺字段、图表崩，不能用。

所以“刷新不实时”的本质：数据源在你电脑里，云端够不着；页面刷新只是反复
下载同一份旧快照（asof 长期停在生成那天）。

【本脚本现在的两种用法】
------------------------------------------------
1) 默认（安全基线）：
   不接数据源时，只复用仓库里已有的 data.json，绝不伪造“已刷新”日期，
   保证站点永远有合法数据、不出错误信号。

2) 采用本地新鲜数据（consume_source）：
   如果你把本地应用算出的新 data.json 放到本目录、命名为 data.source.json，
   本脚本会校验结构后采纳它为新的 data.json（同时记录真实 asof）。
   —— 但真正“自动推到云端”的活儿，请用同目录的 publish_data.py（见下）。

【真正让网页自动变新的两条路（二选一，需你定）】
------------------------------------------------
A) 本地→云端推送桥（推荐，零信号漂移）：
   你本地跑出新版数据 → 运行 publish_data.py → 一条命令把新鲜 data.json
   推送到本仓库 → 页面立刻变新。
   （保留你本地应用当“数据大脑”，不重写任何算法，最安全。）

B) 云端全自动抓取（需你点头）：
   把 62 基金因子模型（_check.js）重写为云端 Python + 东方财富抓取器，
   接进 GitHub Actions，做到“打开网页就拉最新”。工作量大、且重写复杂模型
   有实盘信号偏差风险，未获你明确同意前不要动。

运行依赖：仅标准库（json / os / subprocess / shutil）；git（推送时用）。
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")
SOURCE_PATH = os.path.join(HERE, "data.source.json")  # 本地新鲜数据落点


def _validate(d):
    """校验 data.json 基本结构，缺关键键直接报错，避免写坏站点。"""
    if not isinstance(d, dict):
        raise ValueError("data.json 顶层必须是对象")
    for k in ("SNAP", "REG", "UP"):
        if k not in d:
            raise ValueError("缺少关键键: %s" % k)
    if not isinstance(d["UP"].get("etf"), list) or len(d["UP"]["etf"]) == 0:
        raise ValueError("UP.etf 必须是非空数组")
    if not isinstance(d["REG"].get("HS300"), dict) or "px" not in d["REG"]["HS300"]:
        raise ValueError("REG.HS300.px 缺失")
    return True


def consume_source():
    """若存在 data.source.json，校验后采纳为新的 data.json。返回是否采纳。"""
    if not os.path.exists(SOURCE_PATH):
        return False
    with open(SOURCE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _validate(data)
    # 写新文件前先备份旧版
    if os.path.exists(DATA_PATH):
        shutil.copy2(DATA_PATH, DATA_PATH + ".bak")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    asof = data.get("SNAP", {}).get("asof", "?")
    print("[采纳] 已用 data.source.json 更新 data.json（asof=%s）" % asof)
    # 采纳后删除源，避免下次误用旧数据
    os.remove(SOURCE_PATH)
    return True


def main():
    # 1) 优先采纳本地新鲜数据
    try:
        if consume_source():
            return
    except Exception as e:
        print("[错误] data.source.json 校验/写入失败，未改动 data.json：%s" % e)
        sys.exit(1)

    # 2) 否则进入安全基线：保持现有 data.json，不伪造刷新时间
    if os.path.exists(DATA_PATH):
        d = json.load(open(DATA_PATH, encoding="utf-8"))
        asof = d.get("SNAP", {}).get("asof", "?")
        print("[安全基线] 未检测到本地新鲜数据，保持现有 data.json（asof=%s）。" % asof)
        print("           要用最新数据，请在本机跑出新版后执行 publish_data.py。")
    else:
        print("[错误] 仓库内缺少 data.json 基线，且无 fresh 数据源，无法生成。")
        sys.exit(1)


if __name__ == "__main__":
    main()
