import os
import logging
import asyncio
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN env var")
if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY env var")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful, friendly AI assistant.")
MODEL = os.getenv("MODEL", "llama-3.1-8b-instant")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "24"))

PORT = int(os.getenv("PORT", "10000"))  # Render provides PORT automatically


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

        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i + 4000])

    except Exception as e:
        logging.exception("Error: %s", e)
        await update.message.reply_text("Something went wrong. Try again in a bit.")


async def health_server():
    # Tiny HTTP server so Render detects an open port
    async def handle(reader, writer):
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    logging.info("Health server running on port %s", PORT)
    async with server:
        await server.serve_forever()


async def main_async():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # run health server forever (keeps process alive)
    await health_server()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
