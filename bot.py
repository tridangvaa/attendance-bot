import asyncio
import logging
import sys
import time
from telegram import BotCommand
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start_handler, checkin_handler, checkout_handler,
    status_handler, report_handler,
    addstaff_handler, removestaff_handler, liststaff_handler,
)
import sheets

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _error_handler(update, context) -> None:
    if isinstance(context.error, Conflict):
        logger.error("409 Conflict — another instance is running. Exiting so the process manager can restart.")
        sys.exit(1)
    logger.error("Unhandled exception", exc_info=context.error)


def _run_once() -> None:
    sheets.ensure_headers()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",        start_handler))
    app.add_handler(CommandHandler("checkin",      checkin_handler))
    app.add_handler(CommandHandler("checkout",     checkout_handler))
    app.add_handler(CommandHandler("status",       status_handler))
    app.add_handler(CommandHandler("report",       report_handler))
    app.add_handler(CommandHandler("addstaff",     addstaff_handler))
    app.add_handler(CommandHandler("removestaff",  removestaff_handler))
    app.add_handler(CommandHandler("liststaff",    liststaff_handler))
    app.add_error_handler(_error_handler)

    async def set_commands(app: Application) -> None:
        await app.bot.set_my_commands([
            BotCommand("start",       "Bắt đầu / xem hướng dẫn"),
            BotCommand("checkin",     "Chấm công vào [HH:MM]"),
            BotCommand("checkout",    "Chấm công ra [HH:MM]"),
            BotCommand("status",      "Xem trạng thái hôm nay"),
            BotCommand("report",      "Báo cáo chấm công (admin)"),
            BotCommand("addstaff",    "Thêm nhân viên (admin)"),
            BotCommand("removestaff", "Xóa nhân viên (admin)"),
            BotCommand("liststaff",   "Danh sách nhân viên (admin)"),
        ])

    app.post_init = set_commands

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


def main() -> None:
    logger.info("Initialising Google Sheet headers...")
    while True:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            _run_once()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped.")
            break
        except Exception as e:
            logger.error("Bot crashed: %s — restarting in 10s", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
