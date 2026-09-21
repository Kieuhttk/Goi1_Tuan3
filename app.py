import os
import subprocess
from flask import Flask

app = Flask(__name__)

# Khởi chạy Telegram Bot dưới dạng một tiến trình con (Subprocess)
@app.before_request
def start_bot_once():
    if not hasattr(app, 'bot_started'):
        print("🚀 Đang khởi chạy Telegram Bot AI FinBot trong background...")
        subprocess.Popen(["python", "telegram_bot.py"])
        app.bot_started = True

@app.route('/')
def health_check():
    return "AI FinBot is active and running 24/7!"

if __name__ == "__main__":
    # Tự động bật bot khi app khởi chạy
    subprocess.Popen(["python", "telegram_bot.py"])
    
    # Lắng nghe đúng PORT do Render cấp
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)