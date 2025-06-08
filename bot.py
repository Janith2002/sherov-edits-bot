import os
import json
import logging
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import subprocess

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5384570436"))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track user usage and premium
DATA_FILE = "users.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_premium(user_id):
    data = load_data()
    user = data.get(str(user_id), {})
    if user.get("is_admin"):
        return True
    if "premium_until" in user:
        return datetime.now() < datetime.strptime(user["premium_until"], "%Y-%m-%d")
    return False

def update_usage(user_id):
    data = load_data()
    user = data.setdefault(str(user_id), {"uses": 0})
    user["uses"] = user.get("uses", 0) + 1
    save_data(data)

def get_usage(user_id):
    data = load_data()
    return data.get(str(user_id), {}).get("uses", 0)

def set_premium(user_id, days=14):
    data = load_data()
    user = data.setdefault(str(user_id), {})
    until = datetime.now() + timedelta(days=days)
    user["premium_until"] = until.strftime("%Y-%m-%d")
    save_data(data)

def mark_admin(user_id):
    data = load_data()
    user = data.setdefault(str(user_id), {})
    user["is_admin"] = True
    save_data(data)

# File saving paths
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)
sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to Sherov Edits Bot!

Send a photo/video and a song, and I’ll create a video with watermark (3 free edits).
After that, $1 to unlock 14 days of premium (no watermark).

/binance ID: 1077785527")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start - Welcome message
/stats - Admin only
Send media + audio to edit!")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("Unauthorized.")
    data = load_data()
    text = "\n".join([f"{uid}: {info}" for uid, info in data.items()])
    await update.message.reply_text(f"📊 Usage Stats:\n{text}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in sessions:
        sessions[user_id] = {}

    file = update.message.video or update.message.photo[-1] or update.message.document or update.message.audio
    if not file:
        return await update.message.reply_text("❌ Unsupported file type.")

    file_type = "audio" if file.mime_type and "audio" in file.mime_type else "media"
    file_path = f"{MEDIA_DIR}/{user_id}_{file_type}_{datetime.now().timestamp()}.mp4" if file_type == "media" else f"{MEDIA_DIR}/{user_id}_{file_type}.mp3"
    file_obj = await file.get_file()
    await file_obj.download_to_drive(file_path)
    sessions[user_id][file_type] = file_path

    if "media" in sessions[user_id] and "audio" in sessions[user_id]:
        await update.message.reply_text("🎬 Processing your video...")
        await process_and_send(user_id, update, context)

async def process_and_send(user_id, update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = sessions[user_id]
    input_video = session["media"]
    input_audio = session["audio"]
    output = f"{MEDIA_DIR}/{user_id}_final_{datetime.now().timestamp()}.mp4"

    watermark = not is_premium(user_id)
    watermark_text = "Sherov Edits"

    cmd = [
        "ffmpeg", "-y", "-i", input_video, "-i", input_audio,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "aac", "-shortest"
    ]

    if watermark:
        cmd += ["-vf", f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:x=10:y=10"]

    cmd += [output]
    subprocess.run(cmd)

    await update.message.reply_video(InputFile(output))

    update_usage(user_id)
    usage = get_usage(user_id)
    if not is_premium(user_id) and usage >= 3:
        await update.message.reply_text("⚠️ You've used 3 free edits. Send $1 to Binance ID: 1077785527 to unlock 14 days premium.")

    sessions.pop(user_id, None)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    mark_admin(ADMIN_ID)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.ALL, handle_file))

    print("🤖 Sherov Edits Bot is running...")
    app.run_polling()
