import os
from flask import Flask
from threading import Thread
# Import duy nhất hàm main từ telegram_bot
from telegram_bot import main as run_bot

flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "AI FinBot Webhook Server is active and running 24/7!", 200
def run_flask():
    # Render cấp cổng qua biến môi trường PORT
    import os
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# Khởi chạy Thread chạy Telegram Bot ngầm ngay khi app khởi động
bot_thread = Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    # Lắng nghe đúng PORT do Render cấp phát
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Server Flask đang lắng nghe trên port {port}...")
    run_flask()