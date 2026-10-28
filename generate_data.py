# -*- coding: utf-8 -*-
"""
润林 · A股港股贵贱指南 —— 自动更新数据生成器
================================================
本脚本产出前端站点需要的 data.json（和 index.html 里内嵌的离线快照同结构）。

⚠️⚠️ 请先读这一段（很重要，关系到数字对不对）⚠️⚠️
------------------------------------------------
本仓库目前只带来了"算好的结果数据"（data.json），**没有**带来你 v3 原版
生成器的"算法"。而 data.json 的结构非常复杂（SNAP 32 个键、REG 四大指数、
UP 里 62 只基金 + 实证统计 + 历史回测……），这些买卖判定/分位/回测结果都来自
你原版生成器的具体计算逻辑。

因此本脚本分两种模式：

1) 【安全模式 / 默认】
   在还没接入你原版算法前，脚本**只复用仓库里已有的 data.json**（保留它原始的
   asof / generated 时间，绝不伪造"已刷新"日期），保证站点始终有合法数据、不会
   输出可能错误的买卖信号。Actions 自动跑时也只会"维持现状"，不会乱改数字。

2) 【重算模式 / 接入原版后】
   把你 v3 原版生成器里"产出那个 DATA 字典"的核心函数，整段粘贴到下面的
   build_data(raw) 中（见 TODO 标注）。接入后，脚本会用 akshare 拉实时行情，
   算出和你在本地跑出的一模一样的新 data.json，Actions 才会真正产生"新数据"。

接入步骤（就一步）：
   a. 找到你本地跑出 ah_guide.html 的那个生成脚本（就是你开发服务里的 generate.py）。
   b. 把其中"组装 DATA / 写 data.json"的那段，改成接收本文件的 raw（或直接内部拉数），
      返回完整的 DATA 字典，粘贴进 build_data()。
   c. 在 fetch_raw() 里补全 akshare 接口（下面已给常用示例）。
   d. 本地 `pip install akshare && python generate_data.py` 跑通，确认数字和现版一致，
      再推到 GitHub，Actions 就会自动更新。

运行依赖： pip install akshare
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data.json")


# ---------------------------------------------------------------------------
# 1) 原始行情拉取（akshare，真实可用；需 pip install akshare + 联网）
#    下面给出常用接口示例。akshare 接口名会随版本微调，请以你本地可用版本为准。
# ---------------------------------------------------------------------------
def fetch_raw():
    """拉取生成 data.json 所需的原始数据。

    返回结构建议（供 build_data 使用）：
        {
          "HS300":   {"monthly": [...], "pe": float, "pb": float, ...},
          "SSE":     {"monthly": [...], ...},
          "DIV":     {"monthly": [...], ...},   # 中证红利 / 股息率类
          "HSTECH":  {"monthly": [...], ...},   # 恒生科技
          "etf":     { "<code>": {"nav": [...], ...}, ... }  # 62 只 ETF/基金
        }
    """
    import akshare as ak  # 没装 akshare 时这里会抛 ImportError，被 main 捕获走安全模式

    raw = {}

    # —— 沪深300（000300）日线 → 自行 resample 成月线 ——
    # df = ak.stock_zh_index_daily_em(symbol="sh000300")
    # raw["HS300"] = {"daily": df, ...}

    # —— 上证指数（000001）——
    # raw["SSE"] = {"daily": ak.stock_zh_index_daily_em(symbol="sh000001"), ...}

    # —— 中证红利 / 股息率类（DIV）——
    # raw["DIV"] = {"daily": ak.stock_zh_index_daily_em(symbol="sh000922"), ...}
    # 股息率可用 ak.stock_a_indicator_lg(symbol="000922") 等

    # —— 恒生科技（HSTECH，港股）——
    # raw["HSTECH"] = {"daily": ak.stock_hk_daily(symbol="HSTECH"), ...}
    # 或 ak.stock_hk_index_hist_em(symbol="HSTECH", ...)

    # —— 62 只 ETF / 基金净值 ——
    # ETF_CODES = ["512000", "510300", ...]  # 见现版 data.json 的 UP.etf[].code
    # raw["etf"] = {c: ak.fund_etf_hist_em(symbol=c, period="daily", ...) for c in ETF_CODES}

    # TODO: 按你原版生成器补全以上 akshare 调用，组装成 raw 字典
    raise NotImplementedError("fetch_raw 尚未接入数据源，请在上方补全 akshare 调用")


# ---------------------------------------------------------------------------
# 2) 指标计算（核心算法插槽 —— 这是接原版生成器的关键位置）
# ---------------------------------------------------------------------------
def build_data(raw):
    """把原始行情计算成完整的 DATA 字典（即 data.json 的顶层内容）。

    TODO（关键一步）：把你 v3 原版生成器"产出 DATA 字典"的核心逻辑粘贴到这里。
    下面是目前的安全模式：直接复用仓库内已有的 data.json，保持原始时间不伪造。
    """
    # ===== 安全模式（默认）：复用已有基线，绝不输出可能错误的信号 =====
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            base = json.load(f)
        # 若已接入原版算法（raw 非 None 且可用），应在此用 raw 重算并返回新 DATA，
        # 例如： return compute_v3_data(raw)
        return base
    raise FileNotFoundError("仓库内缺少 data.json 基线，且未接入原版算法，无法生成")


# ---------------------------------------------------------------------------
# 3) 入口
# ---------------------------------------------------------------------------
def main():
    recomputed = False
    data = None
    try:
        raw = fetch_raw()
        data = build_data(raw)      # 接入原版后会真正重算
        recomputed = True
    except NotImplementedError:
        print("[安全模式] 未接入原版指标算法：复用仓库内已有 data.json（不伪造刷新时间）。")
        print("           要自动算出全新数据，请把 v3 原版生成器核心逻辑粘贴到 build_data()。")
        data = build_data(None)
    except ImportError:
        print("[安全模式] 未安装 akshare（pip install akshare），复用仓库内已有 data.json。")
        data = build_data(None)
    except Exception as e:  # 任何拉数/计算异常都退回安全模式，保证站点可用
        print(f"[回退] 拉取/计算失败：{e}")
        if os.path.exists(DATA_PATH):
            data = build_data(None)
        else:
            raise

    # 仅在内容变化时写文件，避免 Actions 产生空提交
    new_text = json.dumps(data, ensure_ascii=False, indent=1)
    old_text = ""
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            old_text = f.read()
    if new_text.strip() == old_text.strip():
        print("[跳过] data.json 内容无变化，未写入。")
        return

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        f.write(new_text)
    asof = data.get("SNAP", {}).get("asof", "?")
    print(f"[{'重算' if recomputed else '复用'}] 已写入 data.json（asof={asof}）")


if __name__ == "__main__":
    main()
