import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 1. 全局异步队列，用于存放待发送的任务
send_queue = asyncio.Queue()

# 2. 收集媒体组（相册）的全局字典
# 格式: { media_group_id: {"messages": [message_id, ...], "task": asyncio.Task} }
media_groups = {}

async def queue_worker() -> None:
    """
    后台工作协程：严格控制发送频率。
    从队列中获取任务，每发送一次后强制等待 1.5 秒，彻底解决 429 报错。
    """
    logger.info("后台队列工作协程已启动...")
    while True:
        task = await send_queue.get()
        try:
            bot = task["bot"]
            chat_id = task["chat_id"]
            
            if task["type"] == "single":
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_id=task["message_id"]
                )
                logger.info(f"[队列] 成功复制单张媒体: {task['message_id']}")
                
            elif task["type"] == "group":
                await bot.copy_messages(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_ids=task["message_ids"]
                )
                logger.info(f"[队列] 成功复制相册: {task['message_ids']}")
                
        except Exception as e:
            logger.error(f"[队列] 执行发送任务失败: {e}")
        finally:
            send_queue.task_done()
            # 核心限速：每次发送后强制等待 1.5 秒，严格遵守 Telegram 的频率限制
            await asyncio.sleep(1.5)

async def collect_media_group(media_group_id: str, chat_id: int, bot) -> None:
    try:
        # 防抖核心：每次收到新图片，这个任务都会被取消并重新创建。
        # 只有当连续 5.0 秒内没有收到该相册的新图片时，才会触发发送。
        await asyncio.sleep(5.0)
        
        if media_group_id in media_groups:
            group_data = media_groups.pop(media_group_id)
            message_ids = sorted(group_data["messages"])  # 必须升序排列
            
            # 将相册任务推入队列排队
            await send_queue.put({
                "type": "group",
                "chat_id": chat_id,
                "message_ids": message_ids,
                "bot": bot
            })
            logger.info(f"[收集器] 相册 {media_group_id} 已推入队列，包含消息: {message_ids}")
    except asyncio.CancelledError:
        # 任务被取消是正常的（因为收到了新图片，需要重新计时）
        pass
    except Exception as e:
        logger.error(f"[收集器] 收集相册出错: {e}")

async def handle_forwarded_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
        
    media_group_id = message.media_group_id
    
    if media_group_id:
        # 如果是相册（媒体组）
        if media_group_id in media_groups:
            # 1. 取消上一次的计时任务（防抖：打断旧计时）
            old_task = media_groups[media_group_id]["task"]
            if old_task:
                old_task.cancel()
            
            # 2. 追加新的消息 ID
            media_groups[media_group_id]["messages"].append(message.message_id)
        else:
            # 第一次收到该相册的消息
            media_groups[media_group_id] = {
                "messages": [message.message_id],
                "task": None
            }
        
        # 3. 重新创建计时任务（防抖：重新开始计时 5.0 秒）
        task = asyncio.create_task(
            collect_media_group(media_group_id, chat.id, context.bot)
        )
        media_groups[media_group_id]["task"] = task
    else:
        # 如果是单张媒体，直接推入队列排队
        await send_queue.put({
            "type": "single",
            "chat_id": chat.id,
            "message_id": message.message_id,
            "bot": context.bot
        })
        logger.info(f"[收集器] 单张消息 {message.message_id} 已推入队列")

async def post_init(application) -> None:
    """在 Application 初始化后，自动在后台启动队列消费者协程"""
    asyncio.create_task(queue_worker())

def main():
    TOKEN = os.getenv("BOT_TOKEN")
    DOMAIN = os.getenv("BOT_DOMAIN")

    if not TOKEN:
        logger.error("请确保配置了环境变量 BOT_TOKEN")
        return

    if not DOMAIN:
        logger.error("请确保配置了环境变量 BOT_DOMAIN")
        return

    PORT = int(os.getenv("PORT", 23795))

    # 使用 post_init 钩子绑定后台工作协程
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    forwarded_media_filter = filters.FORWARDED & (
        filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE |
        filters.Document.ALL | filters.ANIMATION | filters.VIDEO_NOTE | filters.Sticker.ALL
    )
    application.add_handler(MessageHandler(forwarded_media_filter, handle_forwarded_media))

    logger.info(f"正在启动 Webhook 服务器，监听内部端口 {PORT}...")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://{DOMAIN}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
