# -*- coding: utf-8 -*-
"""
config.py —— 全局配置（大白话版）
=================================
这个文件只干一件事：把"接真实 LLM 需要的信息"和"示例数据库"集中放好。
你不用改代码，只要在终端 export 两个环境变量就能跑：
    export OPENAI_API_KEY="sk-xxx"
    export OPENAI_BASE_URL="https://api.openai.com/v1"   # 想用 DeepSeek 就换成它的地址
    export MODEL="gpt-4o-mini"                            # 或 deepseek-chat
"""

import os

# ---- 1) LLM 配置：全部从环境变量读，没写死在代码里（方便换模型/换厂商）----
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")          # 没填就是空字符串，运行时会被拦下提示
LLM_MODEL = os.getenv("MODEL", "gpt-4o-mini")

# ---- 2) 示例数据库：我们用一个"电商销售"小库演示智能问数 ----
# 表结构（这就是 DGP 数据治理后、喂给 TableRAG/NL2SQL 的"元数据"）：
SCHEMA_REGISTRY = {
    "sales_order": {                       # 销售订单表（明细表：一行一笔订单）
        "comment": "电商平台的销售订单明细，一行代表一笔成交订单",
        "columns": {
            "order_id":      "订单编号，主键",
            "product_id":    "商品编号，关联 product 表",
            "user_id":       "下单用户编号",
            "amount":        "订单金额（元），这就是'销售额'的来源",
            "quantity":      "购买数量",
            "order_date":    "下单日期，格式 YYYY-MM-DD",
            "channel":       "下单渠道：app / pc / mini_program（小程序）",
            "city":          "收货城市",
        },
    },
    "product": {                            # 商品表（维度表）
        "comment": "商品基础信息，一行代表一个在售商品",
        "columns": {
            "product_id":   "商品编号，主键",
            "product_name": "商品名称",
            "category":     "商品类目：手机 / 电脑 / 配件 / 服饰",
            "price":        "商品单价（元）",
            "brand":        "品牌",
        },
    },
    "user": {                               # 用户表（维度表）
        "comment": "平台注册用户，一行代表一个用户",
        "columns": {
            "user_id":  "用户编号，主键",
            "age":      "年龄",
            "gender":   "性别：M / F",
            "city":     "常驻城市",
            "vip_level":"会员等级：0普通 1银卡 2金卡 3钻石",
        },
    },
}
