import os
import asyncio
from flask import Flask
from threading import Thread

# Import duy nhất biến Telegram app từ telegram_bot.py
from telegram_bot import app as telegram_app

flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "AI FinBot Webhook Server is active and running 24/7!", 200

def run_telegram_bot():
    """Chạy Telegram Bot trong Event Loop riêng."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    telegram_app.run_polling(drop_pending_updates=True, close_loop=False)

# Khởi chạy Thread ngầm cho Telegram Bot
bot_thread = Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Server Flask đang lắng nghe trên port {port}...")
    flask_app.run(host="0.0.0.0", port=port)