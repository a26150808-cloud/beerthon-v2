import json
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import requests


LINE_LOG_FILE = "line_log.json"
TOP10_HISTORY_FILE = "top10_history.json"
LOW_PRICE_TOP10_HISTORY_FILE = "low_price_top10_history.json"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
LEVEL_SORT_WEIGHT = {"S級": 5, "A級": 4, "B級": 3, "C級": 2, "D級": 1}


def now_taipei():
    return datetime.now(TAIPEI_TZ)


def format_taipei_dt(dt=None):
    if dt is None:
        dt = now_taipei()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def safe_load_json(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def safe_save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_line_log():
    return safe_load_json(LINE_LOG_FILE, {})


def save_line_log(data):
    safe_save_json(LINE_LOG_FILE, data)


def load_top10_history(path):
    return safe_load_json(path, {"records": []})


def sort_history_items_by_level_then_score(items):
    normalized_items = []

    for item in items:
        normalized = item.copy()
        normalized["總分"] = round(float(normalized.get("總分", 0) or 0), 2)
        if normalized.get("等級") == "S級" and normalized["總分"] < 160:
            normalized["等級"] = "A級"
        normalized_items.append(normalized)

    return sorted(
        normalized_items,
        key=lambda item: (
            -LEVEL_SORT_WEIGHT.get(item.get("等級"), 0),
            -round(float(item.get("總分", 0) or 0), 2),
            str(item.get("股票代號", "")),
        ),
    )


def build_low_price_line_section(strategy_mode=None):
    history = load_top10_history(LOW_PRICE_TOP10_HISTORY_FILE)
    records = [
        r for r in history.get("records", [])
        if r.get("items") and (strategy_mode is None or r.get("strategy_mode") == strategy_mode)
    ]

    if not records and strategy_mode is not None:
        records = [r for r in history.get("records", []) if r.get("items")]

    section = "\n【低價股 TOP5（股價低於60元）】\n"

    if not records:
        return section + "目前沒有低價股分析紀錄。\n"

    latest = sorted(records, key=lambda r: r.get("analysis_time", ""), reverse=True)[0]
    items = [
        item for item in latest.get("items", [])
        if float(item.get("收盤價", 999999) or 999999) < 60
    ]
    items = sort_history_items_by_level_then_score(items)[:5]

    if not items:
        return section + "目前沒有股價低於60元的候選股。\n"

    for item in items:
        stop_loss_text = item.get("建議停損") or "未記錄"
        take_profit_text = item.get("第一停利") or "未記錄"
        section += (
            f"{item['股票代號']} {item['股票名稱']}\n"
            f"收盤價：{item['收盤價']}｜總分：{item['總分']}｜等級：{item['等級']}\n"
            f"停損價：{stop_loss_text}｜停利價：{take_profit_text}\n\n"
        )

    return section


def build_line_message_from_history():
    history = load_top10_history(TOP10_HISTORY_FILE)
    records = history.get("records", [])
    if not records:
        return None, "沒有最新分析結果"

    latest = sorted(records, key=lambda r: r.get("analysis_time", ""), reverse=True)[0]
    items = sort_history_items_by_level_then_score(latest.get("items", []))[:10]
    if not items:
        return None, "最新分析結果沒有 TOP10"

    msg = (
        f"🔥 前一次分析 TOP10\n"
        f"策略：{latest.get('strategy_mode', '未記錄')}\n"
        f"分析完成：{latest.get('analysis_time', '未記錄')}\n\n"
    )

    for rank, item in enumerate(items, start=1):
        stop_loss_text = item.get("建議停損") or "未記錄"
        take_profit_text = item.get("第一停利") or "未記錄"
        msg += (
            f"{rank}. {item['股票代號']} {item['股票名稱']}\n"
            f"等級：{item['等級']}｜總分：{item['總分']}\n"
            f"收盤價：{item['收盤價']}\n"
            f"停損價：{stop_loss_text}｜停利價：{take_profit_text}\n\n"
        )

    msg += build_low_price_line_section(latest.get("strategy_mode"))

    return msg, None


def get_latest_top10_record():
    history = load_top10_history(TOP10_HISTORY_FILE)
    records = [r for r in history.get("records", []) if r.get("items")]
    if not records:
        return None
    return sorted(records, key=lambda r: r.get("analysis_time", ""), reverse=True)[0]


def latest_analysis_is_fresh(now, latest_record):
    if not latest_record:
        return False, "沒有 TOP10 分析紀錄"

    analysis_date = latest_record.get("analysis_date")
    today = now.strftime("%Y-%m-%d")
    yesterday = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")

    if analysis_date in (today, yesterday):
        return True, None

    return False, f"最新分析日期太舊：{analysis_date}"


def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        return None, "缺少 LINE_CHANNEL_ACCESS_TOKEN"

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data, timeout=30)
    return response.status_code, response.text[:300]


def should_send(now, log, latest_record):
    today = now.strftime("%Y-%m-%d")

    if now.weekday() >= 5:
        return False, "週末不發送"
    if not (time(8, 0) <= now.time() <= time(8, 30)):
        return False, "不在 08:00～08:30 發送時段"
    if log.get("last_official_sent_date") == today:
        return False, "今日已發送"

    fresh, reason = latest_analysis_is_fresh(now, latest_record)
    if not fresh:
        return False, reason

    return True, None


def main():
    now = now_taipei()
    today = now.strftime("%Y-%m-%d")
    log = load_line_log()
    latest_record = get_latest_top10_record()
    ok, reason = should_send(now, log, latest_record)

    log["last_checked_at"] = format_taipei_dt(now)

    if not ok:
        log["last_skip_date"] = today
        log["last_skip_reason"] = reason
        save_line_log(log)
        print(f"Skip: {reason}")
        return

    msg, reason = build_line_message_from_history()
    if reason:
        log["last_skip_date"] = today
        log["last_skip_reason"] = reason
        save_line_log(log)
        print(f"Skip: {reason}")
        return

    status, detail = send_line_message(msg)
    log["last_official_status"] = status

    if status == 200:
        log["last_official_sent_date"] = today
        log["last_official_sent_at"] = format_taipei_dt(now)
        save_line_log(log)
        print("LINE sent successfully")
        return

    log["last_failed_date"] = today
    log["last_failed_status"] = status
    log["last_failed_detail"] = detail
    save_line_log(log)
    raise SystemExit(f"LINE send failed: {status} {detail}")


if __name__ == "__main__":
    main()
