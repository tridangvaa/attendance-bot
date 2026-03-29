import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import STAFF, ADMIN_IDS
import sheets

logger = logging.getLogger(__name__)

# In-memory session cache: { telegram_id: {"name": str, "checkin": str, "row": int, "date": str} }
active_sessions: dict[int, dict] = {}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── /start ────────────────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in STAFF:
        await update.message.reply_text("❌ You are not registered. Contact your admin.")
        return

    name = STAFF[user_id]
    await update.message.reply_text(
        f"👋 Hello, *{name}*!\n\n"
        "Available commands:\n"
        "  /checkin _[HH:MM]_  — Record your arrival\n"
        "  /checkout _[HH:MM]_ — Record your departure\n"
        "  /status              — View your status today\n"
        "  /report              — Today's full report _(admin only)_\n\n"
        "_Time is optional. If omitted, current time is used._",
        parse_mode="Markdown",
    )


# ── /checkin ──────────────────────────────────────────────────────────────────

async def checkin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in STAFF:
        await update.message.reply_text("❌ You are not registered.")
        return

    name = STAFF[user_id]
    date_str = _today()

    # Block duplicate check-in
    session = active_sessions.get(user_id)
    if session and session["date"] == date_str:
        await update.message.reply_text(
            f"⚠️ *{name}*, you already checked in at *{session['checkin']}* today.",
            parse_mode="Markdown",
        )
        return

    # Accept optional time argument: /checkin 08:30 or /checkin 08:30:00
    if context.args:
        raw = context.args[0]
        try:
            if len(raw) == 5:  # HH:MM
                datetime.strptime(raw, "%H:%M")
                time_str = raw + ":00"
            else:  # HH:MM:SS
                datetime.strptime(raw, "%H:%M:%S")
                time_str = raw
        except ValueError:
            await update.message.reply_text("❌ Invalid time format. Use `/checkin HH:MM` or `/checkin HH:MM:SS`.", parse_mode="Markdown")
            return
    else:
        time_str = _now_time()
    try:
        row_index = sheets.checkin_to_sheet(user_id, name, date_str, time_str)
    except Exception as e:
        logger.error("Sheet write error on check-in: %s", e)
        await update.message.reply_text("❌ Failed to record check-in. Try again.")
        return

    active_sessions[user_id] = {
        "name": name,
        "checkin": time_str,
        "row": row_index,
        "date": date_str,
    }

    await update.message.reply_text(
        f"✅ *Check-in recorded!*\n"
        f"👤 Name: {name}\n"
        f"📅 Date: {date_str}\n"
        f"🕐 Time: {time_str}",
        parse_mode="Markdown",
    )


# ── /checkout ─────────────────────────────────────────────────────────────────

async def checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in STAFF:
        await update.message.reply_text("❌ You are not registered.")
        return

    name = STAFF[user_id]
    date_str = _today()

    # Accept optional time argument: /checkout 17:30 or /checkout 17:30:00
    if context.args:
        raw = context.args[0]
        try:
            if len(raw) == 5:  # HH:MM
                datetime.strptime(raw, "%H:%M")
                time_str = raw + ":00"
            else:  # HH:MM:SS
                datetime.strptime(raw, "%H:%M:%S")
                time_str = raw
        except ValueError:
            await update.message.reply_text("❌ Invalid time format. Use `/checkout HH:MM` or `/checkout HH:MM:SS`.", parse_mode="Markdown")
            return
    else:
        time_str = _now_time()

    # Resolve row from cache or fall back to sheet scan (after bot restart)
    session = active_sessions.get(user_id)
    if session and session["date"] == date_str:
        row_index = session["row"]
        checkin_time = session["checkin"]
    else:
        row_index = sheets.find_open_checkin(user_id, date_str)
        if row_index is None:
            await update.message.reply_text(
                f"⚠️ *{name}*, you haven't checked in today yet!",
                parse_mode="Markdown",
            )
            return
        # Rebuild checkin time from sheet
        sheet = sheets.get_sheet()
        checkin_time = sheet.cell(row_index, 4).value or "00:00:00"

    duration = sheets._calc_duration(checkin_time, time_str)

    try:
        sheets.checkout_to_sheet(row_index, time_str, duration)
    except Exception as e:
        logger.error("Sheet write error on check-out: %s", e)
        await update.message.reply_text("❌ Failed to record check-out. Try again.")
        return

    # Clear session
    active_sessions.pop(user_id, None)

    await update.message.reply_text(
        f"✅ *Check-out recorded!*\n"
        f"👤 Name: {name}\n"
        f"📅 Date: {date_str}\n"
        f"🕐 Time: {time_str}\n"
        f"⏱️ Duration: {duration}",
        parse_mode="Markdown",
    )


# ── /status ───────────────────────────────────────────────────────────────────

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in STAFF:
        await update.message.reply_text("❌ You are not registered.")
        return

    name = STAFF[user_id]
    date_str = _today()
    session = active_sessions.get(user_id)

    if session and session["date"] == date_str:
        # Currently checked in
        now = datetime.strptime(_now_time(), "%H:%M:%S")
        start = datetime.strptime(session["checkin"], "%H:%M:%S")
        elapsed_min = int((now - start).total_seconds() // 60)
        hours, minutes = divmod(elapsed_min, 60)
        await update.message.reply_text(
            f"📊 *Status — {name}*\n"
            f"📅 Date: {date_str}\n"
            f"✅ Checked in at: {session['checkin']}\n"
            f"⏳ Time so far: {hours}h {minutes:02d}m",
            parse_mode="Markdown",
        )
    else:
        # Check sheet for completed record
        try:
            records = sheets.get_report(date_str)
            user_record = next((r for r in records if str(r.get("Telegram ID")) == str(user_id)), None)
        except Exception:
            user_record = None

        if user_record and user_record.get("Check-in Time"):
            await update.message.reply_text(
                f"📊 *Status — {name}*\n"
                f"📅 Date: {date_str}\n"
                f"✅ Check-in: {user_record['Check-in Time']}\n"
                f"✅ Check-out: {user_record.get('Check-out Time') or '—'}\n"
                f"⏱️ Duration: {user_record.get('Duration') or '—'}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"📊 *{name}* — No attendance record for today ({date_str}).",
                parse_mode="Markdown",
            )


# ── /report (admin only) ──────────────────────────────────────────────────────

async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ This command is for admins only.")
        return

    # Optional: /report 2024-06-01 — default to today
    args = context.args
    date_str = args[0] if args else _today()

    try:
        records = sheets.get_report(date_str)
    except Exception as e:
        logger.error("Sheet read error on report: %s", e)
        await update.message.reply_text("❌ Failed to fetch report.")
        return

    if not records:
        await update.message.reply_text(f"📊 No attendance records for *{date_str}*.", parse_mode="Markdown")
        return

    lines = [f"📊 *Attendance Report — {date_str}*", ""]
    for r in records:
        checkin = r.get("Check-in Time") or "—"
        checkout = r.get("Check-out Time") or "⏳ In"
        duration = r.get("Duration") or "—"
        lines.append(f"👤 *{r.get('Staff Name')}*")
        lines.append(f"   In: {checkin}  |  Out: {checkout}  |  {duration}")

    lines.append(f"\nTotal present: {len(records)}/{len(STAFF)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
