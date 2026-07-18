# -*- coding: utf-8 -*-
"""
db.py —— 造一份示例数据库（大白话版）
=====================================
真实项目里数据库是公司现成的；这里为了让你"不依赖任何外部库就能跑"，
用代码生成一份确定性的电商数据（同样的种子，每次跑结果一样）。
生成后存成文件 sample_data/demo.db，后面 NL2SQL 生成的 SQL 就真在这个库上执行。
"""

import os
import sqlite3
import random
from datetime import date, timedelta

HERE = os.path.dirname(__file__)
DB_PATH = os.path.join(HERE, "sample_data", "demo.db")


def build() -> str:
    """建库 + 灌数据，返回 db 文件路径。幂等：先删后建。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rnd = random.Random(42)  # 固定种子 → 结果可复现

    # ---- 商品表（4 个商品，跨度几个类目）----
    products = [
        (1, "旗舰手机X", "手机", 5999, "A品牌"),
        (2, "轻薄笔记本", "电脑", 4999, "B品牌"),
        (3, "蓝牙耳机",   "配件", 399,  "A品牌"),
        (4, "纯棉T恤",    "服饰", 99,   "C品牌"),
    ]
    cur.execute("CREATE TABLE product(product_id INTEGER, product_name TEXT, category TEXT, price REAL, brand TEXT)")
    cur.executemany("INSERT INTO product VALUES(?,?,?,?,?)", products)

    # ---- 用户表（30 个用户）----
    cur.execute("CREATE TABLE user(user_id INTEGER, age INTEGER, gender TEXT, city TEXT, vip_level INTEGER)")
    cities = ["北京", "上海", "广州", "深圳", "成都"]
    for uid in range(1, 31):
        cur.execute("INSERT INTO user VALUES(?,?,?,?,?)",
                    (uid, rnd.randint(18, 60), rnd.choice(["M", "F"]),
                     rnd.choice(cities), rnd.choice([0, 0, 1, 1, 2, 3])))

    # ---- 销售订单表：造 6 个月、约 600 笔，带"趋势+异常" ----
    cur.execute("""CREATE TABLE sales_order(
        order_id INTEGER PRIMARY KEY, product_id INTEGER, user_id INTEGER,
        amount REAL, quantity INTEGER, order_date TEXT, channel TEXT, city TEXT)""")

    start = date(2025, 1, 1)
    oid = 0
    for day in range(180):  # 半年
        d = start + timedelta(days=day)
        # 每月销量有"增长趋势"：越往后每天单量越多
        base = 2 + day // 15
        # 故意埋一个异常：第 90 天（约 4 月初）销量暴跌
        if day == 90:
            base = 0
        n = rnd.randint(max(0, base - 1), base + 2)
        for _ in range(n):
            oid += 1
            pid = rnd.choice([1, 2, 3, 4])
            price = dict((p[0], p[3]) for p in products)[pid]
            qty = rnd.randint(1, 3)
            channel = rnd.choice(["app", "pc", "mini_program"])
            city = rnd.choice(cities)
            cur.execute("INSERT INTO sales_order VALUES(?,?,?,?,?,?,?,?)",
                        (oid, pid, rnd.randint(1, 30), price * qty, qty,
                         d.isoformat(), channel, city))

    conn.commit()
    conn.close()
    return DB_PATH


if __name__ == "__main__":
    print("数据库已生成：", build())
