import os
import asyncio
from flask import Flask
from threading import Thread
# Import trực tiếp ứng dụng Telegram Bot từ file telegram_bot.py của bạn
from telegram_bot import app as telegram_app

flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    """Endpoint cho UptimeRobot / Render Health Check."""
    return "AI FinBot Webhook Server is active and running 24/7!", 200

def run_telegram_bot():
    """Chạy Telegram Bot trong một Event Loop riêng biệt."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Khai báo chạy Polling trực tiếp từ Telegram App
    telegram_app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    print("🚀 Khởi chạy Telegram Bot ngầm...")
    # 1. Chạy Telegram Bot ở một Thread riêng
    bot_thread = Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # 2. Khởi chạy Flask Server lắng nghe PORT của Render
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask Server đang lắng nghe trên port {port}...")
    flask_app.run(host="0.0.0.0", port=port)