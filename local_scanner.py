import os
import sys
from pathlib import Path

# PyInstaller needs these imports because app2.py is loaded dynamically.
import pandas  # noqa: F401
import requests  # noqa: F401
import streamlit  # noqa: F401
import twstock  # noqa: F401
import yfinance  # noqa: F401
from ta.momentum import RSIIndicator  # noqa: F401
from ta.trend import MACD  # noqa: F401


SCAN_LIMIT = 300
OUTPUT_FILES = [
    "analysis_result.json",
    "top10_history.json",
    "low_price_top10_history.json",
    "trade_tracking.json",
    "analysis_log.json",
]


def resolve_project_dir():
    cwd = Path.cwd()
    if (cwd / "app2.py").exists():
        return cwd

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            exe_dir,
            exe_dir.parent,
            exe_dir.parent.parent,
        ]
    else:
        script_dir = Path(__file__).resolve().parent
        candidates = [script_dir, script_dir.parent]

    for candidate in candidates:
        if (candidate / "app2.py").exists():
            return candidate

    return cwd


def load_app2_core(project_dir):
    app2_path = project_dir / "app2.py"
    source = app2_path.read_text(encoding="utf-8-sig")
    marker = "# UI"
    if marker not in source:
        raise RuntimeError("找不到 app2.py 的 UI 區塊標記，無法安全載入核心函式。")

    core_source = source.split(marker, 1)[0]
    core_lines = []
    for line in core_source.splitlines():
        if line.strip() == "require_login()":
            continue
        core_lines.append(line)

    namespace = {
        "__file__": str(app2_path),
        "__name__": "app2_local_core",
    }
    exec(compile("\n".join(core_lines), str(app2_path), "exec"), namespace)
    return namespace


def count_successful_stocks(dfs_by_strategy):
    codes = set()
    fallback_count = 0

    for df in dfs_by_strategy.values():
        if df is None or df.empty:
            continue
        if "股票代號" in df.columns:
            codes.update(str(code) for code in df["股票代號"].dropna())
        else:
            fallback_count = max(fallback_count, len(df))

    return len(codes) if codes else fallback_count


def run_local_scan(core):
    start_time = core["format_taipei_dt"]()
    print(f"分析開始時間：{start_time}")
    print(f"分析成交金額前 {SCAN_LIMIT} 檔")

    run_scan = core["run_scan"]
    dfs_by_strategy, liquidity_count, selected_count, analysis_time = run_scan(SCAN_LIMIT)

    payload = core["build_analysis_result_payload"](
        dfs_by_strategy,
        liquidity_count,
        selected_count,
        analysis_time,
        SCAN_LIMIT,
    )
    core["save_analysis_result"](payload)

    analysis_log = core["load_analysis_log"]()
    analysis_log["last_analysis_time"] = analysis_time
    core["save_analysis_log"](analysis_log)

    top10_created = False
    low_price_top10_created = False
    for mode, mode_df in dfs_by_strategy.items():
        if mode_df.empty:
            continue

        mode_top10 = core["sort_by_level_then_score"](
            core["enforce_s_level_score_floor_for_display"](mode_df)
        ).head(10)
        mode_low_price_top10 = core["get_low_price_top10"](mode_df)

        if not mode_top10.empty:
            top10_created = True
        if not mode_low_price_top10.empty:
            low_price_top10_created = True

        core["record_top10_history"](
            core["TOP10_HISTORY_FILE"],
            analysis_time,
            mode,
            mode_top10,
        )
        core["record_top10_history"](
            core["LOW_PRICE_TOP10_HISTORY_FILE"],
            analysis_time,
            mode,
            mode_low_price_top10,
        )
        core["record_trade_candidates"](analysis_time, mode, mode_top10, "原本TOP10")
        core["record_trade_candidates"](analysis_time, mode, mode_low_price_top10, "低價股TOP10")

    core["update_trade_tracking_records"]()

    finish_time = core["format_taipei_dt"]()
    successful_count = count_successful_stocks(dfs_by_strategy)
    json_ok = all(Path(name).exists() for name in OUTPUT_FILES)

    print(f"分析完成時間：{finish_time}")
    print(f"成功分析股票數：{successful_count}")
    print(f"送入分析股票數：{selected_count}")
    print(f"流動性合格股票數：{liquidity_count}")
    print(f"TOP10 是否產生：{'是' if top10_created else '否'}")
    print(f"低價股 TOP10 是否產生：{'是' if low_price_top10_created else '否'}")
    print(f"是否成功寫入 JSON：{'是' if json_ok else '否'}")
    print("已更新 JSON：")
    for name in OUTPUT_FILES:
        print(f"- {name}")

    if not json_ok:
        missing = [name for name in OUTPUT_FILES if not Path(name).exists()]
        raise RuntimeError("部分 JSON 未產生：" + ", ".join(missing))


def main():
    project_dir = resolve_project_dir()
    os.chdir(project_dir)
    print(f"工作目錄：{project_dir}")

    core = load_app2_core(project_dir)
    run_local_scan(core)


if __name__ == "__main__":
    try:
        main()
        print("本機掃描完成。")
    except Exception as exc:
        print(f"本機掃描失敗：{exc}")
        raise
    finally:
        if getattr(sys, "frozen", False):
            input("按 Enter 關閉視窗...")
