import os
import json
from datetime import datetime, timedelta

import telegram
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import pandas as pd

# ── SETTINGS ───────────────────────────────────────────────────────────────────
# 1) Put your BotFather token here (STRING!)
BOT_TOKEN = "8353412354:AAH2EG1nIZR-4Nag1DmZbzpN6Ca9-q5kdeE"

# 2) Put your own Telegram numeric user ID here (manager can use /teamreport, /export)
#    Tip to get it: message @userinfobot or run this bot and read update.effective_user.id
MANAGER_ID = "123456789"
DATA_FILE = "attendance_data.json"
# ───────────────────────────────────────────────────────────────────────────────

def load_data():
    """Load attendance data from JSON; return {} if missing/invalid."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    """Save attendance data to JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_manager(user_id: str) -> bool:
    """Check if the caller is the designated manager (compare as string)."""
    return str(user_id) == str(MANAGER_ID)

def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your work hour tracker bot.\n"
        "Use /clockin to start and /clockout to end.\n"
        "You can also use /myhours and /myreport."
    )

def clock_in(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()
    now_iso = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    if user_id not in data:
        data[user_id] = {"name": update.effective_user.full_name, "sessions": []}

    last = data[user_id]["sessions"][-1] if data[user_id]["sessions"] else None
    if last and last["date"] == today and last.get("end_time") is None:
        update.message.reply_text("You are already clocked in.")
        return

    data[user_id]["sessions"].append(
        {"date": today, "start_time": now_iso, "end_time": None}
    )
    save_data(data)
    update.message.reply_text("✅ Clocked in. Have a great shift!")

def clock_out(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id not in data or not data[user_id]["sessions"]:
        update.message.reply_text("You haven't clocked in yet.")
        return

    last = data[user_id]["sessions"][-1]
    if last.get("end_time") is not None:
        update.message.reply_text("You are already clocked out.")
        return

    now = datetime.now()
    start_dt = datetime.fromisoformat(last["start_time"])
    duration = now - start_dt

    last["end_time"] = now.isoformat()
    last["duration_minutes"] = int(duration.total_seconds() / 60)
    save_data(data)

    hours = last["duration_minutes"] // 60
    minutes = last["duration_minutes"] % 60
    update.message.reply_text(f"🕘 Clocked out. Worked {hours}h {minutes}m.")

def get_daily_minutes(user_id: str, date_str: str, data: dict) -> int:
    total = 0
    if user_id in data:
        for s in data[user_id]["sessions"]:
            if s["date"] == date_str and "duration_minutes" in s:
                total += int(s["duration_minutes"])
    return total

def my_hours(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    total = get_daily_minutes(user_id, today, data)

    if total > 0:
        update.message.reply_text(f"Today: {total//60}h {total%60}m.")
    else:
        update.message.reply_text("No work hours recorded today yet.")

def my_report(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id not in data:
        update.message.reply_text("No work hours recorded for you yet.")
        return

    lines = ["*Your Work Report (Last 7 Days):*\n"]
    today = datetime.now().date()
    has_any = False

    for i in range(7):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        total = get_daily_minutes(user_id, ds, data)
        if total > 0:
            has_any = True
            lines.append(f"- {ds}: {total//60}h {total%60}m")

    if not has_any:
        lines.append("No hours recorded in the last 7 days.")

    update.message.reply_text("\n".join(lines), parse_mode=telegram.ParseMode.MARKDOWN)

def team_report(update: Update, context: CallbackContext) -> None:
    caller = str(update.effective_user.id)
    if not is_manager(caller):
        update.message.reply_text("You are not authorized to use this command.")
        return

    data = load_data()
    today = datetime.now().date()
    lines = ["*Team Work Report (Last 7 Days):*\n"]
    has_any = False

    for uid, udata in data.items():
        name = udata.get("name", uid)
        total_week = 0
        for i in range(7):
            ds = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            total_week += get_daily_minutes(uid, ds, data)
        if total_week > 0:
            has_any = True
            lines.append(f"- {name}: {total_week//60}h {total_week%60}m")

    if not has_any:
        lines.append("No hours recorded for the team in the last 7 days.")

    update.message.reply_text("\n".join(lines), parse_mode=telegram.ParseMode.MARKDOWN)

def export_report(update: Update, context: CallbackContext) -> None:
    caller = str(update.effective_user.id)
    if not is_manager(caller):
        update.message.reply_text("You are not authorized to use this command.")
        return

    data = load_data()
    records = []
    for uid, udata in data.items():
        name = udata.get("name", uid)
        for s in udata.get("sessions", []):
            if s.get("end_time"):
                start = datetime.fromisoformat(s["start_time"])
                end = datetime.fromisoformat(s["end_time"])
                records.append({
                    "Employee Name": name,
                    "Date": s["date"],
                    "Clock In": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "Clock Out": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "Duration (hours)": round((end - start).total_seconds()/3600, 2),
                })

    if not records:
        update.message.reply_text("No finished sessions to export.")
        return

    df = pd.DataFrame(records)
    csv_path = "attendance_report.csv"
    df.to_csv(csv_path, index=False)

    with open(csv_path, "rb") as f:
        update.message.reply_document(document=f, filename=csv_path,
                                      caption="Your detailed attendance report.")
    os.remove(csv_path)

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("clockin", clock_in))
    dp.add_handler(CommandHandler("clockout", clock_out))
    dp.add_handler(CommandHandler("myhours", my_hours))
    dp.add_handler(CommandHandler("myreport", my_report))
    dp.add_handler(CommandHandler("teamreport", team_report))
    dp.add_handler(CommandHandler("export", export_report))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()