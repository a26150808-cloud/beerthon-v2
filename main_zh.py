# -*- coding: utf-8 -*-

import pandas as pd
import math
import os


def 建立測試資料():
    data = {
        "魚種": ["鮭魚"]*5 + ["鱈魚"]*5,
        "原料編號": [f"RM{i:03d}" for i in range(1, 11)],
        "原料重量(kg)": [50,30,45,25,55,60,40,35,20,38],
        "可切規格(g)": [250,300,200,350,400,150,200,250,300,180],
        "訂單規格(g)": [200,250,200,300,350,150,150,200,250,150],
        "訂單需求數量": [150,80,200,60,100,300,200,120,50,180],
        "售價": [120,150,110,180,210,80,90,100,130,85],
        "成本(每kg)": [180,200,160,220,280,100,120,130,150,110],
    }

    df = pd.DataFrame(data)
    df.to_excel("sample_data.xlsx", index=False)
    print("✔ 已建立 sample_data.xlsx")
    return df


def 讀取資料():
    if not os.path.exists("sample_data.xlsx"):
        return 建立測試資料()
    print("✔ 已讀取 sample_data.xlsx")
    return pd.read_excel("sample_data.xlsx")


def 計算(df):
    結果 = []

    for _, r in df.iterrows():
        if r["可切規格(g)"] >= r["訂單規格(g)"]:
            最大片數 = math.floor(r["原料重量(kg)"]*1000 / r["訂單規格(g)"])
            實際片數 = min(最大片數, r["訂單需求數量"])

            使用重量 = 實際片數 * r["訂單規格(g)"] / 1000
            浪費 = r["原料重量(kg)"] - 使用重量
            利潤 = 實際片數 * r["售價"] - r["原料重量(kg)"] * r["成本(每kg)"]

        else:
            實際片數 = 0
            使用重量 = 0
            浪費 = r["原料重量(kg)"]
            利潤 = -r["原料重量(kg)"] * r["成本(每kg)"]

        結果.append({
            "原料編號": r["原料編號"],
            "魚種": r["魚種"],
            "生產片數": 實際片數,
            "浪費(kg)": round(浪費,2),
            "利潤": round(利潤,0)
        })

    return pd.DataFrame(結果)


def 輸出(df):
    print("\n=== 分析結果 ===")
    print(df)

    最佳 = df.loc[df["利潤"].idxmax()]

    print("\n=== 最佳方案 ===")
    print(f"原料：{最佳['原料編號']}")
    print(f"魚種：{最佳['魚種']}")
    print(f"利潤：{最佳['利潤']}")


if __name__ == "__main__":
    print("=== 水產品決策工具 ===")

    df = 讀取資料()
    結果 = 計算(df)
    輸出(結果)