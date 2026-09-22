import os
import sys
import subprocess
from flask import Flask

app = Flask(__name__)

# Biến toàn cục theo dõi tiến trình của Bot
bot_process = None

def start_telegram_bot():
    """Khởi chạy Telegram Bot dưới dạng một tiến trình ngầm duy nhất."""
    global bot_process
    if bot_process is None or bot_process.poll() is not None:
        print("🚀 Đang khởi chạy Telegram Bot AI FinBot trong background...")
        # Sử dụng sys.executable để đảm bảo dùng đúng file python của môi trường hiện tại
        bot_process = subprocess.Popen([sys.executable, "telegram_bot.py"])

@app.route('/')
def health_check():
    """Endpoint dùng cho các dịch vụ Cronjob (UptimeRobot, BetterUptime) ping duy trì Server 24/7."""
    return "AI FinBot Webhook Server is active and running 24/7!", 200

if __name__ == "__main__":
    # 1. Khởi chạy Bot duy nhất 1 lần khi Server Flask bật
    start_telegram_bot()
    
    # 2. Lắng nghe đúng PORT do Render / Cloud Server cấp
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)