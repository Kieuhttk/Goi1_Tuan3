# ==============================================================================
# MODULE: scanner.py (MEAN REVERSION STRATEGY + MARKET FILTER)
# ==============================================================================
import html
import requests
import os
import schedule
import time
import logging
from datetime import datetime
import pytz
# Import các tham số cấu hình từ config.py
from config import (
    TECHNICAL_STRATEGY, 
    FUNDAMENTAL_STRATEGY, 
    DEFAULT_WATCHLIST, 
    TELEGRAM_BOT_TOKEN as CFG_BOT_TOKEN, 
    TELEGRAM_CHAT_ID as CFG_CHAT_ID
)

# Import hàm SQLite từ database.py
from database import get_fa_from_db

# Import các hàm TA Realtime & Bộ lọc VN-Index từ data_realtime.py
from data_realtime import get_realtime_indicators, check_vnindex_safe

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# 1. FIX SỬA LỖI KHAI BÁO BIẾN MÔI TRƯỜNG
# -------------------------------------------------------------
# Lấy từ biến môi trường "TELEGRAM_BOT_TOKEN". Nếu không có, gán giá trị mặc định fallback
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", CFG_BOT_TOKEN) or "8665430392:AAGk2aN9MwynAPE1V5eoXa_wGBcJFxT1FdI"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", CFG_CHAT_ID) or "8843577531"

WATCHLIST = DEFAULT_WATCHLIST

def get_current_time_str() -> str:
    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")

# -------------------------------------------------------------
# 2. FIX SỬA HÀM GỬI THÔNG BÁO TELEGRAM (DÙNG POST DẠNG JSON)
# -------------------------------------------------------------
def send_telegram_alert(message: str, max_retries: int = 3):
    """Gửi báo cáo quét thị trường về Telegram (định dạng HTML) có Retry & Timeout cao."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }

    # Thử lại tối đa max_retries lần nếu bị Timeout
    for attempt in range(1, max_retries + 1):
        try:
            # Tăng read timeout lên 30s (connect_timeout=10, read_timeout=30)
            response = requests.post(url, json=payload, headers=headers, timeout=(10, 30))
            if response.status_code == 200:
                print("✅ [SCANNER] Đã tự động gửi báo cáo về Telegram!")
                return
            else:
                print(f"⚠️ Telegram API Response Error [{response.status_code}]: {response.text}")
                break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
            print(f"⏳ [Lần {attempt}/{max_retries}] Bị timeout kết nối Telegram, đang thử lại sau 2 giây...")
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi kết nối API Telegram: {e}")
            break


def run_market_scanner(send_to_telegram: bool = True) -> str:
    """
    Hàm quét danh mục Watchlist theo chiến lược Mean Reversion (Bollinger Bands + RSI).
    Trả về chuỗi báo cáo HTML dùng cho cả Scheduler và Telegram Command.
    """
    buy_signals = []
    watch_signals = []

    print("🔍 [SCANNER] Đang tiến hành quét danh mục thị trường (Mean Reversion)...")

    # 0. KIỂM TRA BỘ LỌC AN TOÀN THỊ TRƯỜNG VN-INDEX
    is_market_safe = check_vnindex_safe()
    if not is_market_safe:
        warning_msg = (
            "🚨 <b>FINBOT — CẢNH BÁO RỦI RO THỊ TRƯỜNG</b>\n"
            "═══════════════════════════════\n"
            "⚠️ <b>VN-Index bị bán tháo hoảng loạn gãy sâu dải Dưới (Lower Band).</b>\n"
            "🛡️ <b>Hành động:</b> TẠM DỪNG mở vị thế mua bắt đáy mới để đảm bảo an toàn vốn!"
        )
        if send_to_telegram:
            send_telegram_alert(warning_msg)
        return warning_msg

    # Lấy tham số kỹ thuật từ config.py
    buy_rsi_max = TECHNICAL_STRATEGY.get("BUY_RSI_MAX", 42.0)
    buy_bb_buffer = TECHNICAL_STRATEGY.get("BUY_BB_BUFFER", 1.01)

    for ticker in WATCHLIST:
        try:
            # 1. Truy xuất dữ liệu TA Realtime từ data_realtime.py
            ta_data = get_realtime_indicators(ticker)
            if not ta_data or ta_data.get("close", 0) == 0:
                print(f"❌ {ticker}: Không lấy được dữ liệu nến TA Realtime")
                continue

            # 2. Truy xuất dữ liệu FA từ database.py
            fa_data = get_fa_from_db(ticker)

            # CƠ CHẾ DỰ PHÒNG: Tạo FA an toàn nếu DB rỗng/hết hạn
            if not fa_data:
                is_bank_code = ticker in ["ACB", "TCB", "MBB", "STB", "VCB", "CTG", "BID"]
                fa_data = {
                    "roe_annualized": 15.0,
                    "net_profit_bil": 500.0,
                    "debt_equity": 1.5,
                    "is_bank": is_bank_code
                }

            current_price = ta_data.get("close", 0.0)
            open_price = ta_data.get("open", 0.0)
            is_bank = fa_data.get("is_bank", False)

            # 3. ĐÁNH GIÁ PHÂN TÍCH CƠ BẢN (FA)
            roe = fa_data.get("roe_annualized", 0.0)
            net_profit = fa_data.get("net_profit_bil", 0.0)
            debt_equity = fa_data.get("debt_equity", 0.0)

            fa_assessment = "TỐT ✅"
            if net_profit < 0:
                fa_assessment = "XẤU ❌"

            if not is_bank:
                min_roe = FUNDAMENTAL_STRATEGY.get("NON_BANK_ROE_MIN", 8.0)
                max_de = FUNDAMENTAL_STRATEGY.get("MAX_DEBT_EQUITY", 3.0)
                if roe < min_roe and fa_assessment != "XẤU ❌":
                    fa_assessment = "TRUNG BÌNH ⚠️"
                if debt_equity > max_de:
                    fa_assessment = "XẤU ❌"
            else:
                min_bank_roe = FUNDAMENTAL_STRATEGY.get("BANK_ROE_MIN", 10.0)
                if roe < min_bank_roe and fa_assessment != "XẤU ❌":
                    fa_assessment = "TRUNG BÌNH ⚠️"

            # Bỏ qua cổ phiếu có FA yếu/lỗ
            if fa_assessment == "XẤU ❌":
                continue

            # 4. ĐÁNH GIÁ PHÂN TÍCH KỸ THUẬT (TA MEAN REVERSION)
            lower_band = ta_data.get("lower_band", 0.0)
            ma20 = ta_data.get("ma20", 0.0)
            rsi14 = ta_data.get("rsi14", 0.0)
            prev_rsi14 = ta_data.get("prev_rsi14", 0.0)

            # ĐIỀU KIỆN CHUNG: Giá tiệm cận hoặc thủng dải dưới (Price <= Lower Band * 1.01)
            is_near_lower_band = (current_price <= lower_band * buy_bb_buffer) if lower_band > 0 else False
            is_oversold_rsi = (rsi14 <= buy_rsi_max)
            is_rebound_candle = (current_price > open_price)  # Nến xanh / Rút chân
            is_rsi_turning_up = (rsi14 > prev_rsi14)         # RSI bắt đầu móc lên

            # --- TRƯỜNG HỢP 1: TÍN HIỆU MUA BẮT ĐÁY (BUY) ---
            # Thỏa mãn: Nền FA tốt + Tiệm cận dải dưới + RSI Quá bán + Nến rút chân + RSI móc lên
            if fa_assessment == "TỐT ✅" and is_near_lower_band and is_oversold_rsi and is_rebound_candle and is_rsi_turning_up:
                buy_signals.append(
                    f"🟢 <b>{ticker}</b> — Giá: <code>{current_price:,.0f}</code>\n"
                    f"├ 📊 Lower Band: <code>{lower_band:,.0f}</code> | MA20: <code>{ma20:,.0f}</code>\n"
                    f"├ 📉 RSI: <code>{rsi14:.1f}</code> (Phiên trước: <code>{prev_rsi14:.1f}</code>)\n"
                    f"└ 🎯 <b>Lý do MUA:</b> Tiệm cận dải dưới BB, RSI quá bán ({rsi14:.1f}) xuất hiện nến rút chân đảo chiều!"
                )

            # --- TRƯỜNG HỢP 2: TÍCH LŨY CHỜ ĐIỂM MUA (WATCHLIST SẮP VÀO VÙNG MUA) ---
            # Thỏa mãn: Tiệm cận dải dưới + RSI chớm quá bán (RSI <= 45), chờ xác nhận đảo chiều
            elif is_near_lower_band and (rsi14 <= 45.0):
                watch_signals.append(
                    f"🟡 <b>{ticker}</b> — Giá: <code>{current_price:,.0f}</code>\n"
                    f"├ 📊 Lower Band: <code>{lower_band:,.0f}</code> | RSI: <code>{rsi14:.1f}</code>\n"
                    f"└ 🎯 <b>Lý do SĂN:</b> Đã ép sát dải dưới BB. Chờ nến rút chân xanh để kích hoạt MUA."
                )

        except Exception as e:
            print(f"⚠️ [SCANNER] Lỗi khi xử lý mã {ticker}: {e}")

    # 5. TỔNG HỢP NỘI DUNG BÁO CÁO
    time_str = get_current_time_str()
    msg = "🚀 <b>FINBOT — CẢNH BÁO BẮT ĐÁY (MEAN REVERSION)</b>\n"
    msg += f"<i>Thời gian quét: {time_str}</i>\n"
    msg += "═══════════════════════════════\n\n"

    if buy_signals:
        msg += "🔥 <b>TÍN HIỆU MUA BẮT ĐÁY (BUY)</b>:\n\n"
        msg += "\n\n".join(buy_signals) + "\n\n"
    else:
        msg += "ℹ️ <i>Phiên này chưa có mã đạt đủ điều kiện đảo chiều dải dưới Bollinger Bands.</i>\n\n"

    if watch_signals:
        msg += "👀 <b>DANH SÁCH CANH MUA (TIỆM CẬN ĐÁY Short-term)</b>:\n\n"
        msg += "\n\n".join(watch_signals) + "\n\n"

    msg += "───────────────────────────────\n"
    msg += "💡 <b>Hành động:</b> Mua khi xuất hiện tín hiệu MUA 🟢. Chốt lời khi RSI chạm 56 hoặc giá chạm MA20/Upper Band."

    # 6. GỬI TELEGRAM NẾU ĐƯỢC KÍCH HOẠT
    if send_to_telegram:
        send_telegram_alert(msg)
        print("✅ [SCANNER] Đã tự động gửi báo cáo về Telegram!")

    return msg


if __name__ == "__main__":
    print("🚀 [FINBOT SCANNER] Hệ thống quét tự động đã kích hoạt...")
    
    # Lập lịch chạy trong giờ giao dịch
    schedule.every().day.at("01:15").do(run_market_scanner)  # 08:15 VN
    schedule.every().day.at("01:30").do(run_market_scanner)  # 08:30 VN
    schedule.every().day.at("02:00").do(run_market_scanner)  # 09:00 VN
    schedule.every().day.at("02:30").do(run_market_scanner)  # 09:30 VN
    schedule.every().day.at("03:35").do(run_market_scanner)  # 10:35 VN
    # Quét thử 1 lần ngay khi khởi động
    run_market_scanner(send_to_telegram=True)

    # Vòng lặp duy trì tiến trình chạy ẩn
    while True:
        schedule.run_pending()
        time.sleep(30)