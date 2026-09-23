# ==============================================================================
# MODULE: telegram_bot.py
# Chức năng:
#   - Telegram Bot Interface cho hệ thống AI FinBot
#   - Tự động vẽ biểu đồ kỹ thuật (TA Chart) và tạo Báo cáo định dạng HTML
#   - Cung cấp hàm send_telegram_signal cho các bot quét tín hiệu tự động
#   - Khởi chạy Web Server giữ Port 24/7 trên Render
# ==============================================================================
import os
import logging
import warnings
import asyncio
import pandas as pd
import numpy as np
import html
import requests
from datetime import datetime, time as dtime
import pytz
from threading import Thread
from flask import Flask
import zoneinfo
import matplotlib
matplotlib.use('Agg')  # Chế độ chạy nền không xuất hiện GUI window
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
# Import hàm quét từ scanner.py
from scanner import run_market_scanner

# Import module nội bộ (Tái sử dụng biến BANK_SYMBOLS để tránh trùng lặp code)
from data_fundamental import (
    BANK_SYMBOLS,
    get_clean_financial_data,
    evaluate_sell_scenarios
)
from data_realtime import (
    get_realtime_ohlcv,
    calculate_realtime_indicators,
)

# Ẩn các cảnh báo không cần thiết
warnings.filterwarnings('ignore')

# Cấu hình Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Đưa Token & Chat ID vào biến môi trường
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8665430392:AAGk2aN9MwynAPE1V5eoXa_wGBcJFxT1FdI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Danh mục vị thế đang giữ giả định (Dùng để tính Stoploss/Takeprofit chính xác)
PORTFOLIO_POSITIONS = {
    "HPG": 26500,  # Giá vốn HPG: 26.500 VNĐ
    "VNM": 68000   # Giá vốn VNM: 68.000 VNĐ
}

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng gõ /scan hoặc /quet trên Telegram."""
    await update.message.reply_text("🔍 FinBot đang tiến hành quét thị trường Realtime, vui lòng đợi trong giây lát...")
    
    # Gọi hàm quét (truyền send_to_telegram=False để không bị gửi lặp 2 tin)
    report_msg = run_market_scanner(send_to_telegram=False)
    
    # Phản hồi báo cáo trực tiếp vào cuộc trò chuyện
    await update.message.reply_html(report_msg)
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Cú pháp: <code>/buy &lt;MÃ_CỔ_PHIẾU&gt;</code>\nVD: <code>/buy HPG</code>", parse_mode="HTML")
        return

    symbol = args[0].strip().upper()
    msg = await update.message.reply_text(f"📊 Đang tính toán kế hoạch giải ngân cho mã #{symbol}...")

    try:
        df_p = get_realtime_ohlcv(symbol, limit=60, resolution="1D")
        if df_p is None or df_p.empty:
            await msg.edit_text(f"⚠️ Không lấy được dữ liệu nến cho mã <code>{symbol}</code>.", parse_mode="HTML")
            return

        df_ind = calculate_realtime_indicators(df_p)
        latest = df_ind.iloc[-1]

        raw_price = float(latest.get("close", 0))
        price_vnd = raw_price * 1000.0 if raw_price < 1000 else raw_price
        
        raw_ma20 = float(latest.get("ma20", 0))
        ma20_vnd = raw_ma20 * 1000.0 if raw_ma20 < 1000 else raw_ma20

        raw_upper = float(latest.get("upper_band", 0))
        upper_vnd = raw_upper * 1000.0 if raw_upper < 1000 else raw_upper

        raw_lower = float(latest.get("lower_band", 0))
        lower_vnd = raw_lower * 1000.0 if raw_lower < 1000 else raw_lower

        rsi14 = float(latest.get("rsi14", 0))

        levels = calculate_buy_levels(symbol, price_vnd, lower_vnd, ma20_vnd, upper_vnd)
        time_str = get_current_time_str()
        report = (
            f"🎯 <b>KẾ HOẠCH GIẢI NGÂN BẮT ĐÁY #{symbol}</b>\n"
            f"<i>Cập nhật realtime: {time_str}</i>\n"
            f"═══════════════════════════════\n"
            f"💰 <b>Giá hiện tại:</b> <code>{price_vnd:,.0f} VNĐ</code> | RSI(14): <code>{rsi14:.1f}</code>\n"
            f"📉 <b>Lower Band:</b> <code>{lower_vnd:,.0f}</code> | MA20: <code>{ma20_vnd:,.0f}</code>\n\n"
            f"📥 <b>CHIẾN LƯỢC GIẢI NGÂN DCA 3 TẦNG:</b>\n"
            f" ├ <b>Vùng 1 (Giải ngân 30% Vốn):</b> <code>{levels['vung_1']:,.0f} VNĐ</code>\n"
            f" │  👉 <i>Thăm dò khi giá chạm/ép sát Lower Band.</i>\n"
            f" ├ <b>Vùng 2 (Giải ngân 40% Vốn):</b> <code>{levels['vung_2']:,.0f} VNĐ</code>\n"
            f" │  👉 <i>Bắt đáy mạnh khi bị hoảng loạn ép thủng sâu Lower Band.</i>\n"
            f" └ <b>Vùng 3 (Gia tăng 30% Vốn còn lại):</b>\n"
            f"    👉 <i>Mua gia tăng khi giá quay đầu vượt lại lên trên dải Lower Band (hoặc EMA9/MA20) xác nhận rút chân với khối lượng lớn.</i>\n\n"
            f"🛡️ <b>QUẢN TRỊ RỦI RO & CHỐT LỜI:</b>\n"
            f" ├ 🔴 <b>Cắt lỗ (Stop Loss):</b> <code>{levels['stop_loss']:,.0f} VNĐ</code> (Thủng sâu Vùng 2)\n"
            f" ├ 🟢 <b>Mục tiêu 1 (Chốt lời 50%):</b> <code>{levels['tp1']:,.0f} VNĐ</code> (Chạm MA20)\n"
            f" └ 🚀 <b>Mục tiêu 2 (Chốt hết):</b> <code>{levels['tp2']:,.0f} VNĐ</code> (Chạm Upper Band)\n\n"
            f"----------------------------------------\n"
            f"⚠️ <i><b>Disclaimer:</b> FinBot không phải là chuyên gia đầu tư, không thay thế lời khuyên tài chính.</i>"
        )

        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Lỗi tính vùng mua mã {symbol}: {e}")
        await msg.edit_text(f"❌ Có lỗi xảy ra khi tính kế hoạch mua cho mã {symbol}.")

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Đang kiểm tra sức khỏe thị trường VN-Index...")

    try:
        df_vni = get_realtime_ohlcv("VNINDEX", limit=60, resolution="1D")
        if df_vni is None or df_vni.empty:
            df_vni = get_realtime_ohlcv("VN-INDEX", limit=60, resolution="1D")

        if df_vni is None or df_vni.empty:
            await msg.edit_text("⚠️ Không lấy được dữ liệu chỉ số VN-Index Realtime.")
            return

        df_ind = calculate_realtime_indicators(df_vni)
        latest = df_ind.iloc[-1]

        vni_close = float(latest.get("close", 0))
        vni_ma20 = float(latest.get("ma20", 0))
        vni_lower = float(latest.get("lower_band", 0))
        vni_upper = float(latest.get("upper_band", 0))
        vni_rsi = float(latest.get("rsi14", 0))

        # ĐÁNH GIÁ VÀ PHÂN TÁCH NHÓM CỔ PHIẾU CHI TIẾT
        if vni_close < vni_lower * 0.98 and vni_rsi < 30:
            status = "🚨 <b>THỊ TRƯỜNG BÁN THÁO HOẢNG LOẠN (PANIC SELL)</b>"
            advice = "🛑 <b>Khuyến nghị:</b> TẠM DỪNG mở vị thế mua bắt đáy mới ở TẤT CẢ các nhóm ngành để quản trị an toàn vốn."
        elif vni_close <= vni_lower * 1.01:
            status = "🟡 <b>THỊ TRƯỜNG ÉP DẢI DƯỚI (VÙNG SẮP ĐẢO CHUYỀN)</b>"
            advice = (
                "🎯 <b>Khuyến nghị:</b>\n"
                " ├ <b>Ưu tiên:</b> Quan sát nhóm cổ phiếu trụ thuộc nhóm Bất động sản/Sản xuất có dòng tiền khỏe "
                "(ngừng rơi trước thị trường) tại Lower Band để giải ngân DCA nhẹ.\n"
                " └ <b>Hạn chế:</b> Tạm thời đứng ngoài nhóm Ngân hàng đang có sự phân hóa mạnh."
            )
        elif vni_close >= vni_ma20:
            status = "🟢 <b>THỊ TRƯỜNG TÍCH LŨY CÂN BẰNG / UPTREND</b>"
            advice = "✅ <b>Khuyến nghị:</b> An toàn để gia tăng tỷ trọng lướt sóng các mã có nền giá tích lũy trên MA20."
        else:
            status = "🟠 <b>THỊ TRƯỜNG ĐANG TRONG NHỊP ĐIỀU CHỈNH</b>"
            advice = (
                "👀 <b>Khuyến nghị:</b> Quan sát nhóm cổ phiếu trụ thuộc nhóm Bất động sản/Sản xuất có dòng tiền khỏe "
                "(ngừng rơi trước thị trường) tại Lower Band, hạn chế giải ngân nhóm Ngân hàng đang phân hóa."
            )
        time_str = get_current_time_str()
        report = (
            f"🏛️ <b>BÁO CÁO SỨC KHỎE THỊ TRƯỜNG VN-INDEX</b>\n"
            f"<i>Cập nhật realtime: {time_str}</i>\n"
            f"═══════════════════════════════\n"
            f"📊 <b>Điểm số:</b> <code>{vni_close:,.2f}</code> | RSI(14): <code>{vni_rsi:.1f}</code>\n"
            f"├ MA20: <code>{vni_ma20:,.2f}</code>\n"
            f"├ Lower Band: <code>{vni_lower:,.2f}</code>\n"
            f"└ Upper Band: <code>{vni_upper:,.2f}</code>\n\n"
            f"🚦 <b>Trạng thái:</b> {status}\n\n"
            f"💡 {advice}\n\n"
            f"----------------------------------------\n"
            f"⚠️ <i><b>Disclaimer:</b> FinBot không phải là chuyên gia đầu tư, không thay thế lời khuyên tài chính.</i>"
        )

        await msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Lỗi kiểm tra thị trường VN-Index: {e}")
        await msg.edit_text("❌ Lỗi hệ thống khi kiểm tra thông số VN-Index.")

# ==============================================================================
# HÀM GIÚP BÁO TÍN HIỆU TỰ ĐỘNG CHO MAIN_SIGNAL_BOT
# ==============================================================================
def get_current_time_str() -> str:
    """Lấy thời gian realtime hiện tại theo chuẩn múi giờ Việt Nam (Asia/Ho_Chi_Minh)."""
    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(tz)
    return now.strftime("%d/%m/%Y %H:%M:%S")

def send_telegram_signal(symbol: str, signal_type: str, price: float, ema20: float, rsi: float, fund_info: dict, technical_reasons: str = "", trade_plan: str = ""):
    """Hàm gửi tín hiệu Mua/Bán tự động qua Telegram API Sync cho main_signal_bot."""
    if not BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID. Không thể gửi tin nhắn tự động.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    emoji = "🟢" if "BUY" in signal_type else "🔴"
    text = f"{emoji} <b>TÍN HIỆU HỆ THỐNG: {signal_type} #{symbol.upper()}</b>\n"
    text += f"───────────────────────\n"
    text += f"💵 <b>Giá kích hoạt:</b> <code>{price:,.0f} VNĐ</code>\n"
    text += f"📈 <b>EMA20:</b> <code>{ema20:,.0f}</code> | <b>RSI(14):</b> <code>{rsi:.1f}</code>\n\n"
    
    if technical_reasons:
        text += f"📝 <b>Lý do kỹ thuật:</b>\n{technical_reasons}\n\n"
        
    if trade_plan:
        text += f"🎯 <b>Kế hoạch giao dịch:</b>\n{trade_plan}\n\n"

    text += f"⚠️ <i>Tín hiệu tự động từ FinBot Backtest Model.</i>"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram Signal: {e}")
        return False


# ==============================================================================
# HÀM BỔ TRỢ: KIỂM TRA GIỜ THỊ TRƯỜNG & TẠO REPORT HTML
# ==============================================================================
def is_market_hours() -> bool:
    """Kiểm tra xem hiện tại có đang trong giờ giao dịch không (T2-T6: 9h-11h30 & 13h-15h)"""
    try:
        tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
        now = datetime.now(tz_vn)
    except Exception:
        now = datetime.now()

    # Thứ 7 (5) hoặc Chủ Nhật (6)
    if now.weekday() >= 5:
        return False

    current_time = now.time()
    session1_start = datetime.strptime("09:00", "%H:%M").time()
    session1_end = datetime.strptime("11:30", "%H:%M").time()
    session2_start = datetime.strptime("13:00", "%H:%M").time()
    session2_end = datetime.strptime("15:00", "%H:%M").time()

    return (session1_start <= current_time <= session1_end) or (session2_start <= current_time <= session2_end)

def is_market_closed() -> bool:
    """Trả về True nếu thị trường đã đóng cửa (ngoài giờ giao dịch)"""
    return not is_market_hours()

def get_price_label_html() -> str:
    """Tạo nhãn giá hiển thị ngày giờ chuẩn định dạng HTML cho Telegram"""
    try:
        tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
        updated_now = datetime.now(tz_vn).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        updated_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if is_market_hours():
        return f"Giá hiện tại ({updated_now})"
    else:
        return f"Giá đóng cửa ({updated_now})"

def calculate_buy_levels(ticker: str, current_price: float, lower_band: float, ma20: float, upper_band: float) -> dict:
    base_lower = lower_band if lower_band > 0 else current_price * 0.96
    
    # Mức giá tham chiếu Vùng 1 & 2
    vung_1 = base_lower * 1.005        # Thăm dò sát Lower Band
    vung_2 = base_lower * 0.970        # Bắt đáy khi ép thủng sâu Lower Band 3%

    # Ngưỡng Chốt lời / Cắt lỗ
    stop_loss = vung_2 * 0.95
    take_profit_1 = ma20 if ma20 > 0 else current_price * 1.06
    take_profit_2 = upper_band if upper_band > 0 else current_price * 1.12

    return {
        "vung_1": vung_1,
        "vung_2": vung_2,
        "stop_loss": stop_loss,
        "tp1": take_profit_1,
        "tp2": take_profit_2
    }

def build_pretty_html_report(symbol: str, current_price: float, ta_data: dict, fa_data: dict, sell_eval: dict) -> str:
    """Tạo báo cáo định dạng HTML Telegram rõ ràng, chuẩn hóa theo Backtest."""
    symbol = symbol.upper()
    is_bank = fa_data.get("is_bank", False) or (symbol in BANK_SYMBOLS)
    market_closed = is_market_closed()

    # 1. GIÁ HIỆN TẠI / ĐÓNG CỬA
    try:
        tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
        updated_now = datetime.now(tz_vn).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        updated_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if market_closed:
        price_label = f"Giá đóng cửa ({updated_now})"
    else:
        price_label = f"Giá hiện tại ({updated_now})"

    # 2. PHÂN TÍCH CƠ BẢN (FA)
    roe = fa_data.get("roe_annualized", 0.0)
    net_profit = fa_data.get("net_profit_bil", 0.0)
    period = fa_data.get("period", "Gần nhất")

    fa_assessment = "TỐT ✅"
    fa_reasons = []

    if net_profit < 0:
        fa_assessment = "XẤU ❌"
        fa_reasons.append("Doanh nghiệp báo lỗ trong kỳ")

    if not is_bank:
        debt_equity = fa_data.get("debt_equity", 0.0)
        if roe < 8.0 and fa_assessment != "XẤU ❌":
            fa_assessment = "TRUNG BÌNH ⚠️"
            fa_reasons.append(f"ROE thấp ({roe:.1f}%)")
        if debt_equity > 3.0:
            fa_assessment = "XẤU ❌"
            fa_reasons.append(f"Tỷ lệ đòn bẩy D/E cao ({debt_equity:.2f} lần)")

        fa_metrics_str = (
            f"  • ROE: <code>{roe:.2f}%</code>\n"
            f"  • LNST: <code>{net_profit:,.1f} tỷ VNĐ</code>\n"
            f"  • D/E (Nợ/VCSH): <code>{debt_equity:.2f} lần</code>"
        )
    else:
        nim_ratio = fa_data.get("nim_ratio", 0.0)
        if roe < 10.0 and fa_assessment != "XẤU ❌":
            fa_assessment = "TRUNG BÌNH ⚠️"
            fa_reasons.append(f"ROE Ngân hàng ở mức trung bình ({roe:.1f}%)")
        fa_metrics_str = (
            f"  • ROE: <code>{roe:.2f}%</code>\n"
            f"  • LNST: <code>{net_profit:,.1f} tỷ VNĐ</code>\n"
            f"  • Biên lãi thuần (NIM): <code>{nim_ratio:.2f}%</code>"
        )

    if not fa_reasons:
        fa_reasons.append("Sức khỏe tài chính tốt, hoạt động kinh doanh đạt chuẩn an toàn.")

    fa_comment = html.escape("; ".join(fa_reasons))

    # 3. PHÂN TÍCH KỸ THUẬT (TA) - STRATEGY: MEAN REVERSION (BOLLINGER BANDS + RSI)
    ma20 = ta_data.get("ma20", 0.0)
    upper_band = ta_data.get("upper_band", 0.0)
    lower_band = ta_data.get("lower_band", 0.0)
    rsi14 = ta_data.get("rsi14", 0.0)
    prev_rsi14 = ta_data.get("prev_rsi14", 0.0)

    ta_assessment = "TRUNG BÌNH ⚠️"
    ta_reasons = []

    # --- ĐÁNH GIÁ VỊ TRÍ GIÁ SO VỚI BOLLINGER BANDS ---
    if lower_band > 0 and current_price <= lower_band * 1.01:
        ta_reasons.append("Giá ép sát/thủng Dải Dưới (Lower Band) — Vùng quá bán")
    elif upper_band > 0 and current_price >= upper_band * 0.99:
        ta_reasons.append("Giá chạm/vượt Dải Trên (Upper Band) — Vùng quá mua ngắn hạn")
    elif ma20 > 0 and current_price >= ma20:
        ta_reasons.append("Giá nằm trên MA20 (Nền giá tích lũy cân bằng)")
    else:
        ta_reasons.append("Giá nằm dưới MA20 (Đang trong nhịp điều chỉnh)")

    # --- ĐÁNH GIÁ CHỈ BÁO RSI(14) & TÍN HIỆU ĐẢO CHUYỂN ---
    if rsi14 <= 35:
        ta_reasons.append(f"RSI lọt vùng Quá Bán sâu ({rsi14:.1f}) — Cơ hội bắt đáy cao")
    elif rsi14 <= 42:
        ta_reasons.append(f"RSI chạm vùng Quá Bán ({rsi14:.1f})")
    elif rsi14 >= 65:
        ta_reasons.append(f"RSI vào vùng Quá Mua rủi ro ({rsi14:.1f}) — Ưu tiên chốt lời")
    else:
        ta_reasons.append(f"RSI ở trạng thái Trung tính ({rsi14:.1f})")

    # Kiểm tra nến rút chân / RSI móc lên
    if rsi14 > prev_rsi14 and current_price <= lower_band * 1.02:
        ta_reasons.append(f"RSI có tín hiệu MÓC LÊN ({prev_rsi14:.1f} ↗️ {rsi14:.1f}) tại vùng đáy")

    # --- ĐÁNH GIÁ TỔNG THỂ TA METRICS ---
    if (current_price <= lower_band * 1.01) and (rsi14 <= 42):
        ta_assessment = "TỐT ✅ (VÙNG MUA BẮT ĐÁY)"
    elif (current_price >= upper_band * 0.99) or (rsi14 >= 65):
        ta_assessment = "XẤU ❌ (VÙNG CHỐT LỜI/RỦI RO)"

    # Chuỗi hiển thị chỉ báo kỹ thuật gửi qua Telegram
    ta_metrics_str = (
        f"  • MA20: <code>{ma20:,.0f}</code>\n"
        f"  • Lower Band: <code>{lower_band:,.0f}</code> | Upper Band: <code>{upper_band:,.0f}</code>\n"
        f"  • RSI(14): <code>{rsi14:.1f}</code> (Trước: <code>{prev_rsi14:.1f}</code>)"
    )

    ta_comment = "\n  - ".join([html.escape(r) for r in ta_reasons])
# 4. KHUYẾN NGHỊ CUỐI CÙNG (MEAN REVERSION STRATEGY)
    sell_signal = sell_eval.get("signal", "HOLD")
    scenario = sell_eval.get("scenario", "NONE")
    reason_sell = sell_eval.get("reason", "")

    # Lấy tham số cho chiến lược BB + RSI
    lower_band = ta_data.get("lower_band", 0.0)
    upper_band = ta_data.get("upper_band", 0.0)
    ma20 = ta_data.get("ma20", 0.0)
    rsi14 = ta_data.get("rsi14", 0.0)
    prev_rsi14 = ta_data.get("prev_rsi14", 0.0)

    # ĐIỀU KIỆN KỸ THUẬT MEAN REVERSION
    is_buy_bb = (lower_band > 0) and (current_price <= lower_band * 1.01)  # Ép sát/thủng dải dưới
    is_buy_rsi = (rsi14 <= 42.0)                                           # RSI quá bán
    is_rsi_rebound = (rsi14 > prev_rsi14)                                  # RSI móc lên đảo chiều

    is_take_profit_bb = (upper_band > 0) and (current_price >= upper_band * 0.99)  # Tiệm cận dải trên
    is_overbought_rsi = (rsi14 >= 65.0)                                           # RSI quá mua

    # --- ĐÁNH GIÁ VÀ ĐƯA RA KHUYẾN NGHỊ ---
    # 1. Bán do Quản trị rủi ro / Danh mục vi phạm
    if sell_signal == "SELL":
        rec_title = "🔴 <b>KHUYẾN NGHỊ: BÁN CẮT LỖ / QUẢN TRỊ RỦI RO</b>"
        rec_reason = f"Vi phạm ngưỡng an toàn [{html.escape(scenario)}]: {html.escape(reason_sell)}"

    # 2. Bán do Chốt lời kỹ thuật (Chạm Upper Band hoặc RSI Quá mua)
    elif is_take_profit_bb or is_overbought_rsi:
        rec_title = "🔴 <b>KHUYẾN NGHỊ: CHỐT LỜI / HẠ TỶ TRỌNG</b>"
        rec_reason = f"Giá tiến vào vùng Quá Mua rủi ro ngắn hạn (Upper Band: {upper_band:,.0f} | RSI: {rsi14:.1f})."

    # 3. Mua mới / Bắt đáy chuẩn Mean Reversion
    elif fa_assessment == "TỐT ✅" and is_buy_bb and is_buy_rsi and is_rsi_rebound:
        rec_title = "🟢 <b>KHUYẾN NGHỊ: MUA MỚI (BUY SIGNAL)</b>"
        rec_reason = f"Nền tảng FA tốt + Bắt đáy Bollinger Bands thành công (RSI {rsi14:.1f} có tín hiệu móc đầu đi lên)."

    # 4. Theo dõi / Canh mua (Giá đã sát đáy nhưng chưa xác nhận RSI đảo chiều)
    elif is_buy_bb and is_buy_rsi:
        rec_title = "🟡 <b>KHUYẾN NGHỊ: CANH MUA (WATCHLIST)</b>"
        rec_reason = "Giá đã đi vào vùng Quá Bán sát dải dưới BB, chờ nến xanh xác nhận đảo chiều để MUA."

    # 5. Nắm giữ / Theo dõi
    else:
        rec_title = "⚪ <b>KHUYẾN NGHỊ: THEO DÕI / GIỮ VỊ THẾ</b>"
        rec_reason = "Giá đang dao động trung tính trong dải Bollinger Bands, chưa xuất hiện điểm giao dịch tối ưu."

    # 6. GHÉP CHUỖI VÀ RETURN Ở CUỐI HÀM
    report = (
        f"📊 <b>PHÂN TÍCH CỔ PHIẾU #{symbol}</b>\n"
        f"----------------------------------------\n"
        f"💰 <b>{price_label}:</b> <code>{current_price:,.0f} VNĐ</code>\n\n"
        f"🏢 <b>1. PHÂN TÍCH CƠ BẢN (FA - {period}):</b>\n"
        f"{fa_metrics_str}\n"
        f"👉 <b>Đánh giá:</b> <b>{fa_assessment}</b>\n"
        f"💬 <i>Nhận xét: {fa_comment}</i>\n\n"
        f"📈 <b>2. PHÂN TÍCH KỸ THUẬT (TA):</b>\n"
        f"{ta_metrics_str}\n"
        f"👉 <b>Đánh giá:</b> <b>{ta_assessment}</b>\n"
        f"💬 <i>Nhận xét:</i>\n"
        f"  - {ta_comment}\n\n"
        f"🎯 <b>3. KHUYẾN NGHỊ ĐẦU TƯ:</b>\n"
        f"{rec_title}\n"
        f"📌 <b>Lý do:</b> {rec_reason}\n\n"
        f"----------------------------------------\n"
        f"⚠️ <i><b>Disclaimer:</b> FinBot không phải là chuyên gia đầu tư, không thay thế lời khuyên tài chính.</i>"
    )

    return report

# ==============================================================================
# HÀM GIẢ LẬP GIAO DỊCH & WEB SERVER KHỞI CHẠY
# ==============================================================================
def execute_bot_trade(side: str, symbol: str, price: float, volume: int) -> bool:
    """Giả lập kết nối Gateway đặt lệnh tự động."""
    try:
        logger.info(f"Đang gửi lệnh API: {side} {volume} {symbol} @ {price}")
        return True
    except Exception as e:
        logger.error(f"Lỗi đặt lệnh: {e}")
        return False


app_web = Flask('')

@app_web.route('/')
def home():
    return "AI FinBot Webhook Server is running 24/7!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()


# ==============================================================================
# HÀM VẼ BIỂU ĐỒ KỸ THUẬT (TA CHART)
# ==============================================================================
def generate_chart(df: pd.DataFrame, ticker: str, stock_type_str: str = "Thường - Biên độ trung bình") -> str:
    """
    Hàm vẽ biểu đồ kỹ thuật 3 khung chuẩn hóa khớp 100% với logic Source Code:
    1. Khung 1: Biểu đồ nến Nhật (Candlestick) + Bollinger Bands + Mũi tên tín hiệu BUY/SELL
    2. Khung 2: RSI(14) với ngưỡng Quá Bán = 42, Quá Mua = 62 (Khớp config)
    3. Khung 3: Khối lượng giao dịch (Volume) + MA20 Volume
    
    Returns:
        str: Đường dẫn file ảnh được lưu (hoặc None nếu gặp lỗi)
    """
    try:
        if df is None or df.empty:
            logger.error(f"❌ DataFrame của {ticker} bị rỗng, không thể vẽ chart.")
            return None

        # ------------------------------------------------------------------
        # A. KHỞI TẠO KHUNG VẼ (FIG & AXES)
        # ------------------------------------------------------------------
        fig, (ax_price, ax_rsi, ax_vol) = plt.subplots(
            nrows=3, 
            ncols=1, 
            figsize=(10, 7), 
            sharex=True, 
            gridspec_kw={'height_ratios': [3, 1.2, 1]}
        )
        
        # Reset index để vẽ nến theo chỉ số x liên tục
        df_plot = df.reset_index(drop=True)
        x_indices = np.arange(len(df_plot))

        # ------------------------------------------------------------------
        # B. KHUNG 1: CÂY NẾN NHẬT (CANDLESTICK) & BOLLINGER BANDS
        # ------------------------------------------------------------------
        # Xác định màu nến: Xanh (Close >= Open), Đỏ (Close < Open)
        colors = ['#26a69a' if close >= open_p else '#ef5350' 
                  for close, open_p in zip(df_plot['close'], df_plot['open'])]
        
        # Vẽ bóng nến (High - Low)
        ax_price.vlines(x_indices, ymin=df_plot['low'], ymax=df_plot['high'], color=colors, linewidth=1)
        
        # Vẽ thân nến (Open - Close)
        for i in range(len(df_plot)):
            bottom = min(df_plot['open'].iloc[i], df_plot['close'].iloc[i])
            height = abs(df_plot['close'].iloc[i] - df_plot['open'].iloc[i])
            # Nếu nến doji (height == 0), cho độ cao tối thiểu để hiển thị
            height = max(height, (df_plot['high'].iloc[i] - df_plot['low'].iloc[i]) * 0.02)
            ax_price.add_patch(
                plt.Rectangle(
                    (i - 0.3, bottom), 0.6, height, 
                    color=colors[i], zorder=3
                )
            )

        # Vẽ các đường chỉ báo Bollinger Bands nếu tồn tại
        if 'ma20' in df_plot.columns:
            ax_price.plot(x_indices, df_plot['ma20'], label='MA20', color='#d32f2f', linestyle='--', linewidth=1)
        if 'upper_band' in df_plot.columns:
            ax_price.plot(x_indices, df_plot['upper_band'], label='Upper Band', color='#78909c', linestyle=':', linewidth=1)
        if 'lower_band' in df_plot.columns:
            ax_price.plot(x_indices, df_plot['lower_band'], label='Lower Band', color='#78909c', linestyle=':', linewidth=1)
        
        # Tô màu dải Bollinger Bands
        if 'lower_band' in df_plot.columns and 'upper_band' in df_plot.columns:
            ax_price.fill_between(x_indices, df_plot['lower_band'], df_plot['upper_band'], color='#e3f2fd', alpha=0.5)

        # ------------------------------------------------------------------
        # C. TỰ ĐỘNG PHÁT HIỆN VÀ VẼ MŨI TÊN BUY 🟢 / SELL 🔴 (TỪ SCANNER LOGIC)
        # ------------------------------------------------------------------
        for i in range(1, len(df_plot)):
            close_p = df_plot['close'].iloc[i]
            low_p = df_plot['low'].iloc[i]
            high_p = df_plot['high'].iloc[i]
            rsi_val = df_plot['rsi14'].iloc[i] if 'rsi14' in df_plot.columns else 50
            lower_b = df_plot['lower_band'].iloc[i] if 'lower_band' in df_plot.columns else 0
            upper_b = df_plot['upper_band'].iloc[i] if 'upper_band' in df_plot.columns else 999999
            
            candle_range = high_p - low_p
            tail_ratio = (close_p - low_p) / candle_range if candle_range > 0 else 0

            # Điều kiện MUA / BÁN
            is_buy = (
                close_p <= lower_b * 1.015 and 
                rsi_val <= 42 and 
                (tail_ratio > 0.4 or rsi_val > df_plot['rsi14'].iloc[i-1])
            )
            is_sell = (close_p >= upper_b or rsi_val >= 62)

            # Vẽ BUY (Xóa emoji để tránh lỗi ô vuông, dùng chữ thuần)
            if is_buy:
                ax_price.annotate(
                    'BUY', 
                    xy=(i, low_p), 
                    xytext=(i, low_p * 0.985),
                    arrowprops=dict(facecolor='#2e7d32', edgecolor='#2e7d32', shrink=0.1, width=1, headwidth=4),
                    ha='center', va='top', fontsize=8, fontweight='bold', color='#2e7d32'
                )
            # Vẽ SELL
            elif is_sell and rsi_val >= 62:
                ax_price.annotate(
                    'SELL', 
                    xy=(i, high_p), 
                    xytext=(i, high_p * 1.015),
                    arrowprops=dict(facecolor='#c62828', edgecolor='#c62828', shrink=0.1, width=1, headwidth=4),
                    ha='center', va='bottom', fontsize=8, fontweight='bold', color='#c62828'
                )

        # NÂNG TRẦN GIÁ TRÊN TRỤC Y ĐỂ KHÔNG BỊ CHẠM TIÊU ĐỀ
        y_min = df_plot['low'].min()
        y_max = df_plot['high'].max()
        ax_price.set_ylim(y_min * 0.97, y_max * 1.06)  # Mở rộng biên trên 6% và biên dưới 3%

        ax_price.set_title(f"Biểu đồ Phân tích #{ticker} [{stock_type_str}]", fontsize=12, fontweight='bold', pad=15)
        ax_price.legend(loc='upper left', fontsize=8)
        ax_price.grid(True, linestyle='--', alpha=0.3)
        # ------------------------------------------------------------------
        # D. KHUNG 2: RSI(14) CHUẨN THAM SỐ CODE (BUY=42, SELL=62)
        # ------------------------------------------------------------------
        if 'rsi14' in df_plot.columns:
            ax_rsi.plot(x_indices, df_plot['rsi14'], label='RSI(14)', color='#0288d1', linewidth=1.5)
            
            # ĐƯỜNG NGHƯỠNG KHỚP 100% VỚI SOURCE CODE
            ax_rsi.axhline(62, color='#b71c1c', linestyle='--', linewidth=1, label='Quá Mua (62)')
            ax_rsi.axhline(42, color='#1b5e20', linestyle='--', linewidth=1, label='Quá Bán (42)')
            
            # Tô màu vùng quá bán (RSI <= 42)
            ax_rsi.fill_between(x_indices, df_plot['rsi14'], 42, where=(df_plot['rsi14'] <= 42), color='#c8e6c9', alpha=0.6)

        ax_rsi.set_ylim(10, 90)
        ax_rsi.legend(loc='upper left', fontsize=8)
        ax_rsi.grid(True, linestyle='--', alpha=0.3)

        # ------------------------------------------------------------------
        # E. KHUNG 3: KHỐI LƯỢNG GIAO DỊCH (VOLUME)
        # ------------------------------------------------------------------
        if 'volume' in df_plot.columns:
            ax_vol.bar(x_indices, df_plot['volume'], color=colors, alpha=0.8, width=0.6)
        if 'vol_ma20' in df_plot.columns:
            ax_vol.plot(x_indices, df_plot['vol_ma20'], color='#ef6c00', label='Vol MA20', linewidth=1)
            ax_vol.legend(loc='upper left', fontsize=8)
            
        ax_vol.grid(True, linestyle='--', alpha=0.3)

        # Lưu file ảnh và trả về đường dẫn
        chart_path = f"{ticker}_chart.png"
        plt.tight_layout()
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close(fig)

        return chart_path  # BẮT BUỘC TRẢ VỀ ĐƯỜNG DẪN FILE

    except Exception as e:
        logger.error(f"⚠️ Lỗi khi vẽ biểu đồ cho {ticker}: {e}")
        plt.close('all')
        return None
    
# ==============================================================================
# XỬ LÝ LỆNH PHÂN TÍCH VÀ COMMAND
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 <b>CHÀO MỪNG BẠN ĐẾN VỚI AI FINBOT!</b>\n"
        "<i>Trợ lý phân tích & Quản trị giao dịch chứng khoán thông minh</i>\n"
        "═══════════════════════════════\n\n"
        "📌 <b>CÁC TÍNH NĂNG CHÍNH CỦA BOT:</b>\n\n"
        "1️⃣ <b>Phân Tích Cổ Phiếu Tự Động (FA + TA):</b>\n"
        " └ Gõ trực tiếp Mã cổ phiếu (Ví dụ: <code>HPG</code>, <code>SSI</code>, <code>VCB</code>).\n"
        " └ Nhận Báo cáo sức khỏe doanh nghiệp + Chỉ báo kỹ thuật + Biểu đồ trực quan.\n\n"
        "2️⃣ <b>Kế Hoạch Giải Ngân & Vùng Mua Bắt Đáy:</b>\n"
        " └ Cú pháp: <code>/buy &lt;MÃ&gt;</code> (Ví dụ: <code>/buy HPG</code>).\n"
        " └ Tính toán 3 mốc chia vốn DCA, điểm Cắt lỗ & Chốt lời tự động.\n\n"
        "3️⃣ <b>Soi Lọc Sức Khỏe Thị Trường Chung:</b>\n"
        " └ Cú pháp: <code>/market</code> hoặc <code>/vnindex</code>.\n"
        " └ Đánh giá mức độ an toàn của VN-Index trước khi ra quyết định bắt đáy.\n\n"
        "4️⃣ <b>Quét Tín Hiệu Mua/Bán Realtime:</b>\n"
        " └ Cú pháp: <code>/scan</code> hoặc <code>/quet</code>.\n"
        " └ Quét toàn bộ danh mục theo chiến lược Bollinger Bands & RSI Quá bán.\n\n"
        "----------------------------------------\n"
        "⚠️ <i><b>Disclaimer:</b> FinBot không phải là chuyên gia đầu tư, không thay thế lời khuyên tài chính.</i>"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")


async def analyze_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()
    if not symbol.isalpha() or len(symbol) < 3 or len(symbol) > 4:
        await update.message.reply_text("⚠️ Vui lòng nhập đúng mã cổ phiếu (3-4 ký tự).")
        return

    msg = await update.message.reply_text(f"🔍 Đang truy xuất dữ liệu cho mã #{symbol}...")

    try:
        # Lấy dữ liệu FA & TA Realtime
        fa_data = get_clean_financial_data(symbol)
        df_p = get_realtime_ohlcv(symbol, limit=60, resolution="1D")

        if df_p is None or df_p.empty or len(df_p) < 20:
            await msg.edit_text(f"⚠️ Không tìm thấy hoặc thiếu dữ liệu nến Realtime cho mã <code>{symbol}</code>.", parse_mode="HTML")
            return

        # Tính toán chỉ báo (đã chứa MA20, Upper Band, Lower Band, RSI14)
        df_ind = calculate_realtime_indicators(df_p)
        latest = df_ind.iloc[-1]
        previous = df_ind.iloc[-2]  # Lấy thêm nến kế trước để soi RSI móc lên

        # Chuẩn hóa đơn vị giá (chuyển về VNĐ)
        raw_price = float(latest.get("close", 0))
        price_vnd = raw_price * 1000.0 if raw_price < 1000 else raw_price
        
        raw_ma20 = float(latest.get("ma20", 0))
        ma20_vnd = raw_ma20 * 1000.0 if raw_ma20 < 1000 else raw_ma20

        raw_upper = float(latest.get("upper_band", 0))
        upper_vnd = raw_upper * 1000.0 if raw_upper < 1000 else raw_upper

        raw_lower = float(latest.get("lower_band", 0))
        lower_vnd = raw_lower * 1000.0 if raw_lower < 1000 else raw_lower

        rsi14 = float(latest.get("rsi14", 0))
        prev_rsi14 = float(previous.get("rsi14", 0))
        volume = float(latest.get("volume", 0))

        # Đóng gói Dictionary chuẩn Chiến lược Mean Reversion
        ta_data_dict = {
            "close": price_vnd,
            "open": float(latest.get("open", 0)) * (1000.0 if float(latest.get("open", 0)) < 1000 else 1.0),
            "ma20": ma20_vnd,
            "upper_band": upper_vnd,
            "lower_band": lower_vnd,
            "rsi14": rsi14,
            "prev_rsi14": prev_rsi14,
            "volume": volume
        }

        # Đánh giá kịch bản bán dựa trên vị thế
        entry_price = PORTFOLIO_POSITIONS.get(symbol)
        sell_eval = evaluate_sell_scenarios(
            symbol=symbol,
            current_price=price_vnd,
            ta_data=ta_data_dict,
            fund_data=fa_data,
            entry_price=entry_price
        )

        # Biên soạn HTML Báo cáo
        report_html = build_pretty_html_report(
            symbol=symbol,
            current_price=price_vnd,
            ta_data=ta_data_dict,
            fa_data=fa_data,
            sell_eval=sell_eval
        )

        # Xuất biểu đồ và gửi tin nhắn
        chart_path = await asyncio.to_thread(generate_chart, df_ind, symbol)
        try:
            await msg.delete()
        except Exception:
            pass

        with open(chart_path, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption=report_html,
                parse_mode="HTML",
                read_timeout=60,  # Cho phép tối đa 60 giây để upload ảnh
                write_timeout=60
    )

        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Lỗi phân tích mã {symbol}: {e}")
        await update.message.reply_text(f"❌ Có lỗi xảy ra khi xử lý mã {symbol}: {e}")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"⚠️ Phát sinh lỗi hệ thống/mạng: {context.error}")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    # 1. Chạy Flask Web Server ở luồng phụ (Background Thread) để lắng nghe Port
    keep_alive()

    # 2. Khởi tạo Telegram Bot
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .connect_timeout(60.0)
        .pool_timeout(60.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("quet", scan_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CommandHandler("vnindex", market_command))

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), analyze_ticker))
    app.add_error_handler(global_error_handler)

    print("🚀 Đang chạy Telegram Bot & Web Server...")
    
    # 3. Chạy Polling trên biến `app` vừa tạo bên trong hàm
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()