# Telegram 媒体复制机器人

将收到的转发媒体复制到同一个聊天中。支持单条媒体和相册；相册在最后一条消息到达 5 秒后进入发送队列，队列中每次发送间隔 1.5 秒。

## 配置

通过环境变量配置：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `BOT_TOKEN` | Telegram Bot Token，必填 | 无 |
| `BOT_DOMAIN` | Webhook 的公开域名，必填，不包含协议或路径 | 无 |
| `PORT` | Webhook 服务监听端口 | `23795` |

请使用自己的域名，并将其 HTTPS 请求转发到机器人监听的端口。Webhook 路径包含 Bot Token，应避免在公开日志中记录完整 URL，也不要将 Token 提交到仓库。

## 使用容器运行

构建镜像：

```sh
docker build -f Containerfile -t media-copier-tg-bot .
```

设置 `BOT_TOKEN` 和 `BOT_DOMAIN` 环境变量后运行：

```sh
docker run -d --name media-copier-tg-bot \
  -e BOT_TOKEN -e BOT_DOMAIN -p 23795:23795 \
  media-copier-tg-bot
```

向机器人所在的聊天转发媒体，机器人会将其复制到同一聊天。队列和相册收集状态保存在内存中，进程重启后不会保留。
