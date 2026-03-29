import logging
from telegram.ext import Application, CommandHandler
from config import TELEGRAM_BOT_TOKEN
from handlers import start_handler, checkin_handler, checkout_handler, status_handler, report_handler
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

    app.add_handler(CommandHandler("start",    start_handler))
    app.add_handler(CommandHandler("checkin",  checkin_handler))
    app.add_handler(CommandHandler("checkout", checkout_handler))
    app.add_handler(CommandHandler("status",   status_handler))
    app.add_handler(CommandHandler("report",   report_handler))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
