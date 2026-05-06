"""企业微信智能机器人长连接接入。

通过 WebSocket 连接 wss://openws.work.weixin.qq.com，接收私聊 / 群 @ 消息，
用 DeepSeek tool-calling 解析意图并调用内部工具（库存查询、日报等）回复。

入口：python -m bot.wecom
"""
