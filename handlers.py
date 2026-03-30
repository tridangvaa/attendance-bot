import logging
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS, STAFF as STAFF_CONFIG
import sheets

logger = logging.getLogger(__name__)

# In-memory session cache: { telegram_id: {"name": str, "checkin": str, "row": int, "date": str} }
active_sessions: dict[int, dict] = {}

# Deduplication: track processed update_ids to ignore retries/duplicate deliveries
_processed_updates: set[int] = set()


def _get_staff() -> dict[int, str]:
    """Merge config.py staff with Google Sheet staff. Sheet entries take priority."""
    merged = dict(STAFF_CONFIG)
    merged.update(sheets.load_staff())
    return merged


_VN_TZ = timezone(timedelta(hours=7))


def _today() -> str:
    return datetime.now(_VN_TZ).strftime("%Y-%m-%d")


def _now_time() -> str:
    return datetime.now(_VN_TZ).strftime("%H:%M:%S")


# ── /start ────────────────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    staff = _get_staff()
    if user_id not in staff:
        await update.message.reply_text("❌ Bạn chưa được đăng ký. Vui lòng liên hệ quản trị viên.")
        return

    name = staff[user_id]
    await update.message.reply_text(
        f"👋 Xin chào, *{name}*!\n\n"
        "Các lệnh có thể sử dụng:\n"
        "  /checkin _[HH:MM]_  — Ghi nhận giờ vào\n"
        "  /checkout _[HH:MM]_ — Ghi nhận giờ ra\n"
        "  /status              — Xem trạng thái hôm nay\n"
        "  /report              — Báo cáo tổng hợp _(chỉ admin)_\n\n"
        "_Thời gian không bắt buộc. Nếu bỏ qua, hệ thống dùng giờ hiện tại._",
        parse_mode="Markdown",
    )


# ── /checkin ──────────────────────────────────────────────────────────────────

async def checkin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.update_id in _processed_updates:
        return
    _processed_updates.add(update.update_id)

    user_id = update.effective_user.id
    staff = _get_staff()
    if user_id not in staff:
        await update.message.reply_text("❌ Bạn chưa được đăng ký.")
        return

    name = staff[user_id]
    date_str = _today()

    # Block duplicate check-in — check memory first, then sheet (works across multiple instances)
    session = active_sessions.get(user_id)
    if session and session["date"] == date_str:
        await update.message.reply_text(
            f"⚠️ *{name}*, bạn đã chấm công vào lúc *{session['checkin']}* hôm nay rồi.",
            parse_mode="Markdown",
        )
        return
    existing_row = sheets.find_open_checkin(user_id, date_str)
    if existing_row is not None:
        sheet = sheets.get_sheet()
        existing_time = sheet.cell(existing_row, 4).value or "?"
        await update.message.reply_text(
            f"⚠️ *{name}*, bạn đã chấm công vào lúc *{existing_time}* hôm nay rồi.",
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
            await update.message.reply_text("❌ Định dạng giờ không hợp lệ. Dùng `/checkin HH:MM` hoặc `/checkin HH:MM:SS`.", parse_mode="Markdown")
            return
    else:
        time_str = _now_time()
    try:
        row_index = sheets.checkin_to_sheet(user_id, name, date_str, time_str)
    except Exception as e:
        logger.error("Sheet write error on check-in: %s", e)
        await update.message.reply_text("❌ Không thể ghi nhận giờ vào. Vui lòng thử lại.")
        return

    active_sessions[user_id] = {
        "name": name,
        "checkin": time_str,
        "row": row_index,
        "date": date_str,
    }

    await update.message.reply_text(
        f"✅ *Chấm công vào thành công!*\n"
        f"👤 Họ tên: {name}\n"
        f"📅 Ngày: {date_str}\n"
        f"🕐 Giờ vào: {time_str}",
        parse_mode="Markdown",
    )


# ── /checkout ─────────────────────────────────────────────────────────────────

async def checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.update_id in _processed_updates:
        return
    _processed_updates.add(update.update_id)

    user_id = update.effective_user.id
    staff = _get_staff()
    if user_id not in staff:
        await update.message.reply_text("❌ Bạn chưa được đăng ký.")
        return

    name = staff[user_id]
    date_str = _today()

    if sheets.find_completed_checkout(user_id, date_str):
        await update.message.reply_text(
            f"⚠️ *{name}*, bạn đã chấm công ra hôm nay rồi.",
            parse_mode="Markdown",
        )
        return

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
            await update.message.reply_text("❌ Định dạng giờ không hợp lệ. Dùng `/checkout HH:MM` hoặc `/checkout HH:MM:SS`.", parse_mode="Markdown")
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
                f"⚠️ *{name}*, bạn chưa chấm công vào hôm nay!",
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
        await update.message.reply_text("❌ Không thể ghi nhận giờ ra. Vui lòng thử lại.")
        return

    # Clear session
    active_sessions.pop(user_id, None)

    await update.message.reply_text(
        f"✅ *Chấm công ra thành công!*\n"
        f"👤 Họ tên: {name}\n"
        f"📅 Ngày: {date_str}\n"
        f"🕐 Giờ ra: {time_str}\n"
        f"⏱️ Thời gian làm việc: {duration}",
        parse_mode="Markdown",
    )


# ── /status ───────────────────────────────────────────────────────────────────

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    staff = _get_staff()
    if user_id not in staff:
        await update.message.reply_text("❌ Bạn chưa được đăng ký.")
        return

    name = staff[user_id]
    date_str = _today()
    session = active_sessions.get(user_id)

    if session and session["date"] == date_str:
        # Currently checked in
        now = datetime.strptime(_now_time(), "%H:%M:%S")  # already VN time via _now_time()
        start = datetime.strptime(session["checkin"], "%H:%M:%S")
        elapsed_min = int((now - start).total_seconds() // 60)
        hours, minutes = divmod(elapsed_min, 60)
        await update.message.reply_text(
            f"📊 *Trạng thái — {name}*\n"
            f"📅 Ngày: {date_str}\n"
            f"✅ Giờ vào: {session['checkin']}\n"
            f"⏳ Đã làm việc: {hours}h {minutes:02d}m",
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
                f"📊 *Trạng thái — {name}*\n"
                f"📅 Ngày: {date_str}\n"
                f"✅ Giờ vào: {user_record['Check-in Time']}\n"
                f"✅ Giờ ra: {user_record.get('Check-out Time') or '—'}\n"
                f"⏱️ Thời gian làm việc: {user_record.get('Duration') or '—'}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"📊 *{name}* — Chưa có dữ liệu chấm công hôm nay ({date_str}).",
                parse_mode="Markdown",
            )


# ── /report (admin only) ──────────────────────────────────────────────────────

async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Lệnh này chỉ dành cho quản trị viên.")
        return

    # Optional: /report 2024-06-01 — default to today
    args = context.args
    date_str = args[0] if args else _today()

    try:
        records = sheets.get_report(date_str)
    except Exception as e:
        logger.error("Sheet read error on report: %s", e)
        await update.message.reply_text("❌ Không thể lấy báo cáo.")
        return

    if not records:
        await update.message.reply_text(f"📊 Không có dữ liệu chấm công cho ngày *{date_str}*.", parse_mode="Markdown")
        return

    lines = [f"📊 *Báo cáo chấm công — {date_str}*", ""]
    for r in records:
        checkin = r.get("Check-in Time") or "—"
        checkout = r.get("Check-out Time") or "⏳ Chưa ra"
        duration = r.get("Duration") or "—"
        lines.append(f"👤 *{r.get('Staff Name')}*")
        lines.append(f"   Vào: {checkin}  |  Ra: {checkout}  |  {duration}")

    lines.append(f"\nTổng có mặt: {len(records)}/{len(_get_staff())}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /addstaff (admin only) ────────────────────────────────────────────────────

async def addstaff_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Lệnh này chỉ dành cho quản trị viên.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Cách dùng: `/addstaff <telegram_id> <họ tên>`\nVí dụ: `/addstaff 123456789 Nguyen Van A`",
            parse_mode="Markdown",
        )
        return

    try:
        new_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Telegram ID phải là số.")
        return

    name = " ".join(context.args[1:])
    sheets.add_staff(new_id, name)
    await update.message.reply_text(f"✅ Đã thêm nhân viên: *{name}* (`{new_id}`)", parse_mode="Markdown")


# ── /removestaff (admin only) ─────────────────────────────────────────────────

async def removestaff_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Lệnh này chỉ dành cho quản trị viên.")
        return

    if not context.args:
        await update.message.reply_text(
            "Cách dùng: `/removestaff <telegram_id>`",
            parse_mode="Markdown",
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Telegram ID phải là số.")
        return

    removed = sheets.remove_staff(target_id)
    if removed:
        await update.message.reply_text(f"✅ Đã xóa nhân viên có ID `{target_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Không tìm thấy nhân viên có ID `{target_id}`.", parse_mode="Markdown")


# ── /liststaff (admin only) ───────────────────────────────────────────────────

async def liststaff_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Lệnh này chỉ dành cho quản trị viên.")
        return

    staff = _get_staff()
    if not staff:
        await update.message.reply_text("Chưa có nhân viên nào được đăng ký.")
        return

    lines = ["👥 *Danh sách nhân viên*", ""]
    for tid, name in staff.items():
        lines.append(f"• {name} — `{tid}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
