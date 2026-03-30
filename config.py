import os
from dotenv import load_dotenv

load_dotenv()  # no-op on Railway (no .env file); loads local .env for dev

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Attendance")
# On Railway, set GOOGLE_CREDENTIALS_JSON to the full credentials JSON string.
# Locally, GOOGLE_CREDENTIALS_FILE can point to a credentials.json file.
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Admin IDs — comma-separated in .env, e.g. ADMIN_IDS=111222333,444555666
_admin_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {int(x.strip()) for x in _admin_raw.split(",") if x.strip()}

# ── Manual Staff List ─────────────────────────────────────────────────────────
# Add staff here as a fallback. Staff added via /addstaff (Google Sheet) will
# be merged on top — sheet entries take priority over entries here.
STAFF: dict[int, str] = {
    1989406520: "Vu Thi Thom",
    8654360346: "Lam Tinh Nhi",
    6441061958: "Nguyen Trung Hieu",
    8636974699: "Tran Hoai Truc Linh",
    1496096197: "Ho Tri Dang",
}

SHEET_HEADERS = ["Date", "Staff Name", "Telegram ID", "Check-in Time", "Check-out Time", "Duration"]
