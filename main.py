import os
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN env var")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY env var")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = "You are a helpful, friendly AI assistant."
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "24"))  # total messages (user+assistant)


def _get_history(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get("history", [])


def _save_history(context: ContextTypes.DEFAULT_TYPE, history):
    context.user_data["history"] = history[-MAX_HISTORY:]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! 👋 Send me a message and I’ll reply with AI.\n"
        "Use /reset to clear memory."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("Memory cleared ✅")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # private only
    if update.effective_chat.type != "private":
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    history = _get_history(context)
    history.append({"role": "user", "content": text})
    _save_history(context, history)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _get_history(context)

    try:
        await update.message.chat.send_action("typing")

        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
        )
        answer = resp.choices[0].message.content.strip()

        history = _get_history(context)
        history.append({"role": "assistant", "content": answer})
        _save_history(context, history)

        # Telegram limit ~4096 chars; split long answers
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i+4000])

    except Exception as e:
        logging.exception("Error: %s", e)
        await update.message.reply_text("Something went wrong. Try again in a bit.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
