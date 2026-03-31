import logging
from telegram import BotCommand
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


def main() -> None:
    # Ensure the Google Sheet has the correct header row
    logger.info("Initialising Google Sheet headers...")
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

    # Set Vietnamese command descriptions shown in Telegram menu
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


if __name__ == "__main__":
    main()
