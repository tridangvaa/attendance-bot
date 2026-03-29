import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Attendance")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Admin IDs — comma-separated in .env, e.g. ADMIN_IDS=111222333,444555666
_admin_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {int(x.strip()) for x in _admin_raw.split(",") if x.strip()}

# ── 15 Staff Members ──────────────────────────────────────────────────────────
# Replace the numeric keys with each staff member's real Telegram user ID.
# To find a Telegram user ID, have them message @userinfobot.
STAFF: dict[int, str] = {
    1989406520: "Vu Thi Thom",
    100000002: "Tran Thi B",
    100000003: "Le Van C",
    100000004: "Pham Thi D",
    100000005: "Hoang Van E",
    100000006: "Vu Thi F",
    100000007: "Dang Van G",
    100000008: "Bui Thi H",
    100000009: "Do Van I",
    100000010: "Ngo Thi J",
    100000011: "Ly Van K",
    100000012: "Dinh Thi L",
    100000013: "Trinh Van M",
    100000014: "Mai Thi N",
    100000015: "Cao Van O",
}

SHEET_HEADERS = ["Date", "Staff Name", "Telegram ID", "Check-in Time", "Check-out Time", "Duration"]
