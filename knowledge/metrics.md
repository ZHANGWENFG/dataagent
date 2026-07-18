# 指标口径定义

## 销售额
销售额指已完成订单的订单金额（amount 字段）之和。默认口径：amount 已扣除退款，因此"销售额"不含退款订单。统计时间按 order_date（下单日期，格式 YYYY-MM-DD）。

## 城市维度
city 字段在 sales_order（收货城市）与 user（常驻城市）两表都有。问"各城市"默认指 sales_order.city（收货城市）。

## 渠道 channel
channel 取值：app / pc / mini_program（小程序）。"线上渠道"包含 app 与 mini_program，不含 pc。

## 会员等级 vip_level
user.vip_level：0 普通、1 银卡、2 金卡、3 钻石。高级会员指 vip_level >= 2。
