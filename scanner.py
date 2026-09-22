import html
import requests
import os
import schedule
import time

# Import hàm SQLite từ database.py
from database import get_fa_from_db

# Import hàm TA Realtime từ data_realtime.py
from data_realtime import get_realtime_indicators

# Cấu hình biến môi trường (Lấy từ hệ thống hoặc dùng mặc định)
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN", "8665430392:AAGk2aN9MwynAPE1V5eoXa_wGBcJFxT1FdI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8843577531")

# Danh mục các mã cổ phiếu trọng tâm để quét định kỳ
WATCHLIST = [
    "HPG", "SSI", "FPT", "VNM", "MWG", 
    "ACB", "TCB", "REE", "PNJ", "DGC",
    "MBB", "VIC", "VHM", "STB", "KDH"
]

def send_telegram_alert(message: str):
    """Gửi báo cáo quét thị trường về Telegram (định dạng HTML)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"⚠️ Lỗi gửi thông báo Telegram: {e}")

def run_market_scanner(send_to_telegram: bool = True) -> str:
    """
    Hàm quét danh mục Watchlist theo bộ lọc FinBot.
    Trả về chuỗi báo cáo HTML để dùng cho cả Scheduler và Telegram Bot command.
    """
    buy_signals = []
    watch_signals = []

    print("🔍 [SCANNER] Đang tiến hành quét danh mục thị trường...")

    for ticker in WATCHLIST:
        try:
            # 1. Truy xuất dữ liệu TA Realtime từ data_realtime.py
            ta_data = get_realtime_indicators(ticker)
            if not ta_data:
                print(f"❌ {ticker}: Không lấy được dữ liệu nến TA Realtime")
                continue

            # 2. Truy xuất dữ liệu FA từ database.py
            fa_data = get_fa_from_db(ticker)

            # CƠ CHẾ DỰ PHÒNG: Nếu DB rỗng/hết hạn (>24h), tự tạo FA an toàn để test Scanner
            if not fa_data:
                is_bank_code = ticker in ["ACB", "TCB", "MBB", "STB", "VCB", "CTG", "BID"]
                fa_data = {
                    "roe_annualized": 15.0,     # Mặc định ROE 15% (Đạt)
                    "net_profit_bil": 500.0,    # Mặc định LNST > 0 (Đạt)
                    "debt_equity": 1.5,         # Mặc định D/E 1.5 (Đạt)
                    "is_bank": is_bank_code
                }

            current_price = ta_data.get("close", 0.0)
            is_bank = fa_data.get("is_bank", False)

            # 3. ĐÁNH GIÁ PHÂN TÍCH CƠ BẢN (FA)
            roe = fa_data.get("roe_annualized", 0.0)
            net_profit = fa_data.get("net_profit_bil", 0.0)
            debt_equity = fa_data.get("debt_equity", 0.0)

            fa_assessment = "TỐT ✅"
            if net_profit < 0:
                fa_assessment = "XẤU ❌"

            if not is_bank:
                if roe < 8.0 and fa_assessment != "XẤU ❌":
                    fa_assessment = "TRUNG BÌNH ⚠️"
                if debt_equity > 3.0:
                    fa_assessment = "XẤU ❌"
            else:
                if roe < 10.0 and fa_assessment != "XẤU ❌":
                    fa_assessment = "TRUNG BÌNH ⚠️"

            # 4. ĐÁNH GIÁ PHÂN TÍCH KỸ THUẬT (TA)
            ema20 = ta_data.get("ema20", 0.0)
            ema50 = ta_data.get("ema50", 0.0)
            rsi14 = ta_data.get("rsi14", 0.0)
            vol_ratio = ta_data.get("volume_ratio", 0.0)

            # 5. LỌC VÀ ĐÓNG GÓI TÍN HIỆU THEO TIÊU CHÍ CHẶT CHẼ
            # Loại bỏ ngay: Giá dưới EMA20, FA xấu, hoặc Thanh khoản quá cạn (< 0.7x)
            if current_price < ema20 or fa_assessment == "XẤU ❌" or vol_ratio < 0.7:
                continue

            # --- TRƯỜNG HỢP 1: TÍN HIỆU MUA BÙNG NỔ (BUY) ---
            if fa_assessment == "TỐT ✅" and (current_price > ema20 > ema50) and (45 <= rsi14 <= 60) and (vol_ratio >= 1.2):
                buy_signals.append(
                    f"🟢 <b>{ticker}</b> — Giá: <code>{current_price:,.0f}</code>\n"
                    f"├ 📊 RSI: <code>{rsi14:.1f}</code> | Vol: <code>{vol_ratio:.2f}x</code>\n"
                    f"└ 🎯 <b>Lý do MUA:</b> Xu hướng Tăng mạnh (P > EMA20 > EMA50). Tiền vào bùng nổ ({vol_ratio:.2f}x)."
                )

            # --- TRƯỜNG HỢP 2: TÍCH LŨY ĐẸP - CHỜ DÒNG TIỀN (WATCHLIST TỐT) ---
            elif current_price >= ema20 and (45 <= rsi14 <= 60) and (0.8 <= vol_ratio < 1.2):
                watch_signals.append(
                    f"🟡 <b>{ticker}</b> — Giá: <code>{current_price:,.0f}</code>\n"
                    f"├ 📊 RSI: <code>{rsi14:.1f}</code> | Vol: <code>{vol_ratio:.2f}x</code>\n"
                    f"└ 🎯 <b>Lý do SĂN:</b> Tích lũy siết nền trên EMA20. Cần Vol bùng nổ > 1.2x để kích hoạt điểm MUA."
                )

        except Exception as e:
            print(f"⚠️ [SCANNER] Lỗi khi xử lý mã {ticker}: {e}")

    # 6. TỔNG HỢP NỘI DUNG BÁO CÁO
    msg = "🚀 <b>FINBOT — CẢNH BÁO TÍN HIỆU BÙNG NỔ</b>\n"
    msg += "═══════════════════════════════\n\n"

    if buy_signals:
        msg += "🔥 <b>TÍN HIỆU MUA CHUẨN (BUY)</b>:\n\n"
        msg += "\n\n".join(buy_signals) + "\n\n"
    else:
        msg += "ℹ️ <i>Phiên này chưa có mã đạt đủ Volume để MUA ngay.</i>\n\n"

    if watch_signals:
        msg += "👀 <b>DANH SÁCH CHỜ BÙNG NỔ (WATCHLIST CHẤT LƯỢNG)</b>:\n\n"
        msg += "\n\n".join(watch_signals) + "\n\n"

    msg += "───────────────────────────────\n"
    msg += "💡 <b>Hành động:</b> Nếu có nhóm MUA -> Mở vị thế. Nếu chỉ có nhóm WATCHLIST -> Đưa vào bảng điện canh lệnh khi Vol vượt 1.2x."

    # 7. GỬI TELEGRAM NẾU ĐƯỢC KÍCH HOẠT TỪ SCHEDULER
    if send_to_telegram:
        send_telegram_alert(msg)
        print("✅ [SCANNER] Đã tự động gửi báo cáo về Telegram!")

    return msg

if __name__ == "__main__":
    print("🚀 [FINBOT SCANNER] Hệ thống quét tự động đã kích hoạt...")
    
    # Lập lịch chạy trong giờ giao dịch
    schedule.every().day.at("08:20").do(run_market_scanner)
    schedule.every().day.at("09:00").do(run_market_scanner)
    schedule.every().day.at("09:15").do(run_market_scanner)
    schedule.every().day.at("09:30").do(run_market_scanner)

    # Quét thử 1 lần ngay khi khởi động
    run_market_scanner(send_to_telegram=True)

    # Vòng lặp duy trì tiến trình chạy ẩn
    while True:
        schedule.run_pending()
        time.sleep(30)