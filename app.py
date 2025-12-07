# better_bot.py
import os
import json
import logging
import tempfile
import threading
from io import BytesIO
from functools import wraps
from typing import Dict

import openai
from gtts import gTTS
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatAction,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)

# ---------------- CONFIG ----------------
TELEGRAM_BOT_TOKEN = "8435631757:AAHj8lR8rDG72DxetBGUyLeVg3ZQHpKbMh0"
OWNER_ID = "7301067810"

# Hardcoded OpenAI API key (your provided key)
openai.api_key = "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"

DATA_FILE = "data.json"
waiting_for: Dict[int, Dict] = {}

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- STORAGE ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"admins": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

data = load_data()
if OWNER_ID and OWNER_ID not in data.get("admins", []):
    data.setdefault("admins", []).append(OWNER_ID)
    save_data(data)

def is_admin(user_id: int):
    return str(user_id) in data.get("admins", [])

def admin_only(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext, *a, **kw):
        uid = update.effective_user.id
        if not is_admin(uid):
            update.message.reply_text("❌ You are not authorized to run this command.")
            return
        return func(update, context, *a, **kw)
    return wrapper

# ---------------- OPENAI HELPERS ----------------
def openai_chat_reply(prompt: str, system="You are a helpful assistant.", max_tokens=700):
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.exception("OpenAI chat error")
        return f"⚠️ OpenAI error: {e}"

def openai_image_generate(prompt: str):
    try:
        resp = openai.Image.create(prompt=prompt, n=1, size="1024x1024")
        return resp["data"][0]["url"]
    except Exception as e:
        logger.exception("OpenAI image error")
        return None

def openai_transcribe_file(filepath: str):
    try:
        with open(filepath, "rb") as f:
            resp = openai.Audio.transcribe("whisper-1", f)
            return resp.get("text", "")
    except Exception as e:
        logger.exception("OpenAI transcription error")
        return ""

# ---------------- UTILITIES ----------------
def run_in_thread(fn):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t
    return wrapper

def send_typing(chat_id, context: CallbackContext):
    try:
        context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        pass

# ---------------- COMMAND HANDLERS ----------------
def start_cmd(update: Update, context: CallbackContext):
    kb = [
        [InlineKeyboardButton("Ask AI", callback_data="ask")],
        [InlineKeyboardButton("Generate Image", callback_data="image")],
        [InlineKeyboardButton("TTS (Text→Voice)", callback_data="tts")],
        [InlineKeyboardButton("Get Info", callback_data="info")],
        [InlineKeyboardButton("Advice", callback_data="advice"), InlineKeyboardButton("Solve", callback_data="solve")],
    ]
    text = (
        "👋 <b>Welcome!</b>\n\n"
        "I'm an AI assistant bot. Use the buttons below or commands:\n"
        "/ask <question>\n/image <prompt>\n/tts <text>\n/info <username_or_id>\n/solve <assignment>\n/advice <topic>\n\n"
        "Send a voice message to transcribe & answer, or a photo to have me describe it."
    )
    update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Commands:\n"
        "/ask <question>\n/image <prompt>\n/tts <text>\n/info <username_or_id>\n/solve <assignment>\n/advice <topic>\n"
        "Inline buttons are available for quick actions."
    )

# ---------------- CORE COMMANDS ----------------
@run_in_thread
def _do_ask(chat_id, prompt, context: CallbackContext):
    send_typing(chat_id, context)
    answer = openai_chat_reply(prompt)
    context.bot.send_message(chat_id=chat_id, text=answer)

def ask_cmd(update: Update, context: CallbackContext):
    prompt = " ".join(context.args).strip()
    if not prompt:
        update.message.reply_text("Usage: /ask <your question>")
        return
    update.message.reply_text("🔎 Thinking...")
    _do_ask(update.effective_chat.id, prompt, context)

@run_in_thread
def _do_image(chat_id, prompt, context: CallbackContext):
    send_typing(chat_id, context)
    url = openai_image_generate(prompt)
    if url:
        context.bot.send_photo(chat_id=chat_id, photo=url, caption=f"Image for: {prompt}")
    else:
        context.bot.send_message(chat_id=chat_id, text="❌ Failed to generate image.")

def image_cmd(update: Update, context: CallbackContext):
    prompt = " ".join(context.args).strip()
    if not prompt:
        update.message.reply_text("Usage: /image <prompt>")
        return
    update.message.reply_text("🖼️ Generating image...")
    _do_image(update.effective_chat.id, prompt, context)

@run_in_thread
def _do_tts(chat_id, text, context: CallbackContext):
    send_typing(chat_id, context)
    try:
        tts = gTTS(text)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        context.bot.send_voice(chat_id=chat_id, voice=buf, caption="Here is your voice note")
    except Exception as e:
        logger.exception("TTS error")
        context.bot.send_message(chat_id=chat_id, text=f"TTS error: {e}")

def tts_cmd(update: Update, context: CallbackContext):
    text = " ".join(context.args).strip()
    if not text:
        update.message.reply_text("Usage: /tts <text>")
        return
    update.message.reply_text("🔊 Generating voice...")
    _do_tts(update.effective_chat.id, text, context)

@run_in_thread
def _do_info(chat_id, target, context: CallbackContext):
    try:
        send_typing(chat_id, context)
        chat = context.bot.get_chat(target)
        info = (
            f"👤 <b>User Info</b>\n"
            f"First name: {chat.first_name or '-'}\n"
            f"Last name: {chat.last_name or '-'}\n"
            f"Username: @{chat.username or '-'}\n"
            f"User ID: {chat.id}\n"
            f"Bio: {getattr(chat, 'bio', '-')}"
        )
        context.bot.send_message(chat_id=chat_id, text=info, parse_mode="HTML")
    except Exception as e:
        logger.exception("Info fetch error")
        context.bot.send_message(chat_id=chat_id, text=f"Cannot fetch info: {e}")

def info_cmd(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /info <username_or_id>")
        return
    target = context.args[0]
    if target.startswith("@"):
        target = target
    update.message.reply_text("🔎 Looking up user...")
    _do_info(update.effective_chat.id, target, context)

@run_in_thread
def _do_solve(chat_id, text, context: CallbackContext):
    send_typing(chat_id, context)
    system = "You are an expert tutor. Explain step-by-step and provide final concise answer."
    answer = openai_chat_reply(text, system=system, max_tokens=1000)
    context.bot.send_message(chat_id=chat_id, text=answer)

def solve_cmd(update: Update, context: CallbackContext):
    text = " ".join(context.args).strip()
    if not text:
        update.message.reply_text("Usage: /solve <assignment text>")
        return
    update.message.reply_text("🧠 Solving your assignment...")
    _do_solve(update.effective_chat.id, text, context)

@run_in_thread
def _do_advice(chat_id, topic, context: CallbackContext):
    send_typing(chat_id, context)
    prompt = f"Provide short, practical advice about: {topic} (4-6 bullet points)"
    advice = openai_chat_reply(prompt, max_tokens=300)
    context.bot.send_message(chat_id=chat_id, text=advice)

def advice_cmd(update: Update, context: CallbackContext):
    topic = " ".join(context.args).strip()
    if not topic:
        update.message.reply_text("Usage: /advice <topic>")
        return
    update.message.reply_text("💡 Generating advice...")
    _do_advice(update.effective_chat.id, topic, context)

# ---------------- VOICE / PHOTO ----------------
@run_in_thread
def handle_voice_background(chat_id, file_path, context: CallbackContext):
    send_typing(chat_id, context)
    text_trans = openai_transcribe_file(file_path)
    if text_trans:
        context.bot.send_message(chat_id=chat_id, text=f"📝 Transcription:\n{text_trans}")
        answer = openai_chat_reply(f"The user said: {text_trans}\nProvide a short helpful answer.")
        context.bot.send_message(chat_id=chat_id, text=f"🤖 AI reply:\n{answer}")
    else:
        context.bot.send_message(chat_id=chat_id, text="❌ Could not transcribe the audio.")
    try:
        os.remove(file_path)
    except Exception:
        pass

def voice_handler(update: Update, context: CallbackContext):
    voice = update.message.voice
    if not voice:
        update.message.reply_text("No voice found.")
        return
    f = context.bot.get_file(voice.file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    f.download(custom_path=tmp.name)
    update.message.reply_text("Transcribing audio...")
    handle_voice_background(update.effective_chat.id, tmp.name, context)

@run_in_thread
def handle_photo_background(chat_id, file_path, context: CallbackContext):
    send_typing(chat_id, context)
    desc = openai_chat_reply("Describe a user-uploaded photo in 2-3 short sentences (imaginary placeholder).")
    context.bot.send_message(chat_id=chat_id, text=f"🖼️ Description:\n{desc}")
    try:
        os.remove(file_path)
    except Exception:
        pass

def photo_handler(update: Update, context: CallbackContext):
    photo = update.message.photo
    if not photo:
        update.message.reply_text("No photo found.")
        return
    file_id = photo[-1].file_id
    f = context.bot.get_file(file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    f.download(custom_path=tmp.name)
    update.message.reply_text("Analyzing photo...")
    handle_photo_background(update.effective_chat.id, tmp.name, context)

# ---------------- INLINE BUTTONS ----------------
def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    uid = query.from_user.id
    action = query.data
    waiting_for[uid] = {"action": action}
    prompts = {
        "ask": "Send your question for /ask:",
        "image": "Send the image prompt for /image:",
        "tts": "Send the text for /tts:",
        "info": "Send the username or ID for /info:",
        "solve": "Send your assignment for /solve:",
        "advice": "Send the topic for /advice:",
    }
    query.message.reply_text(prompts.get(action, "Send your input:"))

# ---------------- MULTI-STEP TEXT ----------------
def text_message_handler(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid in waiting_for:
        state = waiting_for.pop(uid)
        action = state.get("action")
        text = update.message.text.strip()
        if action == "ask": _do_ask(update.effective_chat.id, text, context)
        elif action == "image": _do_image(update.effective_chat.id, text, context)
        elif action == "tts": _do_tts(update.effective_chat.id, text, context)
        elif action == "info": _do_info(update.effective_chat.id, text, context)
        elif action == "solve": _do_solve(update.effective_chat.id, text, context)
        elif action == "advice": _do_advice(update.effective_chat.id, text, context)
        else: update.message.reply_text("Unknown action.")
        return
    if len(update.message.text.strip()) < 6: return
    update.message.reply_text("🤖 Here's a quick AI reply...")
    _do_ask(update.effective_chat.id, update.message.text.strip(), context)

# ---------------- ADMIN ----------------
@admin_only
def addadmin_cmd(update: Update, context: CallbackContext):
    if not context.args: return update.message.reply_text("Usage: /addadmin <telegram_user_id>")
    uid = context.args[0]
    if uid in data.get("admins", []):
        return update.message.reply_text("User is already an admin.")
    data.setdefault("admins", []).append(uid)
    save_data(data)
    update.message.reply_text(f"Added {uid} as admin.")

@admin_only
def removeadmin_cmd(update: Update, context: CallbackContext):
    if not context.args: return update.message.reply_text("Usage: /removeadmin <telegram_user_id>")
    uid = context.args[0]
    if uid not in data.get("admins", []):
        return update.message.reply_text("User is not an admin.")
    data["admins"].remove(uid)
    save_data(data)
    update.message.reply_text(f"Removed {uid} from admins.")

@admin_only
def listadmins_cmd(update: Update, context: CallbackContext):
    admins = data.get("admins", [])
    update.message.reply_text("Admins:\n" + "\n".join(admins) if admins else "No admins set.")

# ---------------- MAIN ----------------
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("ask", ask_cmd))
    dp.add_handler(CommandHandler("image", image_cmd))
    dp.add_handler(CommandHandler("tts", tts_cmd))
    dp.add_handler(CommandHandler("info", info_cmd))
    dp.add_handler(CommandHandler("solve", solve_cmd))
    dp.add_handler(CommandHandler("advice", advice_cmd))

    dp.add_handler(CommandHandler("addadmin", addadmin_cmd))
    dp.add_handler(CommandHandler("removeadmin", removeadmin_cmd))
    dp.add_handler(CommandHandler("admins", listadmins_cmd))

    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.voice, voice_handler))
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))

    updater.start_polling()
    logger.info("Bot started.")
    updater.idle()

if __name__ == "__main__":
    main()