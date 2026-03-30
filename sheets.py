import gspread
import json
import os
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import Optional
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, GOOGLE_SHEET_NAME, SHEET_HEADERS

STAFF_SHEET_NAME = "Staff"
STAFF_HEADERS = ["Telegram ID", "Name"]

DEDUP_SHEET_NAME = "ProcessedUpdates"

_client: Optional[gspread.Client] = None


def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
        else:
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
        _client = gspread.authorize(creds)
    return _client


def get_sheet() -> gspread.Worksheet:
    return _get_client().open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_NAME)


def _get_staff_sheet() -> gspread.Worksheet:
    spreadsheet = _get_client().open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = spreadsheet.worksheet(STAFF_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=STAFF_SHEET_NAME, rows=100, cols=2)
        ws.append_row(STAFF_HEADERS)
    return ws


def _get_dedup_sheet() -> gspread.Worksheet:
    spreadsheet = _get_client().open_by_key(GOOGLE_SHEET_ID)
    try:
        return spreadsheet.worksheet(DEDUP_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=DEDUP_SHEET_NAME, rows=1000, cols=1)
        ws.append_row(["Update ID"])
        return ws


def claim_update(update_id: int) -> bool:
    """
    Claim an update_id in the shared ProcessedUpdates sheet.
    Returns True if this call is the first to claim it (safe to process).
    Returns False if another instance already claimed it (skip processing).
    """
    ws = _get_dedup_sheet()
    all_ids = ws.col_values(1)[1:]  # skip header — read BEFORE appending
    if str(update_id) in all_ids:
        return False
    ws.append_row([str(update_id)])
    return True


def ensure_headers() -> None:
    sheet = get_sheet()
    if sheet.row_values(1) != SHEET_HEADERS:
        sheet.insert_row(SHEET_HEADERS, index=1)
    # Also ensure staff sheet exists
    _get_staff_sheet()


def load_staff() -> dict[int, str]:
    """Load all staff from the Staff sheet. Returns {telegram_id: name}."""
    ws = _get_staff_sheet()
    records = ws.get_all_records()
    return {int(r["Telegram ID"]): str(r["Name"]) for r in records if r.get("Telegram ID")}


def add_staff(telegram_id: int, name: str) -> None:
    """Add a staff member to the Staff sheet."""
    ws = _get_staff_sheet()
    # Update if already exists, otherwise append
    records = ws.get_all_values()
    for i, row in enumerate(records[1:], start=2):
        if row and str(row[0]) == str(telegram_id):
            ws.update_cell(i, 2, name)
            return
    ws.append_row([str(telegram_id), name])


def remove_staff(telegram_id: int) -> bool:
    """Remove a staff member by Telegram ID. Returns True if found and removed."""
    ws = _get_staff_sheet()
    records = ws.get_all_values()
    for i, row in enumerate(records[1:], start=2):
        if row and str(row[0]) == str(telegram_id):
            ws.delete_rows(i)
            return True
    return False


def checkin_to_sheet(user_id: int, name: str, date_str: str, time_str: str) -> int:
    """Append a new check-in row. Returns the 1-based row index of the new row."""
    sheet = get_sheet()
    sheet.append_row([date_str, name, str(user_id), time_str, "", ""])
    return len(sheet.get_all_values())  # last row = the one just appended


def checkout_to_sheet(row_index: int, checkout_time: str, duration: str) -> None:
    """Update check-out time and duration for an existing row."""
    sheet = get_sheet()
    sheet.update_cell(row_index, 5, checkout_time)   # E = Check-out Time
    sheet.update_cell(row_index, 6, duration)         # F = Duration


def find_completed_checkout(user_id: int, date_str: str) -> bool:
    """Return True if the user already has a completed checkout today."""
    sheet = get_sheet()
    rows = sheet.get_all_values()
    for row in rows[1:]:
        if len(row) >= 5 and row[2] == str(user_id) and row[0] == date_str and row[4]:
            return True
    return False


def find_open_checkin(user_id: int, date_str: str) -> Optional[int]:
    """
    Fallback scan used after a bot restart.
    Returns the 1-based row index of today's open check-in for user_id, or None.
    """
    sheet = get_sheet()
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):   # skip header
        if len(row) >= 4 and row[2] == str(user_id) and row[0] == date_str:
            checkout_col = row[4] if len(row) > 4 else ""
            if not checkout_col:
                return i
    return None


def get_report(date_str: str) -> list[dict]:
    """Return all attendance rows for a given date as a list of dicts."""
    sheet = get_sheet()
    records = sheet.get_all_records()   # uses row 1 as header keys
    return [r for r in records if r.get("Date") == date_str]


def _calc_duration(checkin_str: str, checkout_str: str) -> str:
    fmt = "%H:%M:%S"
    try:
        delta = datetime.strptime(checkout_str, fmt) - datetime.strptime(checkin_str, fmt)
        total_minutes = int(delta.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes:02d}m"
    except ValueError:
        return "N/A"
