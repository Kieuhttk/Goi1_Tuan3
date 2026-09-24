import os
import time
import schedule
from flask import Flask
from threading import Thread

# 1. Import Telegram Bot
from telegram_bot import main as run_bot

# 2. Import Scanner từ scanner.py
from scanner import run_market_scanner

flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "AI FinBot Webhook Server & Scanner active and running 24/7!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# -------------------------------------------------------------
# 3. HÀM CHẠY VÒNG LẶP LẬP LỊCH CHO SCANNER
# -------------------------------------------------------------
def run_scheduler():
    print("🚀 [FINBOT SCANNER] Đã kích hoạt tiến trình lập lịch ngầm...")
    
    # 💥 BƯỚC TEST NGAY: Quét và gửi tin về Telegram ngay khi Server vừa bật lên
    try:
        print("⚡ [TEST INITS] Đang chạy quét thử nghiệm ngay khi khởi tạo...")
        run_market_scanner(send_to_telegram=True)
    except Exception as e:
        print(f"⚠️ Lỗi khi chạy test khởi động: {e}")

    # Lập lịch chạy trong giờ giao dịch chuẩn (Giờ UTC = Giờ VN - 7 tiếng)
    schedule.every().day.at("01:15").do(run_market_scanner)  # 08:15 VN
    schedule.every().day.at("01:30").do(run_market_scanner)  # 08:30 VN
    schedule.every().day.at("02:00").do(run_market_scanner)  # 09:00 VN
    schedule.every().day.at("02:30").do(run_market_scanner)  # 09:30 VN
    schedule.every().day.at("16:10").do(run_market_scanner)  # 10:35 VN

    # Vòng lặp duy trì tiến trình quét
    while True:
        schedule.run_pending()
        time.sleep(30)

# -------------------------------------------------------------
# 4. KHỞI CHẠY TẤT CẢ TIẾN TRÌNH NGẦM (THREADS)
# -------------------------------------------------------------
# Thread 1: Chạy Telegram Bot
bot_thread = Thread(target=run_bot, daemon=True)
bot_thread.start()

# Thread 2: Chạy Scanner Lập lịch
scanner_thread = Thread(target=run_scheduler, daemon=True)
scanner_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Server Flask đang lắng nghe trên port {port}...")
    run_flask()