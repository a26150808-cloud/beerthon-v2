import yfinance as yf
import pandas as pd
from ta.trend import MACD
from ta.momentum import RSIIndicator

# 台股清單（先用幾檔測試）
stocks = ["2330.TW", "2317.TW", "2454.TW", "2303.TW"]

results = []

for stock in stocks:
    try:
        df = yf.download(stock, period="3mo")

        if df.empty:
            continue

        # 計算均線
        df["MA5"] = df["Close"].rolling(5).mean()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA60"] = df["Close"].rolling(60).mean()

        # MACD
        macd = MACD(df["Close"])
        df["MACD"] = macd.macd_diff()

        # RSI
        rsi = RSIIndicator(df["Close"])
        df["RSI"] = rsi.rsi()

        latest = df.iloc[-1]

        # 條件
        cond1 = latest["Close"] > latest["MA20"]
        cond2 = latest["MA5"] > df.iloc[-2]["MA5"]
        cond3 = latest["Volume"] > df["Volume"].rolling(20).mean().iloc[-1] * 1.5
        cond4 = latest["MACD"] > 0
        cond5 = latest["Close"] >= df["Close"].rolling(20).max().iloc[-1]

        if all([cond1, cond2, cond3, cond4, cond5]):
            entry = latest["Close"]
            stop_loss = entry * 0.93
            take_profit1 = entry * 1.1
            take_profit2 = entry * 1.2

            results.append({
                "股票": stock,
                "收盤價": round(entry, 2),
                "停損": round(stop_loss, 2),
                "停利1": round(take_profit1, 2),
                "停利2": round(take_profit2, 2)
            })

    except Exception as e:
        print(f"{stock} error: {e}")

df_result = pd.DataFrame(results)

if not df_result.empty:
    df_result.to_excel("台股每日篩選結果.xlsx", index=False)
    print("完成！已輸出 Excel")
else:
    print("今天沒有符合條件的股票")