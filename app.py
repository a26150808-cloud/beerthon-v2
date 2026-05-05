import streamlit as st
import yfinance as yf
import pandas as pd
import twstock
import hashlib
import requests
import base64

def send_line_message(message):
    token = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]

    url = "https://api.line.me/v2/bot/message/broadcast"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    data = {
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    r = requests.post(url, headers=headers, json=data)
    return r.status_code
import json
import os
import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo
from ta.trend import MACD
from ta.momentum import RSIIndicator

st.set_page_config(page_title="台股選股系統", layout="wide")

# =========================
# 登入設定
# =========================

# 正式部署時建議全部改用 st.secrets，不建議依賴預設密碼。
DEFAULT_LOGIN_PASSWORD = "123456"
DEFAULT_ADMIN_PASSWORD = "admin888888"

SETTINGS_FILE = "app_settings.json"
LINE_LOG_FILE = "line_log.json"
LINE_TEST_LOG_FILE = "line_test_log.json"
ANALYSIS_LOG_FILE = "analysis_log.json"
ANALYSIS_RESULT_FILE = "analysis_result.json"
FINANCIAL_ERROR_LOG_FILE = "financial_error_log.json"
TOP10_HISTORY_FILE = "top10_history.json"
LOW_PRICE_TOP10_HISTORY_FILE = "low_price_top10_history.json"
TRADE_TRACKING_FILE = "trade_tracking.json"
VISITOR_STATS_FILE = "visitor_stats.json"
GITHUB_PERSIST_FILES = [
    TRADE_TRACKING_FILE,
    ANALYSIS_RESULT_FILE,
    ANALYSIS_LOG_FILE,
    TOP10_HISTORY_FILE,
    LOW_PRICE_TOP10_HISTORY_FILE,
    LINE_LOG_FILE,
]
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
STRATEGY_MODES = ["短線（強勢突破）", "中線（趨勢穩定）"]
LEVEL_RANK = {"S級": 0, "A級": 1, "B級": 2, "C級": 3, "D級": 4}
LEVEL_SORT_WEIGHT = {"S級": 5, "A級": 4, "B級": 3, "C級": 2, "D級": 1}


def hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_taipei():
    return datetime.now(TAIPEI_TZ)


def format_taipei_dt(dt=None):
    if dt is None:
        dt = now_taipei()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def today_taipei():
    return now_taipei().strftime("%Y-%m-%d")


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


def get_secret_or_env(name, default=None):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.environ.get(name, default)


def github_api_settings():
    return {
        "token": get_secret_or_env("GITHUB_TOKEN"),
        "repo": get_secret_or_env("GITHUB_REPO"),
        "branch": get_secret_or_env("GITHUB_BRANCH"),
    }


def github_api_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get_file_sha(path):
    settings = github_api_settings()
    token = settings["token"]
    repo = settings["repo"]
    branch = settings["branch"]

    missing = [name for name, value in {
        "GITHUB_TOKEN": token,
        "GITHUB_REPO": repo,
        "GITHUB_BRANCH": branch,
    }.items() if not value]
    if missing:
        return None, f"缺少 GitHub 設定：{', '.join(missing)}"

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        response = requests.get(
            url,
            headers=github_api_headers(token),
            params={"ref": branch},
            timeout=20,
        )
    except requests.RequestException as exc:
        return None, f"GitHub API 讀取失敗：{exc}"

    if response.status_code == 404:
        return None, None
    if response.status_code >= 400:
        return None, f"GitHub API 讀取失敗：HTTP {response.status_code} {response.text[:200]}"

    return response.json().get("sha"), None


def github_update_file(path, commit_message):
    settings = github_api_settings()
    token = settings["token"]
    repo = settings["repo"]
    branch = settings["branch"]

    missing = [name for name, value in {
        "GITHUB_TOKEN": token,
        "GITHUB_REPO": repo,
        "GITHUB_BRANCH": branch,
    }.items() if not value]
    if missing:
        return False, f"缺少 GitHub 設定：{', '.join(missing)}"

    if not os.path.exists(path):
        return False, "本地檔案不存在"

    sha, sha_error = github_get_file_sha(path)
    if sha_error:
        return False, sha_error

    try:
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
    except OSError as exc:
        return False, f"讀取本地檔案失敗：{exc}"

    payload = {
        "message": commit_message,
        "content": content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        response = requests.put(
            url,
            headers=github_api_headers(token),
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        return False, f"GitHub API 更新失敗：{exc}"

    if response.status_code in (200, 201):
        return True, None

    return False, f"GitHub API 更新失敗：HTTP {response.status_code} {response.text[:200]}"


def persist_runtime_json_files_to_github():
    result = {
        "success": [],
        "failed": [],
        "skipped": [],
        "missing_config": [],
    }

    settings = github_api_settings()
    missing = [name for name, value in {
        "GITHUB_TOKEN": settings["token"],
        "GITHUB_REPO": settings["repo"],
        "GITHUB_BRANCH": settings["branch"],
    }.items() if not value]
    if missing:
        result["missing_config"] = missing
        return result

    for path in GITHUB_PERSIST_FILES:
        if not os.path.exists(path):
            result["skipped"].append({"path": path, "reason": "本地檔案不存在"})
            continue

        ok, reason = github_update_file(path, "Persist runtime tracking data")
        if ok:
            result["success"].append(path)
        else:
            result["failed"].append({"path": path, "reason": reason or "未知錯誤"})

    return result


def save_settings(settings):
    safe_save_json(SETTINGS_FILE, settings)


def load_settings():
    settings = safe_load_json(SETTINGS_FILE, {})

    try:
        secret_password_hash = st.secrets.get("password_hash")
        secret_admin_password_hash = st.secrets.get("admin_password_hash")
    except Exception:
        secret_password_hash = None
        secret_admin_password_hash = None

    if secret_password_hash:
        settings["password_hash"] = secret_password_hash
    elif "password_hash" not in settings:
        settings["password_hash"] = hash_text(DEFAULT_LOGIN_PASSWORD)

    if secret_admin_password_hash:
        settings["admin_password_hash"] = secret_admin_password_hash
    elif "admin_password_hash" not in settings:
        settings["admin_password_hash"] = hash_text(DEFAULT_ADMIN_PASSWORD)

    return settings


def load_line_log():
    return safe_load_json(LINE_LOG_FILE, {})


def save_line_log(data):
    safe_save_json(LINE_LOG_FILE, data)


def load_line_test_log():
    return safe_load_json(LINE_TEST_LOG_FILE, {"tests": []})


def save_line_test_log(data):
    safe_save_json(LINE_TEST_LOG_FILE, data)

def load_analysis_log():
    return safe_load_json(ANALYSIS_LOG_FILE, {})


def save_analysis_log(data):
    safe_save_json(ANALYSIS_LOG_FILE, data)


def load_analysis_result():
    return safe_load_json(ANALYSIS_RESULT_FILE, {})


def save_analysis_result(data):
    safe_save_json(ANALYSIS_RESULT_FILE, data)


def load_financial_error_log():
    return safe_load_json(FINANCIAL_ERROR_LOG_FILE, {"last_updated": None, "errors": []})


def save_financial_error_log(data):
    safe_save_json(FINANCIAL_ERROR_LOG_FILE, data)


def load_top10_history(path):
    return safe_load_json(path, {"records": []})


def save_top10_history(path, data):
    safe_save_json(path, data)


def load_trade_tracking():
    return safe_load_json(TRADE_TRACKING_FILE, {"records": []})


def save_trade_tracking(data, allow_unsafe_overwrite=False):
    old_data = safe_load_json(TRADE_TRACKING_FILE, {"records": []})
    old_records = old_data.get("records", []) if isinstance(old_data, dict) else []
    new_records = data.get("records", []) if isinstance(data, dict) else []
    old_count = len(old_records) if isinstance(old_records, list) else 0
    new_count = len(new_records) if isinstance(new_records, list) else 0

    blocked_reason = None
    if not allow_unsafe_overwrite:
        if old_count > 0 and new_count == 0:
            blocked_reason = f"阻擋 trade_tracking 空資料覆蓋：舊紀錄 {old_count} 筆，新紀錄 0 筆"
        elif old_count >= 10 and new_count < old_count * 0.5:
            blocked_reason = f"阻擋 trade_tracking 異常縮水覆蓋：舊紀錄 {old_count} 筆，新紀錄 {new_count} 筆"

    if blocked_reason:
        append_financial_error("trade_tracking", "save_trade_tracking", "異常覆蓋已阻擋", blocked_reason)
        try:
            st.warning(blocked_reason)
        except Exception:
            pass
        return False

    safe_save_json(TRADE_TRACKING_FILE, data)
    return True


def load_visitor_stats():
    return safe_load_json(VISITOR_STATS_FILE, {"visitors": []})


def save_visitor_stats(data):
    safe_save_json(VISITOR_STATS_FILE, data)


def get_visitor_identity():
    headers = {}

    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}

    ip = (
        headers.get("x-forwarded-for", "").split(",")[0].strip()
        or headers.get("x-real-ip", "").strip()
        or headers.get("remote-addr", "").strip()
    )
    user_agent = headers.get("user-agent", "").strip()
    estimated = not (ip and user_agent)

    if "visitor_session_seed" not in st.session_state:
        st.session_state.visitor_session_seed = str(uuid.uuid4())

    identity_source = f"{ip}|{user_agent}" if not estimated else f"{st.session_state.visitor_session_seed}|{user_agent or 'unknown'}"
    visitor_id = hash_text(identity_source)

    return visitor_id, estimated


def record_visitor():
    stats = load_visitor_stats()
    visitors = stats.get("visitors", [])
    visitor_id, estimated = get_visitor_identity()
    now_text = format_taipei_dt()
    today = today_taipei()

    visitor = next((v for v in visitors if v.get("visitor_id") == visitor_id), None)

    if visitor is None:
        visitor = {
            "visitor_id": visitor_id,
            "first_seen": now_text,
            "last_seen": now_text,
            "visit_count": 0,
            "daily_counts": {},
            "estimated": estimated,
        }
        visitors.append(visitor)

    if not st.session_state.get("visitor_recorded", False):
        visitor["visit_count"] = int(visitor.get("visit_count", 0) or 0) + 1
        daily_counts = visitor.get("daily_counts", {})
        daily_counts[today] = int(daily_counts.get(today, 0) or 0) + 1
        visitor["daily_counts"] = daily_counts
        st.session_state["visitor_recorded"] = True

    visitor["last_seen"] = now_text
    visitor["estimated"] = bool(visitor.get("estimated", False) or estimated)

    stats["visitors"] = visitors
    stats["last_updated"] = now_text
    save_visitor_stats(stats)

    return stats


def summarize_visitor_stats(stats):
    visitors = stats.get("visitors", [])
    today = today_taipei()
    today_visitors = [
        v for v in visitors
        if int(v.get("daily_counts", {}).get(today, 0) or 0) > 0
    ]
    today_total_opens = sum(
        int(v.get("daily_counts", {}).get(today, 0) or 0)
        for v in visitors
    )

    return {
        "total_unique": len(visitors),
        "today_unique": len(today_visitors),
        "today_total_opens": today_total_opens,
        "estimated": any(v.get("estimated", False) for v in visitors),
    }


visitor_stats = record_visitor()
settings = load_settings()

def require_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return

    st.title("🔐 台股選股系統登入")
    st.info("請輸入登入密碼。")

    password = st.text_input("登入密碼", type="password")

    if st.button("登入"):
        if hash_text(password) == settings["password_hash"]:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("密碼錯誤")

    st.stop()


require_login()


# =========================
# 股票清單
# =========================

@st.cache_data
def get_all_tw_stocks():
    stocks = {}

    for code, info in twstock.codes.items():
        try:
            if not code.isdigit():
                continue

            if len(code) != 4:
                continue

            if info.type != "股票":
                continue

            if info.market == "上市":
                symbol = f"{code}.TW"
            elif info.market == "上櫃":
                symbol = f"{code}.TWO"
            else:
                continue

            stocks[symbol] = {
                "code": code,
                "name": info.name,
                "market": info.market
            }

        except Exception:
            continue

    return stocks


# =========================
# 資料下載
# =========================

@st.cache_data(show_spinner=False)
def download_price_data(symbol):
    df = yf.download(symbol, period="5y", progress=False, auto_adjust=False)

    if df.empty or len(df) < 250:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()
    df["VOL20"] = df["Volume"].rolling(20).mean()
    df["HIGH20"] = df["Close"].rolling(20).max()

    macd = MACD(close=df["Close"])
    df["MACD_HIST"] = macd.macd_diff()

    rsi = RSIIndicator(close=df["Close"])
    df["RSI"] = rsi.rsi()

    df["距20日線%"] = (df["Close"] - df["MA20"]) / df["MA20"] * 100
    df["20日波動%"] = df["Close"].rolling(20).std() / df["Close"] * 100

    return df.dropna()


@st.cache_data(show_spinner=False)
def get_recent_trading_value(symbol):
    df = yf.download(symbol, period="5d", progress=False, auto_adjust=False)

    if df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    latest = df.iloc[-1]
    price = float(latest["Close"])
    volume = float(latest["Volume"])

    return price * volume


# =========================
# 流動性
# =========================

def liquidity_pass(price, volume):
    trading_value = price * volume
    trading_value_million = trading_value / 10_000_000

    if price < 10:
        return False, trading_value_million, "股價低於10元"

    if trading_value < 50_000_000:
        return False, trading_value_million, "日成交金額低於5000萬"

    if trading_value >= 300_000_000:
        return True, trading_value_million, "流動性優質，3億以上"

    if trading_value >= 100_000_000:
        return True, trading_value_million, "流動性良好，1億以上"

    return True, trading_value_million, "流動性合格，5000萬以上"


# =========================
# 技術訊號
# =========================

def is_signal(df, i, strategy_mode):
    today = df.iloc[i]
    yesterday = df.iloc[i - 1]

    if "短線" in strategy_mode:
        return (
            today["Close"] > today["MA20"] and
            today["MA5"] > yesterday["MA5"] and
            today["Volume"] > today["VOL20"] * 1.5 and
            today["MACD_HIST"] > 0 and
            today["Close"] >= today["HIGH20"] and
            today["RSI"] < 75 and
            today["距20日線%"] < 15 and
            today["20日波動%"] < 10
        )

    return (
        today["Close"] > today["MA20"] and
        today["Close"] > today["MA60"] and
        today["MA20"] > today["MA60"] and
        today["MA20"] > yesterday["MA20"] and
        today["Volume"] > today["VOL20"] and
        today["MACD_HIST"] > 0 and
        45 <= today["RSI"] < 70 and
        today["距20日線%"] < 10 and
        today["20日波動%"] < 8
    )


# =========================
# 回測
# =========================

def backtest(df, years=3, strategy_mode="短線（強勢突破）"):
    test_df = df.tail(years * 250).copy()
    trades = []

    for i in range(60, len(test_df) - 20):
        if is_signal(test_df, i, strategy_mode):
            entry = float(test_df.iloc[i]["Close"])
            stop_loss = entry * 0.93
            take_profit = entry * 1.10

            for j in range(i + 1, min(i + 21, len(test_df))):
                low = float(test_df.iloc[j]["Low"])
                high = float(test_df.iloc[j]["High"])
                close = float(test_df.iloc[j]["Close"])

                if low <= stop_loss:
                    trades.append((stop_loss - entry) / entry * 100)
                    break

                if high >= take_profit:
                    trades.append((take_profit - entry) / entry * 100)
                    break

                if j == min(i + 20, len(test_df) - 1):
                    trades.append((close - entry) / entry * 100)
                    break

    if not trades:
        return {
            "交易次數": 0,
            "勝率": 0,
            "平均報酬": 0,
            "最大回撤": 0,
            "賺賠比": 0,
        }

    wins = [x for x in trades if x > 0]
    losses = [x for x in trades if x <= 0]

    win_rate = len(wins) / len(trades) * 100
    avg_return = sum(trades) / len(trades)

    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    rr_ratio = avg_win / avg_loss if avg_loss else 0

    equity = 100
    peak = 100
    max_drawdown = 0

    for r in trades:
        equity *= (1 + r / 100)
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak * 100
        max_drawdown = min(max_drawdown, drawdown)

    return {
        "交易次數": len(trades),
        "勝率": round(win_rate, 2),
        "平均報酬": round(avg_return, 2),
        "最大回撤": round(max_drawdown, 2),
        "賺賠比": round(rr_ratio, 2),
    }


# =========================
# 財報分數
# =========================

def classify_financial_error(exc):
    text = str(exc).lower()
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return "網路錯誤"
    if "timeout" in text or "connection" in text or "network" in text:
        return "網路錯誤"
    if isinstance(exc, (KeyError, AttributeError)):
        return "欄位缺失"
    if isinstance(exc, (TypeError, ValueError)):
        return "格式錯誤"
    return "無資料"


def append_financial_error(symbol, source, reason, detail=""):
    log = load_financial_error_log()
    errors = log.get("errors", [])
    errors.append({
        "time": format_taipei_dt(),
        "symbol": symbol,
        "source": source,
        "reason": reason,
        "detail": str(detail)[:200],
    })
    log["last_updated"] = format_taipei_dt()
    log["errors"] = errors[-300:]
    save_financial_error_log(log)


def score_financial_fields(fields):
    score = 0
    notes = []
    missing = []

    eps = fields.get("eps")
    gross_margin = fields.get("gross_margin")
    debt_to_equity = fields.get("debt_to_equity")
    revenue_growth = fields.get("revenue_growth")

    if eps is None:
        missing.append("EPS")
        notes.append("EPS資料不足")
    elif eps > 0:
        score += 20
        notes.append("EPS為正")
    else:
        notes.append("EPS不足")

    if gross_margin is None:
        missing.append("毛利率")
        notes.append("毛利率資料不足")
    elif gross_margin > 0.2:
        score += 20
        notes.append("毛利率佳")
    else:
        notes.append("毛利率不足")

    if debt_to_equity is None:
        missing.append("負債權益比")
        notes.append("負債資料不足")
    elif debt_to_equity < 150:
        score += 20
        notes.append("負債可接受")
    else:
        notes.append("負債偏高")

    if revenue_growth is None:
        missing.append("營收成長")
        notes.append("營收成長資料不足")
    elif revenue_growth > 0:
        score += 20
        notes.append("營收成長")
    else:
        notes.append("營收成長不足")

    return score, notes, missing


def get_yfinance_info_fields(ticker):
    info = ticker.info or {}
    if not info:
        raise ValueError("yfinance info 無資料")

    return {
        "eps": info.get("trailingEps"),
        "gross_margin": info.get("grossMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "revenue_growth": info.get("revenueGrowth"),
    }


def get_yfinance_statement_fields(ticker):
    financials = ticker.quarterly_financials
    balance_sheet = ticker.quarterly_balance_sheet

    if financials is None or financials.empty:
        financials = ticker.financials
    if balance_sheet is None or balance_sheet.empty:
        balance_sheet = ticker.balance_sheet
    if financials is None or financials.empty:
        raise ValueError("yfinance 財務報表無資料")

    latest = financials.iloc[:, 0]
    previous = financials.iloc[:, 1] if financials.shape[1] > 1 else None

    total_revenue = latest.get("Total Revenue")
    gross_profit = latest.get("Gross Profit")
    net_income = latest.get("Net Income")

    gross_margin = None
    if total_revenue and total_revenue != 0 and gross_profit is not None:
        gross_margin = float(gross_profit) / float(total_revenue)

    revenue_growth = None
    if previous is not None:
        prev_revenue = previous.get("Total Revenue")
        if prev_revenue and prev_revenue != 0 and total_revenue is not None:
            revenue_growth = (float(total_revenue) - float(prev_revenue)) / abs(float(prev_revenue))

    debt_to_equity = None
    if balance_sheet is not None and not balance_sheet.empty:
        bs_latest = balance_sheet.iloc[:, 0]
        total_debt = bs_latest.get("Total Debt")
        equity = bs_latest.get("Stockholders Equity")
        if total_debt is not None and equity not in (None, 0):
            debt_to_equity = float(total_debt) / abs(float(equity)) * 100

    return {
        "eps": 1 if net_income is not None and float(net_income) > 0 else None,
        "gross_margin": gross_margin,
        "debt_to_equity": debt_to_equity,
        "revenue_growth": revenue_growth,
    }


def get_external_financial_fields(symbol):
    # 擴充接口：未來可在這裡接 TWSE/MOPS/Yahoo 等合規公開資料來源。
    # 目前 Streamlit Cloud 版本先回傳空資料，避免依賴需要登入或易變動網頁爬取。
    return {}


@st.cache_data(show_spinner=False)
def get_financial_score(symbol):
    ticker = yf.Ticker(symbol)
    fields = {}

    for source_name, loader in [
        ("yfinance_info", get_yfinance_info_fields),
        ("yfinance_statement", get_yfinance_statement_fields),
    ]:
        try:
            source_fields = loader(ticker)
            fields.update({k: v for k, v in source_fields.items() if v is not None})
        except Exception as exc:
            append_financial_error(symbol, source_name, classify_financial_error(exc), exc)

    try:
        backup_fields = get_external_financial_fields(symbol)
        fields.update({k: v for k, v in backup_fields.items() if v is not None})
    except Exception as exc:
        append_financial_error(symbol, "external_interface", classify_financial_error(exc), exc)

    score, notes, missing = score_financial_fields(fields)

    if len(missing) == 4:
        append_financial_error(symbol, "financial_score", "無資料", "所有財報欄位皆缺失")
        return 0, "財報資料不足"

    if missing:
        notes.append("部分財報資料不足")

    return score, "、".join(notes)


# =========================
# 分析股票
# =========================

def analyze_stock(symbol, info, strategy_mode, df=None, financial_data=None):
    if df is None:
        df = download_price_data(symbol)
    if df is None or len(df) < 250:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(latest["Close"])
    volume = float(latest["Volume"])

    liquidity_ok, trading_value_million, liquidity_note = liquidity_pass(close, volume)

    tech_score = 0
    conditions = []
    missing = []

    if "短線" in strategy_mode:
        checks = [
            ("站上20日線", close > float(latest["MA20"])),
            ("5日線上彎", float(latest["MA5"]) > float(prev["MA5"])),
            ("量能放大1.5倍", volume > float(latest["VOL20"]) * 1.5),
            ("MACD轉正", float(latest["MACD_HIST"]) > 0),
            ("突破20日高點", close >= float(latest["HIGH20"])),
            ("RSI未過熱", float(latest["RSI"]) < 75),
            ("未過度遠離20日線", float(latest["距20日線%"]) < 15),
            ("波動未過高", float(latest["20日波動%"]) < 10),
        ]
        min_score = 5
    else:
        checks = [
            ("站上20日線", close > float(latest["MA20"])),
            ("站上60日線", close > float(latest["MA60"])),
            ("20日線高於60日線", float(latest["MA20"]) > float(latest["MA60"])),
            ("20日線上彎", float(latest["MA20"]) > float(prev["MA20"])),
            ("量能高於均量", volume > float(latest["VOL20"])),
            ("MACD為正", float(latest["MACD_HIST"]) > 0),
            ("RSI健康區間", 45 <= float(latest["RSI"]) < 70),
            ("波動偏低", float(latest["20日波動%"]) < 8),
        ]
        min_score = 5

    for name, passed in checks:
        if passed:
            tech_score += 1
            conditions.append(name)
        else:
            missing.append(name)

    is_match = tech_score >= min_score and liquidity_ok

    bt3 = backtest(df, years=3, strategy_mode=strategy_mode)
    bt5 = backtest(df, years=5, strategy_mode=strategy_mode)

    if financial_data is None:
        financial_score, financial_note = get_financial_score(symbol)
    else:
        financial_score, financial_note = financial_data

    recent_low = float(df["Low"].tail(20).min())
    ma20 = float(latest["MA20"])

    stop_loss = max(close * 0.93, ma20 * 0.98, recent_low * 0.98)
    if stop_loss >= close:
        stop_loss = close * 0.93
    tp1 = close * 1.10
    tp2 = close * 1.20

    return {
        "策略模式": strategy_mode,
        "股票代號": info["code"],
        "股票名稱": info["name"],
        "市場": info["market"],
        "收盤價": round(close, 2),

        "是否符合策略": "是" if is_match else "否",
        "差幾條件達標": max(min_score - tech_score, 0),
        "日成交金額_千萬": round(trading_value_million, 2),
        "流動性": liquidity_note,

        "技術分數": tech_score,
        "符合條件": "、".join(conditions) if conditions else "無",
        "未符合條件": "、".join(missing) if missing else "無",

        "距20日線%": round(float(latest["距20日線%"]), 2),
        "20日波動%": round(float(latest["20日波動%"]), 2),
        "RSI": round(float(latest["RSI"]), 2),

        "3年交易次數": bt3["交易次數"],
        "3年勝率%": bt3["勝率"],
        "3年平均報酬%": bt3["平均報酬"],
        "3年最大回撤%": bt3["最大回撤"],
        "3年賺賠比": bt3["賺賠比"],

        "5年交易次數": bt5["交易次數"],
        "5年勝率%": bt5["勝率"],
        "5年平均報酬%": bt5["平均報酬"],
        "5年最大回撤%": bt5["最大回撤"],
        "5年賺賠比": bt5["賺賠比"],

        "財報分數": financial_score,
        "財報備註": financial_note,

        "建議停損": round(stop_loss, 2),
        "第一停利": round(tp1, 2),
        "第二停利": round(tp2, 2),
    }


# =========================
# 評分
# =========================

def calc_total_score(row):
    score = 0

    score += row["技術分數"] * 8
    score += row["財報分數"] * 0.5

    if row["是否符合策略"] == "是":
        score += 15

    if row["3年勝率%"] >= 70:
        score += 25
    elif row["3年勝率%"] >= 60:
        score += 18
    elif row["3年勝率%"] >= 50:
        score += 8

    if row["3年賺賠比"] >= 2:
        score += 25
    elif row["3年賺賠比"] >= 1.5:
        score += 18
    elif row["3年賺賠比"] >= 1:
        score += 8

    if row["3年平均報酬%"] >= 5:
        score += 20
    elif row["3年平均報酬%"] > 0:
        score += 10

    if row["3年最大回撤%"] >= -10:
        score += 15
    elif row["3年最大回撤%"] >= -20:
        score += 8
    elif row["3年最大回撤%"] < -30:
        score -= 15

    if row["3年交易次數"] < 5:
        score -= 25
    elif row["3年交易次數"] < 10:
        score -= 10

    if row["5年平均報酬%"] <= 0:
        score -= 10

    if row["距20日線%"] > 15:
        score -= 12

    if row["20日波動%"] > 8:
        score -= 10

    if row["日成交金額_千萬"] >= 30:
        score += 15
    elif row["日成交金額_千萬"] >= 10:
        score += 8
    elif row["日成交金額_千萬"] >= 5:
        score += 3

    return round(score, 2)


def risk_count(risk_text):
    if not risk_text or risk_text == "風險可接受":
        return 0
    return len([x for x in str(risk_text).split("、") if x])


def is_s_level(row, top5_score):
    # S/A/B/C/D 標準：
    # S級：A級中更強，需總分達160，且技術、量能、財報、風險同時過關。
    # A級：總分90以上，整體條件佳。
    # B級：總分75以上，可觀察。
    # C級：總分60以上，只追蹤。
    # D級：總分60以下，條件不足。
    score_gate = row["總分"] >= 160
    technical_strong = row["是否符合策略"] == "是" and row["技術分數"] >= 6
    volume_ok = row["日成交金額_千萬"] >= 10 and "量能" not in str(row.get("未符合條件", ""))
    fundamental_ok = row["財報分數"] >= 40
    risk_ok = risk_count(row.get("風險提醒", "")) <= 1
    enough_backtest = row["3年交易次數"] >= 10 and row["3年平均報酬%"] > 0

    return all([score_gate, technical_strong, volume_ok, fundamental_ok, risk_ok, enough_backtest])


def get_level(score):
    if score >= 90:
        return "A級"
    elif score >= 75:
        return "B級"
    elif score >= 60:
        return "C級"
    return "D級"


def get_action(row):
    if row["是否符合策略"] == "否":
        if row["差幾條件達標"] <= 1:
            return "接近達標，可列入預備觀察"
        return "尚未符合策略，暫不進場"

    if row["等級"] == "S級":
        return "最優先觀察，可小倉試單，嚴守停損"
    if row["等級"] == "A級":
        return "優先觀察，可小倉試單，嚴守停損"
    if row["等級"] == "B級":
        return "可觀察，等拉回20日線或突破確認"
    if row["等級"] == "C級":
        return "只追蹤，不建議直接追高"
    return "不建議操作"


def get_position(row):
    if row["是否符合策略"] == "否":
        return "不進場"

    if row["等級"] == "S級":
        return "小倉 15%~20%"
    if row["等級"] == "A級":
        return "小倉 10%~20%"
    if row["等級"] == "B級":
        return "觀察倉 5%~10%"
    if row["等級"] == "C級":
        return "暫不進場"
    return "不操作"


def get_risk(row):
    risks = []

    if row["是否符合策略"] == "否":
        risks.append("策略未達標")

    if row["3年交易次數"] < 10:
        risks.append("樣本偏少")

    if row["3年最大回撤%"] < -30:
        risks.append("回撤偏大")

    if row["3年勝率%"] < 60:
        risks.append("勝率未達60%")

    if row["3年賺賠比"] < 1.5:
        risks.append("賺賠比未達1.5")

    if row["財報分數"] < 40:
        risks.append("財報資料不足或偏弱")

    if row["距20日線%"] > 15:
        risks.append("離20日線過遠")

    if row["20日波動%"] > 8:
        risks.append("短期波動偏大")

    return "、".join(risks) if risks else "風險可接受"


def enrich_result(df):
    df["總分"] = df.apply(calc_total_score, axis=1)

    # 🔥 非上市上櫃降權（你要加在這）
    df.loc[df["市場"] == "未知", "總分"] *= 0.7

    df["風險提醒"] = df.apply(get_risk, axis=1)
    df["等級"] = df["總分"].apply(get_level)

    top5_score = df["總分"].quantile(0.95) if len(df) >= 20 else 150
    df.loc[df.apply(lambda row: is_s_level(row, top5_score), axis=1), "等級"] = "S級"

    df["操作建議"] = df.apply(get_action, axis=1)
    df["建議倉位"] = df.apply(get_position, axis=1)
    df["主要理由"] = df.apply(
        lambda row: row["符合條件"] if row["符合條件"] != "無" else row["操作建議"],
        axis=1
    )

    return (
        df.assign(_score_sort=df["總分"].round(2))
        .sort_values(
            by=["是否符合策略", "_score_sort", "3年勝率%", "3年賺賠比", "股票代號"],
            ascending=[False, False, False, False, True]
        )
        .drop(columns=["_score_sort"])
        .reset_index(drop=True)
    )


# =========================
# 自動掃描 24 小時快取
# =========================

@st.cache_data(ttl=86400)
def run_scan(scan_limit):
    stock_pool = get_all_tw_stocks()
    all_items = list(stock_pool.items())

    temp_list = []

    for symbol, info in all_items:
        try:
            trading_value = get_recent_trading_value(symbol)

            if trading_value is not None and trading_value >= 50_000_000:
                temp_list.append({
                    "symbol": symbol,
                    "info": info,
                    "trading_value": trading_value
                })
        except Exception:
            pass

    temp_list = sorted(temp_list, key=lambda x: (-x["trading_value"], x["info"]["code"]))
    selected = temp_list[:int(scan_limit)]

    results_by_strategy = {mode: [] for mode in STRATEGY_MODES}
    price_data_by_symbol = {}
    financial_data_by_symbol = {}

    for item in selected:
        try:
            symbol = item["symbol"]

            if symbol not in price_data_by_symbol:
                price_data_by_symbol[symbol] = download_price_data(symbol)

            price_df = price_data_by_symbol[symbol]
            if price_df is None:
                continue

            if symbol not in financial_data_by_symbol:
                try:
                    financial_data_by_symbol[symbol] = get_financial_score(symbol)
                except Exception as exc:
                    append_financial_error(symbol, "run_scan", classify_financial_error(exc), exc)
                    financial_data_by_symbol[symbol] = (0, "財報資料不足")

            financial_data = financial_data_by_symbol[symbol]

            for mode in STRATEGY_MODES:
                result = analyze_stock(
                    symbol,
                    item["info"],
                    mode,
                    df=price_df,
                    financial_data=financial_data
                )
                if result:
                    results_by_strategy[mode].append(result)
        except Exception:
            pass

    dataframes = {}

    for mode, results in results_by_strategy.items():
        if results:
            dataframes[mode] = enrich_result(pd.DataFrame(results))
        else:
            dataframes[mode] = pd.DataFrame()

    return dataframes, len(temp_list), len(selected), format_taipei_dt()


def top10_display_columns():
    return [
        "股票代號", "股票名稱", "收盤價", "總分", "等級", "主要理由",
        "操作建議", "建議停損", "第一停利", "風險提醒"
    ]


def sort_by_level_then_score(df):
    return (
        df.assign(
            _level_weight=df["等級"].map(LEVEL_SORT_WEIGHT).fillna(0),
            _score_sort=df["總分"].round(2)
        )
        .sort_values(by=["_level_weight", "_score_sort", "股票代號"], ascending=[False, False, True])
        .drop(columns=["_level_weight", "_score_sort"])
        .reset_index(drop=True)
    )


def enforce_s_level_score_floor_for_display(df):
    display_df = df.copy()
    display_df.loc[
        (display_df["等級"] == "S級") & (display_df["總分"] < 160),
        "等級"
    ] = "A級"
    return display_df


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
            str(item.get("股票代號", ""))
        )
    )


def dataframe_to_records(df):
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


def records_to_dataframe(records):
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def build_analysis_result_payload(dfs_by_strategy, liquidity_count, selected_count, analysis_time, scan_limit):
    return {
        "analysis_time": analysis_time,
        "saved_at": format_taipei_dt(),
        "scan_limit": int(scan_limit),
        "liquidity_count": int(liquidity_count),
        "selected_count": int(selected_count),
        "strategies": {
            mode: dataframe_to_records(dfs_by_strategy.get(mode, pd.DataFrame()))
            for mode in STRATEGY_MODES
        },
    }


def parse_analysis_result_payload(payload):
    if not isinstance(payload, dict):
        payload = {}

    strategies = payload.get("strategies", {})
    dfs_by_strategy = {
        mode: records_to_dataframe(strategies.get(mode, []))
        for mode in STRATEGY_MODES
    }
    return (
        dfs_by_strategy,
        int(payload.get("liquidity_count", 0) or 0),
        int(payload.get("selected_count", 0) or 0),
        payload.get("analysis_time", "尚未分析"),
    )


def get_low_price_top10(df):
    if df.empty:
        return pd.DataFrame()
    return (
        df[df["收盤價"] < 60]
        .assign(_score_sort=lambda x: x["總分"].round(2))
        .sort_values(by=["_score_sort", "股票代號"], ascending=[False, True])
        .drop(columns=["_score_sort"])
        .head(10)
        .reset_index(drop=True)
    )


def record_top10_history(path, analysis_time, strategy_mode, top_df):
    if top_df.empty:
        return

    history = load_top10_history(path)
    records = history.get("records", [])
    analysis_date = analysis_time[:10]
    record_id = f"{analysis_date}|{analysis_time}|{strategy_mode}"

    if any(r.get("record_id") == record_id for r in records):
        return

    items = []
    for rank, (_, row) in enumerate(top_df.head(10).iterrows(), start=1):
        items.append({
            "rank": rank,
            "股票代號": row["股票代號"],
            "股票名稱": row["股票名稱"],
            "收盤價": float(row["收盤價"]),
            "總分": round(float(row["總分"]), 2),
            "等級": row["等級"],
            "建議停損": float(row["建議停損"]) if "建議停損" in row else None,
            "第一停利": float(row["第一停利"]) if "第一停利" in row else None,
        })

    records.append({
        "record_id": record_id,
        "analysis_date": analysis_date,
        "analysis_time": analysis_time,
        "strategy_mode": strategy_mode,
        "items": items,
    })

    history["records"] = records[-120:]
    save_top10_history(path, history)


def record_trade_candidates(analysis_time, strategy_mode, candidates_df, source):
    if candidates_df.empty:
        return

    tracking = load_trade_tracking()
    records = tracking.get("records", [])
    existing_keys = {
        (
            r.get("analysis_date"),
            r.get("strategy_mode"),
            str(r.get("股票代號")),
            r.get("source"),
        )
        for r in records
    }
    analysis_date = analysis_time[:10]

    for _, row in candidates_df.iterrows():
        key = (analysis_date, strategy_mode, str(row["股票代號"]), source)
        if key in existing_keys:
            continue

        entry_price = float(row["收盤價"])
        max_tracking_days = 20 if "短線" in strategy_mode else 60
        stop_loss = float(row["建議停損"])
        take_profit = float(row["第一停利"])
        records.append({
            "analysis_date": analysis_date,
            "analysis_time": analysis_time,
            "strategy_mode": strategy_mode,
            "source": source,
            "股票代號": str(row["股票代號"]),
            "股票名稱": row["股票名稱"],
            "等級": row["等級"],
            "總分": round(float(row["總分"]), 2),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "建議停損": stop_loss,
            "第一停利": take_profit,
            "status": "holding",
            "latest_price": entry_price,
            "return_pct": 0.0,
            "exit_date": None,
            "exit_reason": None,
            "max_tracking_days": max_tracking_days,
            "tracking_days": 0,
        })
        existing_keys.add(key)

    tracking["records"] = records
    save_trade_tracking(tracking)


def update_trade_tracking_records():
    tracking = load_trade_tracking()
    records = tracking.get("records", [])
    changed = False

    for record in records:
        strategy_mode = str(record.get("strategy_mode", ""))
        max_tracking_days = int(record.get("max_tracking_days") or (20 if "短線" in strategy_mode else 60))
        record["max_tracking_days"] = max_tracking_days
        record.setdefault("exit_date", None)
        record.setdefault("exit_reason", None)
        record.setdefault("tracking_days", 0)
        record.setdefault("source", record.get("來源", "原本TOP10"))

        if record.get("status", "holding") != "holding":
            changed = True
            continue

        code = str(record.get("股票代號", "")).strip()
        if not code:
            continue

        symbol = f"{code}.TWO" if record.get("市場") == "上櫃" else f"{code}.TW"

        try:
            price_df = download_price_data(symbol)
            if price_df is None:
                alternate_symbol = f"{code}.TWO" if symbol.endswith(".TW") else f"{code}.TW"
                price_df = download_price_data(alternate_symbol)
            if price_df is None or price_df.empty:
                continue

            analysis_date = pd.to_datetime(record.get("analysis_date"), errors="coerce")
            if pd.isna(analysis_date):
                continue

            price_df = price_df.copy()
            price_df.index = pd.to_datetime(price_df.index).tz_localize(None).normalize()
            post_df = price_df[price_df.index > analysis_date.normalize()]

            if post_df.empty:
                changed = True
                continue

            entry_price = float(record.get("entry_price", 0) or 0)
            stop_loss = float(record.get("stop_loss", record.get("建議停損", 0)) or 0)
            take_profit = float(record.get("take_profit", record.get("第一停利", 0)) or 0)
            record["stop_loss"] = stop_loss
            record["take_profit"] = take_profit

            tracking_df = post_df.head(max_tracking_days)
            latest = tracking_df.iloc[-1]
            latest_close = float(latest["Close"])
            record["latest_price"] = round(latest_close, 2)
            record["tracking_days"] = len(tracking_df)

            if entry_price <= 0:
                record["return_pct"] = 0.0
                changed = True
                continue

            closed = False
            for trade_date, day in tracking_df.iterrows():
                high_hit = take_profit > 0 and float(day["High"]) >= take_profit
                low_hit = stop_loss > 0 and float(day["Low"]) <= stop_loss

                if high_hit and low_hit:
                    record["status"] = "loss"
                    record["exit_price"] = round(stop_loss, 2)
                    record["exit_date"] = trade_date.strftime("%Y-%m-%d")
                    record["exit_reason"] = "同日停利與停損皆觸發，保守判定停損"
                    record["return_pct"] = round((stop_loss - entry_price) / entry_price * 100, 2)
                    closed = True
                    break

                if low_hit:
                    record["status"] = "loss"
                    record["exit_price"] = round(stop_loss, 2)
                    record["exit_date"] = trade_date.strftime("%Y-%m-%d")
                    record["exit_reason"] = "觸發停損"
                    record["return_pct"] = round((stop_loss - entry_price) / entry_price * 100, 2)
                    closed = True
                    break

                if high_hit:
                    record["status"] = "win"
                    record["exit_price"] = round(take_profit, 2)
                    record["exit_date"] = trade_date.strftime("%Y-%m-%d")
                    record["exit_reason"] = "觸發第一停利"
                    record["return_pct"] = round((take_profit - entry_price) / entry_price * 100, 2)
                    closed = True
                    break

            if not closed:
                record["return_pct"] = round((latest_close - entry_price) / entry_price * 100, 2)
                if len(post_df) >= max_tracking_days:
                    record["status"] = "expired"
                    record["exit_price"] = round(latest_close, 2)
                    record["exit_date"] = tracking_df.index[-1].strftime("%Y-%m-%d")
                    record["exit_reason"] = f"超過{max_tracking_days}個交易日未觸發停利/停損"

            changed = True
        except Exception as exc:
            append_financial_error(code, "trade_tracking", "價格更新失敗", exc)
            continue

    if changed:
        tracking["records"] = records
        tracking["last_updated"] = format_taipei_dt()
        save_trade_tracking(tracking)

    return tracking


def summarize_trade_tracking(records):
    total = len(records)
    closed = [r for r in records if r.get("status") in ("win", "loss")]
    wins = [r for r in closed if r.get("status") == "win"]
    losses = [r for r in closed if r.get("status") == "loss"]
    holdings = [r for r in records if r.get("status", "holding") == "holding"]
    expired = [r for r in records if r.get("status") == "expired"]
    returns = [float(r.get("return_pct", 0) or 0) for r in closed]

    def win_rate_for(filtered):
        closed_filtered = [r for r in filtered if r.get("status") in ("win", "loss")]
        if not closed_filtered:
            return 0.0
        wins_filtered = [r for r in closed_filtered if r.get("status") == "win"]
        return round(len(wins_filtered) / len(closed_filtered) * 100, 2)

    return {
        "總追蹤筆數": total,
        "已停利win": len(wins),
        "已停損loss": len(losses),
        "追蹤中holding": len(holdings),
        "逾期expired": len(expired),
        "勝率%": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        "平均已結案報酬%": round(sum(returns) / len(returns), 2) if returns else 0.0,
        "S級勝率%": win_rate_for([r for r in records if r.get("等級") == "S級"]),
        "A級勝率%": win_rate_for([r for r in records if r.get("等級") == "A級"]),
        "短線勝率%": win_rate_for([r for r in records if "短線" in str(r.get("strategy_mode", ""))]),
        "中線勝率%": win_rate_for([r for r in records if "中線" in str(r.get("strategy_mode", ""))]),
    }


def filter_trade_records_by_period(records, period_label):
    if period_label == "全部":
        return records

    days_map = {
        "最近30天": 30,
        "最近60天": 60,
        "最近90天": 90,
    }
    days = days_map.get(period_label)
    if days is None:
        return records

    end_date = pd.Timestamp(now_taipei().date())
    start_date = end_date - pd.Timedelta(days=days - 1)
    filtered = []

    for record in records:
        analysis_date = pd.to_datetime(record.get("analysis_date"), errors="coerce")
        if pd.isna(analysis_date):
            continue
        analysis_date = analysis_date.normalize()
        if start_date <= analysis_date <= end_date:
            filtered.append(record)

    return filtered


TRADE_STATUS_FILTERS = {
    "全部": None,
    "已停利 win": "win",
    "已停損 loss": "loss",
    "持有中 holding": "holding",
    "已過期 expired": "expired",
}

TRADE_CLOSED_STATUSES = ("win", "loss", "expired")

TRADE_TRACKING_DISPLAY_COLUMNS = [
    "analysis_date", "strategy_mode", "source", "股票代號", "股票名稱",
    "等級", "總分", "entry_price", "stop_loss", "take_profit",
    "exit_price", "實際報酬%", "status", "exit_reason", "exit_date",
    "tracking_day",
]


def filter_trade_records_by_status(records, status_label):
    status = TRADE_STATUS_FILTERS.get(status_label)
    if status is None:
        return records
    return [r for r in records if r.get("status", "holding") == status]


def build_trade_tracking_display_df(records):
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).copy()
    if df.empty:
        return df

    if "exit_price" not in df.columns:
        df["exit_price"] = pd.NA
    if "exit_date" not in df.columns:
        df["exit_date"] = pd.NA
    if "tracking_day" not in df.columns and "tracking_days" in df.columns:
        df["tracking_day"] = df["tracking_days"]

    if "entry_price" in df.columns and "exit_price" in df.columns:
        entry = pd.to_numeric(df["entry_price"], errors="coerce")
        exit_price = pd.to_numeric(df["exit_price"], errors="coerce")
        valid_return = entry.notna() & exit_price.notna() & (entry != 0)
        return_pct = pd.Series(pd.NA, index=df.index, dtype="Float64")
        return_pct.loc[valid_return] = (
            (exit_price[valid_return] - entry[valid_return]) / entry[valid_return] * 100
        ).round(2)
        df["實際報酬%"] = return_pct

    existing_columns = [c for c in TRADE_TRACKING_DISPLAY_COLUMNS if c in df.columns]
    display_df = df[existing_columns].copy()
    return display_df.astype("object").where(pd.notna(display_df), "")


def get_consecutive_top10(path, strategy_mode, min_days=3, limit=5):
    history = load_top10_history(path)
    records = [
        r for r in history.get("records", [])
        if r.get("strategy_mode") == strategy_mode and r.get("items")
    ]

    latest_by_date = {}
    for record in records:
        latest_by_date[record["analysis_date"]] = record

    dates = sorted(latest_by_date.keys(), reverse=True)
    if not dates:
        return pd.DataFrame()

    latest_record = latest_by_date[dates[0]]
    rows = []

    for item in latest_record["items"]:
        code = item["股票代號"]
        streak = 0

        for date in dates:
            record = latest_by_date[date]
            codes = {x["股票代號"] for x in record["items"]}
            if code in codes:
                streak += 1
            else:
                break

        if streak >= min_days:
            rows.append({
                "股票代號": code,
                "股票名稱": item["股票名稱"],
                "連續天數": streak,
                "最近一次排名": item["rank"],
            })

    return pd.DataFrame(rows).sort_values(
        by=["連續天數", "最近一次排名"],
        ascending=[False, True]
    ).head(limit).reset_index(drop=True) if rows else pd.DataFrame()


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


def send_official_line_after_manual_refresh():
    if st.session_state.get("admin_ok") != True:
        return "正式 LINE 未發送：只有管理員手動刷新後可以觸發。"

    now = now_taipei()
    today = now.strftime("%Y-%m-%d")
    log = load_line_log()

    if not (time(16, 0) <= now.time() <= time(18, 0)):
        return "正式 LINE 未發送：只允許在 16:00～18:00 手動刷新後發送。"

    if log.get("last_official_sent_date") == today:
        return "今日正式 LINE 已發送過，不會重複發送。"

    msg, reason = build_line_message_from_history()
    if reason:
        log["last_skip_date"] = today
        log["last_skip_reason"] = reason
        log["last_checked_at"] = format_taipei_dt(now)
        save_line_log(log)
        return f"正式 LINE 未發送：{reason}"

    status = send_line_message(msg)
    log["last_checked_at"] = format_taipei_dt(now)
    log["last_official_status"] = status

    if status == 200:
        log["last_official_sent_date"] = today
        log["last_official_sent_at"] = format_taipei_dt(now)
        save_line_log(log)
        return "正式 LINE 已於手動刷新後送出。"

    log["last_failed_date"] = today
    log["last_failed_status"] = status
    save_line_log(log)
    return f"正式 LINE 發送失敗：{status}"


def maybe_send_scheduled_line():
    return "正式 LINE 只會在 16:00～18:00 手動刷新後發送一次；本頁不會因重新整理而自動發送。"


def show_github_persist_result(result):
    if not result:
        return

    missing_config = result.get("missing_config", [])
    if missing_config:
        st.warning(f"GitHub 寫回未執行，缺少設定：{', '.join(missing_config)}")
        return

    success = result.get("success", [])
    failed = result.get("failed", [])
    skipped = result.get("skipped", [])

    if success:
        st.success("已寫回 GitHub：" + "、".join(success))
    if skipped:
        skipped_text = "、".join(f"{item['path']}（{item['reason']}）" for item in skipped)
        st.warning("略過 GitHub 寫回：" + skipped_text)
    if failed:
        for item in failed:
            st.error(f"GitHub 寫回失敗：{item['path']}：{item['reason']}")


def perform_manual_refresh(scan_limit):
    st.cache_data.clear()
    dfs_by_strategy, liquidity_count, selected_count, analysis_time = run_scan(scan_limit)

    payload = build_analysis_result_payload(
        dfs_by_strategy,
        liquidity_count,
        selected_count,
        analysis_time,
        scan_limit,
    )
    save_analysis_result(payload)

    analysis_log = load_analysis_log()
    analysis_log["last_analysis_time"] = analysis_time
    save_analysis_log(analysis_log)

    for mode, mode_df in dfs_by_strategy.items():
        if not mode_df.empty:
            mode_top10 = sort_by_level_then_score(enforce_s_level_score_floor_for_display(mode_df)).head(10)
            mode_low_price_top10 = get_low_price_top10(mode_df)

            record_top10_history(
                TOP10_HISTORY_FILE,
                analysis_time,
                mode,
                mode_top10
            )
            record_top10_history(
                LOW_PRICE_TOP10_HISTORY_FILE,
                analysis_time,
                mode,
                mode_low_price_top10
            )
            record_trade_candidates(analysis_time, mode, mode_top10, "原本TOP10")
            record_trade_candidates(analysis_time, mode, mode_low_price_top10, "低價股TOP10")

    trade_tracking = update_trade_tracking_records()
    line_status_text = send_official_line_after_manual_refresh()
    github_persist_result = persist_runtime_json_files_to_github()

    return payload, trade_tracking, line_status_text, github_persist_result


# =========================
# UI
# =========================

st.title("📈 台股選股系統（進階版）")
st.warning("本工具只提供候選股與操作參考，不保證獲利，也不是自動下單。")

with st.sidebar:
    st.header("設定")

    scan_limit = st.selectbox(
        "掃描股票數量",
        options=[300, 500, 1000],
        format_func=lambda x: f"{x} 檔（{'快速' if x == 300 else '平衡' if x == 500 else '完整'}）",
        index=0
    )

    display_strategy = st.radio(
        "顯示策略",
        options=STRATEGY_MODES,
        index=0
    )

    st.divider()

    if st.session_state.get("admin_ok") == True:
        if st.button("🔄 手動刷新今日資料"):
            with st.spinner("正在手動刷新今日資料，請勿關閉頁面。"):
                _, _, refresh_line_status, github_persist_result = perform_manual_refresh(scan_limit)
            st.session_state["manual_refresh_line_status"] = refresh_line_status
            st.session_state["github_persist_result"] = github_persist_result
            st.success("今日資料已手動刷新並儲存。")
            show_github_persist_result(github_persist_result)
        else:
            show_github_persist_result(st.session_state.get("github_persist_result"))
    else:
        st.info("資料由管理員於每日 16:00～18:00 手動更新。")

    st.info("一般使用者只會讀取已儲存的分析結果；建議管理員每日 16:00～18:00 手動更新。")

    st.divider()

    st.header("等級判斷標準")
    grade_detail = st.selectbox("選擇等級", options=["S級", "A級", "B級", "C級", "D級"])
    grade_text = {
        "S級": "分數需達 160，且技術分數強、量能不可明顯轉弱、財報分數至少 40、風險不超過 1 項。適合最優先觀察，小倉試單並嚴守停損。",
        "A級": "總分 90 以上，技術與回測條件佳，量能需達基本流動性，財報不可過弱。適合優先觀察，等待突破或拉回確認。",
        "B級": "總分 75 以上，條件不錯但可能仍有風險或樣本不足。適合觀察倉或等待更明確訊號。",
        "C級": "總分 60 以上，部分條件成立但技術、量能、基本面或風險仍不足。適合追蹤，不建議追高。",
        "D級": "總分低於 60 或多項條件不足。通常策略未達標、風險較多或財報資料不足，暫不建議操作。",
    }
    st.info(grade_text[grade_detail])

    st.divider()

    st.header("密碼管理")

    if "admin_ok" not in st.session_state:
        st.session_state.admin_ok = False

    if not st.session_state.admin_ok:
        admin_password = st.text_input("管理員密碼", type="password")

        if st.button("進入管理模式"):
            if hash_text(admin_password) == settings["admin_password_hash"]:
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error("管理員密碼錯誤")

    else:
        st.success("目前為管理員模式")

        st.subheader("修改使用者登入密碼")

        new_login_password = st.text_input("新的登入密碼", type="password")
        confirm_login_password = st.text_input("再次輸入新的登入密碼", type="password")

        if st.button("修改登入密碼"):
            if new_login_password != confirm_login_password:
                st.error("兩次登入密碼不一致")
            elif len(new_login_password) < 6:
                st.error("登入密碼至少 6 碼")
            else:
                settings["password_hash"] = hash_text(new_login_password)
                save_settings(settings)
                st.success("登入密碼已修改，其他人下次需使用新密碼登入")

        st.divider()

        st.subheader("修改管理員密碼")

        old_admin_password = st.text_input("目前管理員密碼", type="password")
        new_admin_password = st.text_input("新的管理員密碼", type="password")
        confirm_admin_password = st.text_input("再次輸入新的管理員密碼", type="password")

        if st.button("修改管理員密碼"):
            if hash_text(old_admin_password) != settings["admin_password_hash"]:
                st.error("目前管理員密碼錯誤")
            elif new_admin_password != confirm_admin_password:
                st.error("兩次管理員密碼不一致")
            elif len(new_admin_password) < 8:
                st.error("管理員密碼至少 8 碼")
            else:
                settings["admin_password_hash"] = hash_text(new_admin_password)
                save_settings(settings)
                st.success("管理員密碼已修改")

        if st.button("退出管理模式"):
            st.session_state.admin_ok = False
            st.rerun()

    st.divider()

    if st.button("登出"):
        st.session_state.logged_in = False
        st.session_state.admin_ok = False
        st.rerun()

    st.sidebar.markdown("---")
    visitor_summary = summarize_visitor_stats(visitor_stats)
    st.sidebar.caption("📊 訪客統計（參考）")
    st.sidebar.caption(f"累計不重複訪客數：{visitor_summary['total_unique']}")
    st.sidebar.caption(f"今日不重複訪客數：{visitor_summary['today_unique']}")
    st.sidebar.caption(f"今日總開啟次數：{visitor_summary['today_total_opens']}")
    if visitor_summary["estimated"]:
        st.sidebar.markdown(
            "<span style='color: gray; font-size: 0.8rem;'>※ 訪客統計為估算值</span>",
            unsafe_allow_html=True
        )


st.subheader("🔥 今日 Top 10 推薦")

analysis_result = load_analysis_result()
dfs_by_strategy, liquidity_count, selected_count, analysis_time = parse_analysis_result_payload(analysis_result)
trade_tracking = load_trade_tracking()
line_status_text = st.session_state.pop("manual_refresh_line_status", maybe_send_scheduled_line())

st.caption(f"📅 上次分析完成時間：{analysis_time}")

if st.session_state.get("admin_ok") == True:
    if st.button("📱 測試LINE通知"):
        line_message, line_reason = build_line_message_from_history()
        test_message = "🔥 LINE測試成功，你的選股系統已連動\n\n"
        if line_message:
            test_message += line_message
        else:
            test_message += f"正式通知內容目前無法產生：{line_reason}\n"
            test_message += build_low_price_line_section()

        status = send_line_message(test_message)
        test_log = load_line_test_log()
        test_log.setdefault("tests", []).append({
            "time": format_taipei_dt(),
            "status": status
        })
        test_log["tests"] = test_log["tests"][-100:]
        save_line_test_log(test_log)

        if status == 200:
            st.success("LINE測試發送成功，不會影響正式發送狀態")
        else:
            st.error(f"測試發送失敗：{status}")

df = dfs_by_strategy.get(display_strategy, pd.DataFrame())
st.caption(f"目前顯示策略：{display_strategy}。一般瀏覽只讀取已儲存結果，不會重新抓資料。")
st.info(line_status_text)


if df.empty:
    st.info("目前沒有符合資料。可切換策略、調整掃描數量，或手動刷新。")
else:
    st.success(f"流動性合格 {liquidity_count} 檔，分析成交金額前 {selected_count} 檔。")

    top10 = sort_by_level_then_score(enforce_s_level_score_floor_for_display(df)).head(10)
    st.subheader("原本 TOP10")
    st.dataframe(top10[top10_display_columns()], use_container_width=True, hide_index=True)

    consecutive_top10 = get_consecutive_top10(TOP10_HISTORY_FILE, display_strategy)
    st.subheader("連續 3 天以上進入 TOP10 的股票")
    if consecutive_top10.empty:
        st.info("目前無連續 3 天以上進入 TOP10 的股票")
    else:
        st.dataframe(consecutive_top10, use_container_width=True, hide_index=True)

    low_price_top10 = get_low_price_top10(df)
    st.subheader("低價股 TOP10（股價低於 60 元）")
    if low_price_top10.empty:
        st.info("目前沒有股價低於 60 元的 TOP10 候選。")
    else:
        st.dataframe(
            low_price_top10[top10_display_columns()],
            use_container_width=True,
            hide_index=True
        )

    consecutive_low_price = get_consecutive_top10(LOW_PRICE_TOP10_HISTORY_FILE, display_strategy)
    st.subheader("連續 3 天以上進入低價股 TOP10 的股票")
    if consecutive_low_price.empty:
        st.info("目前無連續 3 天以上進入低價股 TOP10 的股票")
    else:
        st.dataframe(consecutive_low_price, use_container_width=True, hide_index=True)

    with st.expander("📊 選股追蹤與勝率統計"):
        st.info("每次 TOP10 會持續追蹤，短線最多 20 個交易日，中線最多 60 個交易日；勝率只計算已停利與已停損紀錄。若舊資料曾用舊規則結案，可刪除 trade_tracking.json 後重新開始追蹤。")
        tracking_records = trade_tracking.get("records", [])
        tracking_filter = st.selectbox(
            "追蹤紀錄策略篩選",
            options=["全部"] + STRATEGY_MODES,
            key="trade_tracking_strategy_filter"
        )
        tracking_period = st.selectbox(
            "統計區間",
            options=["全部", "最近30天", "最近60天", "最近90天"],
            key="trade_tracking_period_filter"
        )

        if tracking_filter == "全部":
            strategy_tracking_records = tracking_records
        else:
            strategy_tracking_records = [
                r for r in tracking_records
                if r.get("strategy_mode") == tracking_filter
            ]

        filtered_tracking_records = filter_trade_records_by_period(strategy_tracking_records, tracking_period)
        tracking_summary = summarize_trade_tracking(filtered_tracking_records)
        st.dataframe(pd.DataFrame([tracking_summary]), use_container_width=True, hide_index=True)

        status_filter = st.selectbox(
            "狀態篩選",
            options=list(TRADE_STATUS_FILTERS.keys()),
            key="trade_tracking_status_filter"
        )
        status_filtered_records = filter_trade_records_by_status(filtered_tracking_records, status_filter)

        st.subheader("回測紀錄查詢")
        if status_filtered_records:
            query_records = sorted(
                status_filtered_records,
                key=lambda r: r.get("analysis_time", ""),
                reverse=True
            )
            query_df = build_trade_tracking_display_df(query_records)
            st.caption(f"目前顯示 {len(query_records)} 筆符合條件的追蹤紀錄。")
            st.dataframe(query_df, use_container_width=True, hide_index=True)
        else:
            st.info("目前沒有符合篩選條件的選股追蹤紀錄。")

        st.subheader("已結案交易")
        closed_records = [
            r for r in filtered_tracking_records
            if r.get("status") in TRADE_CLOSED_STATUSES
        ]
        if closed_records:
            closed_records = sorted(
                closed_records,
                key=lambda r: r.get("exit_date") or r.get("analysis_time", ""),
                reverse=True
            )
            closed_df = build_trade_tracking_display_df(closed_records)
            st.caption(f"目前顯示 {len(closed_records)} 筆已結案交易。")
            st.dataframe(closed_df, use_container_width=True, hide_index=True)
        else:
            st.info("目前沒有已結案交易。")

    best = top10.iloc[0]

    st.subheader("今日第一優先參考")
    st.write(f"策略：{best['策略模式']}")
    st.write(f"股票：{best['股票代號']} {best['股票名稱']}（{best['市場']}）")
    st.write(f"是否符合策略：{best['是否符合策略']}")
    st.write(f"等級：{best['等級']}，總分：{best['總分']}")
    st.write(f"操作建議：{best['操作建議']}")
    st.write(f"建議倉位：{best['建議倉位']}")
    st.write(f"建議停損：{best['建議停損']}")
    st.write(f"第一停利：{best['第一停利']}")
    st.write(f"第二停利：{best['第二停利']}")
    st.write(f"風險提醒：{best['風險提醒']}")

    with st.expander("查看全部分析結果"):
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("查看財報錯誤摘要"):
        financial_error_log = load_financial_error_log()
        financial_errors = financial_error_log.get("errors", [])
        if financial_errors:
            st.dataframe(pd.DataFrame(financial_errors[-50:]), use_container_width=True, hide_index=True)
        else:
            st.info("目前沒有財報錯誤紀錄。")


st.divider()
st.subheader("🔍 單一股票分析")

single_code = st.text_input("輸入股票代號，例如：2330、2317、2454")

if st.button("分析單一股票"):
    if single_code.strip() == "":
        st.warning("請先輸入股票代號")
    else:
        code = single_code.strip()
        stock_pool = get_all_tw_stocks()

        symbol_tw = f"{code}.TW"
        symbol_two = f"{code}.TWO"

        if symbol_tw in stock_pool:
            symbol = symbol_tw
            info = stock_pool[symbol_tw]

        elif symbol_two in stock_pool:
            symbol = symbol_two
            info = stock_pool[symbol_two]

        else:
            # 嘗試非上市上櫃（例如興櫃）
            symbol = symbol_tw
            info = {
                "code": code,
                "name": "非上市上櫃（測試查詢）",
                "market": "未知"
            }

        # 嘗試下載資料（確認是否真的有資料）
        df_test = download_price_data(symbol)

        if df_test is None:
            st.warning("⚠️ 此股票可能為非上市上櫃或資料不足（yfinance 無資料），無法分析")
            st.stop()

        with st.spinner(f"正在分析 {code} {info['name']}..."):
            financial_data = get_financial_score(symbol)
            single_results = []

            for mode in STRATEGY_MODES:
                result = analyze_stock(
                    symbol,
                    info,
                    mode,
                    df=df_test,
                    financial_data=financial_data
                )
                if result:
                    single_results.append(result)

        if single_results:
            st.success(f"{code} {info['name']} 短線 / 中線分析完成")

            tabs = st.tabs(STRATEGY_MODES)

            for tab, mode in zip(tabs, STRATEGY_MODES):
                with tab:
                    mode_rows = [r for r in single_results if r["策略模式"] == mode]
                    if not mode_rows:
                        st.warning("此策略資料不足，無法分析。")
                        continue

                    df_single = enrich_result(pd.DataFrame(mode_rows))
                    st.dataframe(df_single, use_container_width=True, hide_index=True)

                    row = df_single.iloc[0]

                    st.subheader("個股分析結論")
                    st.write(f"股票：{row['股票代號']} {row['股票名稱']}（{row['市場']}）")
                    st.write(f"策略：{row['策略模式']}")
                    st.write(f"是否符合策略：{row['是否符合策略']}")
                    st.write(f"等級：{row['等級']}，總分：{row['總分']}")
                    st.write(f"操作建議：{row['操作建議']}")
                    st.write(f"建議倉位：{row['建議倉位']}")
                    st.write(f"符合條件：{row['符合條件']}")
                    st.write(f"未符合條件：{row['未符合條件']}")
                    st.write(f"財報備註：{row['財報備註']}")
                    st.write(f"風險提醒：{row['風險提醒']}")
        else:
            st.warning("資料不足，無法分析這檔股票。")
