import os
import json
import threading
import math
from functools import wraps
from gtts import gTTS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters
)
import openai

# ===== CONFIG =====
TELEGRAM_BOT_TOKEN = "8435631757:AAHj8lR8rDG72DxetBGUyLeVg3ZQHpKbMh0"
OWNER_ID = "7301067810"
openai.api_key = "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"

waiting_for = {}

# ===== ADMIN HELPERS =====
DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"admins": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

data = load_data()
if OWNER_ID not in data.get("admins", []):
    data.setdefault("admins", []).append(OWNER_ID)
    save_data(data)

def is_admin(user_id):
    return str(user_id) in data.get("admins", [])

def admin_only(func):
    @wraps(func)
    def wrapper(update, context, *a, **kw):
        uid = update.effective_user.id
        if not is_admin(uid):
            update.message.reply_text("❌ You are not authorized.")
            return
        return func(update, context, *a, **kw)
    return wrapper

# ===== OPENAI HELPERS =====
def openai_chat_reply(prompt, system="You are a helpful assistant.", max_tokens=700):
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ OpenAI error: {e}"

# ===== UTILITIES =====
def run_in_thread(fn):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t
    return wrapper

def send_typing(chat_id, context):
    context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

# ===== COMMANDS =====
def start_cmd(update, context):
    kb = [
        [InlineKeyboardButton("Ask AI", callback_data="ask"),
         InlineKeyboardButton("Solve HW", callback_data="solve")],
        [InlineKeyboardButton("Advice", callback_data="advice"),
         InlineKeyboardButton("TTS", callback_data="tts")],
        [InlineKeyboardButton("Info", callback_data="info"),
         InlineKeyboardButton("Math Solver", callback_data="math")],
        [InlineKeyboardButton("Random Joke", callback_data="joke"),
         InlineKeyboardButton("Quote", callback_data="quote")]
    ]
    text = (
        "👋 <b>Hello! David's AI is here!</b>\n\n"
        "I can assist you with anything you need.\n"
        "Choose any button or use commands:\n"
        "/ask /solve /advice /tts /info /math /joke /quote"
    )
    update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)
    )

def help_cmd(update, context):
    update.message.reply_text(
        "Commands:\n"
        "/ask <question>\n"
        "/solve <assignment>\n"
        "/advice <topic>\n"
        "/tts <text>\n"
        "/info <username_or_id>\n"
        "/math <expression>\n"
        "/joke\n"
        "/quote\n"
        "Use buttons for quick actions."
    )

# ===== CORE COMMANDS =====
@run_in_thread
def _do_ask(chat_id, prompt, context):
    send_typing(chat_id, context)
    answer = openai_chat_reply(prompt)
    context.bot.send_message(chat_id=chat_id, text=answer)

def ask_cmd(update, context):
    prompt = " ".join(context.args).strip()
    if not prompt: return update.message.reply_text("Usage: /ask <question>")
    _do_ask(update.effective_chat.id, prompt, context)

@run_in_thread
def _do_tts(chat_id, text, context):
    send_typing(chat_id, context)
    try:
        tts = gTTS(text)
        file_path = f"{chat_id}_tts.mp3"
        tts.save(file_path)
        context.bot.send_message(chat_id=chat_id, text=f"TTS ready. Download here: {file_path}")
    except Exception as e:
        context.bot.send_message(chat_id=chat_id, text=f"TTS error: {e}")

def tts_cmd(update, context):
    text = " ".join(context.args).strip()
    if not text: return update.message.reply_text("Usage: /tts <text>")
    _do_tts(update.effective_chat.id, text, context)

@run_in_thread
def _do_info(chat_id, target, context):
    try:
        send_typing(chat_id, context)
        chat = context.bot.get_chat(target)
        info = (
            f"👤 User Info\n"
            f"First name: {chat.first_name or '-'}\n"
            f"Last name: {chat.last_name or '-'}\n"
            f"Username: @{chat.username or '-'}\n"
            f"User ID: {chat.id}"
        )
        context.bot.send_message(chat_id=chat_id, text=info)
    except Exception as e:
        context.bot.send_message(chat_id=chat_id, text=f"Cannot fetch info: {e}")

def info_cmd(update, context):
    if not context.args: return update.message.reply_text("Usage: /info <username_or_id>")
    target = context.args[0]
    _do_info(update.effective_chat.id, target, context)

@run_in_thread
def _do_solve(chat_id, text, context):
    send_typing(chat_id, context)
    system = "You are an expert tutor. Explain step-by-step."
    answer = openai_chat_reply(text, system=system, max_tokens=1000)
    context.bot.send_message(chat_id=chat_id, text=answer)

def solve_cmd(update, context):
    text = " ".join(context.args).strip()
    if not text: return update.message.reply_text("Usage: /solve <assignment>")
    _do_solve(update.effective_chat.id, text, context)

@run_in_thread
def _do_advice(chat_id, topic, context):
    send_typing(chat_id, context)
    prompt = f"Provide advice on: {topic} (4-6 bullet points)"
    advice = openai_chat_reply(prompt, max_tokens=300)
    context.bot.send_message(chat_id=chat_id, text=advice)

def advice_cmd(update, context):
    topic = " ".join(context.args).strip()
    if not topic: return update.message.reply_text("Usage: /advice <topic>")
    _do_advice(update.effective_chat.id, topic, context)

def math_cmd(update, context):
    expr = " ".join(context.args).strip()
    if not expr: return update.message.reply_text("Usage: /math <expression>")
    try:
        allowed = {"__builtins__": None, "abs": abs, "round": round, "pow": pow, "math": math}
        result = eval(expr, allowed)
        update.message.reply_text(f"Result: {result}")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def joke_cmd(update, context):
    answer = openai_chat_reply("Tell me a funny short joke.")
    update.message.reply_text(answer)

def quote_cmd(update, context):
    answer = openai_chat_reply("Give me an inspiring motivational quote.")
    update.message.reply_text(answer)

# ===== INLINE BUTTONS =====
def callback_handler(update, context):
    query = update.callback_query
    query.answer()
    uid = query.from_user.id
    action = query.data
    waiting_for[uid] = {"action": action}
    prompts = {
        "ask": "Send your question for /ask:",
        "tts": "Send the text for /tts:",
        "info": "Send username or ID for /info:",
        "solve": "Send assignment for /solve:",
        "advice": "Send topic for /advice:",
        "math": "Send math expression for /math:",
        "joke": "Click /joke command to get a random joke.",
        "quote": "Click /quote command to get a quote."
    }
    query.message.reply_text(prompts.get(action, "Send your input:"))

def text_message_handler(update, context):
    uid = update.effective_user.id
    if uid in waiting_for:
        state = waiting_for.pop(uid)
        action = state.get("action")
        text = update.message.text.strip()
        if action == "ask": _do_ask(update.effective_chat.id, text, context)
        elif action == "tts": _do_tts(update.effective_chat.id, text, context)
        elif action == "info": _do_info(update.effective_chat.id, text, context)
        elif action == "solve": _do_solve(update.effective_chat.id, text, context)
        elif action == "advice": _do_advice(update.effective_chat.id, text, context)
        elif action == "math": math_cmd(update, context)
        else: update.message.reply_text("Unknown action.")

# ===== MAIN =====
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("ask", ask_cmd))
    dp.add_handler(CommandHandler("tts", tts_cmd))
    dp.add_handler(CommandHandler("info", info_cmd))
    dp.add_handler(CommandHandler("solve", solve_cmd))
    dp.add_handler(CommandHandler("advice", advice_cmd))
    dp.add_handler(CommandHandler("math", math_cmd))
    dp.add_handler(CommandHandler("joke", joke_cmd))
    dp.add_handler(CommandHandler("quote", quote_cmd))

    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()            f"👤 User Info\n"
            f"First name: {chat.first_name or '-'}\n"
            f"Last name: {chat.last_name or '-'}\n"
            f"Username: @{chat.username or '-'}\n"
            f"User ID: {chat.id}"
        )
        context.bot.send_message(chat_id=chat_id, text=info)
    except Exception as e:
        context.bot.send_message(chat_id=chat_id, text=f"Cannot fetch info: {e}")

def info_cmd(update, context):
    if not context.args: return update.message.reply_text("Usage: /info <username_or_id>")
    target = context.args[0]
    _do_info(update.effective_chat.id, target, context)

@run_in_thread
def _do_solve(chat_id, text, context):
    send_typing(chat_id, context)
    system = "You are an expert tutor. Explain step-by-step."
    answer = openai_chat_reply(text, system=system, max_tokens=1000)
    context.bot.send_message(chat_id=chat_id, text=answer)

def solve_cmd(update, context):
    text = " ".join(context.args).strip()
    if not text: return update.message.reply_text("Usage: /solve <assignment>")
    _do_solve(update.effective_chat.id, text, context)

@run_in_thread
def _do_advice(chat_id, topic, context):
    send_typing(chat_id, context)
    prompt = f"Provide advice on: {topic} (4-6 bullet points)"
    advice = openai_chat_reply(prompt, max_tokens=300)
    context.bot.send_message(chat_id=chat_id, text=advice)

def advice_cmd(update, context):
    topic = " ".join(context.args).strip()
    if not topic: return update.message.reply_text("Usage: /advice <topic>")
    _do_advice(update.effective_chat.id, topic, context)

def math_cmd(update, context):
    expr = " ".join(context.args).strip()
    if not expr: return update.message.reply_text("Usage: /math <expression>")
    try:
        allowed = {"__builtins__": None, "abs": abs, "round": round, "pow": pow, "math": math}
        result = eval(expr, allowed)
        update.message.reply_text(f"Result: {result}")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def joke_cmd(update, context):
    answer = openai_chat_reply("Tell me a funny short joke.")
    update.message.reply_text(answer)

def quote_cmd(update, context):
    answer = openai_chat_reply("Give me an inspiring motivational quote.")
    update.message.reply_text(answer)

# ===== INLINE BUTTONS =====
def callback_handler(update, context):
    query = update.callback_query
    query.answer()
    uid = query.from_user.id
    action = query.data
    waiting_for[uid] = {"action": action}
    prompts = {
        "ask": "Send your question for /ask:",
        "tts": "Send the text for /tts:",
        "info": "Send username or ID for /info:",
        "solve": "Send assignment for /solve:",
        "advice": "Send topic for /advice:",
        "math": "Send math expression for /math:",
        "joke": "Click /joke command to get a random joke.",
        "quote": "Click /quote command to get a quote."
    }
    query.message.reply_text(prompts.get(action, "Send your input:"))

def text_message_handler(update, context):
    uid = update.effective_user.id
    if uid in waiting_for:
        state = waiting_for.pop(uid)
        action = state.get("action")
        text = update.message.text.strip()
        if action == "ask": _do_ask(update.effective_chat.id, text, context)
        elif action == "tts": _do_tts(update.effective_chat.id, text, context)
        elif action == "info": _do_info(update.effective_chat.id, text, context)
        elif action == "solve": _do_solve(update.effective_chat.id, text, context)
        elif action == "advice": _do_advice(update.effective_chat.id, text, context)
        elif action == "math": math_cmd(update, context)
        else: update.message.reply_text("Unknown action.")

# ===== MAIN =====
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("ask", ask_cmd))
    dp.add_handler(CommandHandler("tts", tts_cmd))
    dp.add_handler(CommandHandler("info", info_cmd))
    dp.add_handler(CommandHandler("solve", solve_cmd))
    dp.add_handler(CommandHandler("advice", advice_cmd))
    dp.add_handler(CommandHandler("math", math_cmd))
    dp.add_handler(CommandHandler("joke", joke_cmd))
    dp.add_handler(CommandHandler("quote", quote_cmd))

    dp.add_handler(CallbackQueryHandler(callback_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
