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
import html
import requests
from datetime import datetime, time as dtime
from threading import Thread
from flask import Flask

import matplotlib
matplotlib.use('Agg')  # Chế độ chạy nền không xuất hiện GUI window
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

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

# ==============================================================================
# HÀM GIÚP BÁO TÍN HIỆU TỰ ĐỘNG CHO MAIN_SIGNAL_BOT
# ==============================================================================
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
def is_market_closed() -> bool:
    """Kiểm tra xem thị trường chứng khoán Việt Nam hiện tại đã đóng cửa chưa."""
    now = datetime.now()
    if now.weekday() >= 5:  # Thứ 7 hoặc Chủ Nhật
        return True
    
    market_close_time = dtime(15, 0, 0)
    market_open_time = dtime(9, 0, 0)
    
    if now.time() > market_close_time or now.time() < market_open_time:
        return True
    return False


def build_pretty_html_report(symbol: str, current_price: float, ta_data: dict, fa_data: dict, sell_eval: dict) -> str:
    """Tạo báo cáo định dạng HTML Telegram rõ ràng, chuẩn hóa theo Backtest."""
    symbol = symbol.upper()
    is_bank = fa_data.get("is_bank", False) or (symbol in BANK_SYMBOLS)
    market_closed = is_market_closed()

    # 1. GIÁ HIỆN TẠI / ĐÓNG CỬA
    price_label = "Giá đóng cửa" if market_closed else "Giá hiện tại"
    price_fmt = f"<code>{current_price:,.0f} VNĐ</code>"

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

    # 3. PHÂN TÍCH KĨ THUẬT (TA)
    ema20 = ta_data.get("ema20", 0.0)
    ema50 = ta_data.get("ema50", 0.0)
    rsi14 = ta_data.get("rsi14", 0.0)
    vol_ratio = ta_data.get("volume_ratio", 0.0)

    ta_assessment = "TỐT ✅"
    ta_reasons = []

    if current_price >= ema20:
        ta_reasons.append("Giá duy trì trên EMA20 (Xu hướng tăng)")
    else:
        ta_assessment = "XẤU ❌"
        ta_reasons.append("Giá thủng EMA20 (Khả năng bước vào nhịp chỉnh)")

    # ĐIỀU KIỆN TỐI ƯU BACKTEST DÀNH CHO RSI & VOLUME
    if rsi14 > 65:
        ta_reasons.append(f"RSI chạm vùng rủi ro ngắn hạn ({rsi14:.1f})")
    elif rsi14 < 40:
        ta_reasons.append(f"RSI suy yếu ({rsi14:.1f})")
    else:
        ta_reasons.append(f"RSI vùng tích lũy bùng nổ đẹp ({rsi14:.1f})")

    if vol_ratio >= 1.2:
        ta_reasons.append(f"Dòng tiền xác nhận (Vol đạt {vol_ratio:.2f}x MA20)")
    else:
        ta_reasons.append(f"Thanh khoản chưa bùng nổ (Vol đạt {vol_ratio:.2f}x MA20)")

    ta_metrics_str = (
        f"  • EMA20: <code>{ema20:,.0f}</code> | EMA50: <code>{ema50:,.0f}</code>\n"
        f"  • RSI(14): <code>{rsi14:.1f}</code>\n"
        f"  • Volume / MA20: <code>{vol_ratio:.2f}x</code>"
    )
    
    ta_comment = "\n  - ".join([html.escape(r) for r in ta_reasons])

    # 4. KHUYẾN NGHỊ CUỐI CÙNG THEO TIÊU CHUẨN BACKTEST
    sell_signal = sell_eval.get("signal", "HOLD")
    scenario = sell_eval.get("scenario", "NONE")
    reason_sell = sell_eval.get("reason", "")

    if sell_signal == "SELL":
        rec_title = f"🔴 <b>KHUYẾN NGHỊ: BÁN / HẠ TỶ TRỌNG</b>"
        rec_reason = f"Chạm ngưỡng vi phạm [{html.escape(scenario)}]: {html.escape(reason_sell)}"
    # ĐIỀU KIỆN MUA SIẾT CHẶT ĐỂ TĂNG WIN RATE: 45 <= RSI <= 60 và Vol >= 1.2
    elif fa_assessment == "TỐT ✅" and (current_price > ema20 > ema50) and (45 <= rsi14 <= 60) and (vol_ratio >= 1.2):
        rec_title = f"🟢 <b>KHUYẾN NGHỊ: MUA MỚI (BUY SIGNAL)</b>"
        rec_reason = "Đồng thuận Tăng giá (Uptrend) + Dòng tiền bùng nổ + FA đạt chuẩn an toàn."
    else:
        rec_title = f"🟡 <b>KHUYẾN NGHỊ: THEO DÕI / GIỮ VỊ THẾ</b>"
        rec_reason = "Tín hiệu chưa đủ hội tụ điểm mua bùng nổ tối ưu, tiếp tục quan sát."

    # GHÉP KHUNG TIN NHẮN HTML
    report = f"""📊 <b>PHÂN TÍCH CỔ PHIẾU #{symbol}</b>
───────────────────────
💰 <b>{price_label}:</b> {price_fmt}

🏢 <b>1. PHÂN TÍCH CƠ BẢN (FA - {period}):</b>
{fa_metrics_str}
👉 <b>Đánh giá:</b> <b>{fa_assessment}</b>
💬 <i>Nhận xét: {fa_comment}</i>

📈 <b>2. PHÂN TÍCH KỸ THUẬT (TA):</b>
{ta_metrics_str}
👉 <b>Đánh giá:</b> <b>{ta_assessment}</b>
💬 <i>Nhận xét:</i>
  - {ta_comment}

🎯 <b>3. KHUYẾN NGHỊ ĐẦU TƯ:</b>
{rec_title}
📌 <b>Lý do:</b> {rec_reason}

───────────────────────
⚠️ <i><b>Disclaimer:</b> FinBot không phải là chuyên gia đầu tư, không thay thế lời khuyên tài chính.</i>"""

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
def generate_chart(df: pd.DataFrame, symbol: str) -> str:
    """Vẽ biểu đồ Giá, EMA20 và RSI, xuất file temp_symbol.png."""
    chart_filename = f"temp_{symbol}.png"
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2.5, 1]})
    fig.patch.set_facecolor('#1e1e1e')
    
    ax1.set_facecolor('#1e1e1e')
    close_series = df['close'] / 1000.0 if df['close'].iloc[-1] > 1000 else df['close']
    ema20_series = df['ema20'] / 1000.0 if 'ema20' in df.columns and df['ema20'].iloc[-1] > 1000 else df.get('ema20', pd.Series())

    ax1.plot(close_series.values, label='Giá đóng cửa', color='#00e676', linewidth=2)
    if not ema20_series.empty:
        ax1.plot(ema20_series.values, label='EMA20', color='#ff9100', linestyle='--', linewidth=1.5)
    
    ax1.set_title(f"Biểu đồ Phân tích Kỹ thuật #{symbol}", color='white', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left', facecolor='#2a2a2a', edgecolor='none', labelcolor='white')
    ax1.tick_params(colors='white')
    ax1.grid(True, linestyle=':', alpha=0.3)

    ax2.set_facecolor('#1e1e1e')
    if 'rsi14' in df.columns:
        ax2.plot(df['rsi14'].values, color='#29b6f6', label='RSI(14)', linewidth=1.5)
        ax2.axhline(70, color='#ff5252', linestyle=':', alpha=0.7)
        ax2.axhline(30, color='#69f0ae', linestyle=':', alpha=0.7)
        ax2.axhline(50, color='gray', linestyle='--', alpha=0.5)

    ax2.set_ylim(0, 100)
    ax2.tick_params(colors='white')
    ax2.grid(True, linestyle=':', alpha=0.3)
    ax2.legend(loc='upper left', facecolor='#2a2a2a', edgecolor='none', labelcolor='white')

    plt.tight_layout()
    plt.savefig(chart_filename, dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

    return chart_filename


# ==============================================================================
# XỬ LÝ LỆNH PHÂN TÍCH VÀ COMMAND
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 <b>Chào mừng bạn đến với AI FinBot!</b>\n\n"
        "Nhập mã cổ phiếu (VD: <code>VIC</code>, <code>HPG</code>, <code>ACB</code>) để nhận báo cáo phân tích FA/TA tự động."
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

        if df_p is None or df_p.empty:
            await msg.edit_text(f"⚠️ Không tìm thấy dữ liệu giá Realtime cho mã <code>{symbol}</code>.", parse_mode="HTML")
            return

        df_ind = calculate_realtime_indicators(df_p)
        latest = df_ind.iloc[-1]

        raw_price = float(latest.get("close", 0))
        price_vnd = raw_price * 1000.0 if raw_price < 1000 else raw_price
        
        raw_ema20 = float(latest.get("ema20", 0))
        ema20_vnd = raw_ema20 * 1000.0 if raw_ema20 < 1000 else raw_ema20

        raw_ema50 = float(latest.get("ema50", 0))
        ema50_vnd = raw_ema50 * 1000.0 if raw_ema50 < 1000 else raw_ema50

        rsi14 = float(latest.get("rsi14", 0))
        volume = float(latest.get("volume", 0))

        vol_ma20 = float(latest.get("vol_ma20", 0)) if pd.notna(latest.get("vol_ma20")) else 0.0
        vol_ratio = (volume / vol_ma20) if vol_ma20 > 0 else 0.0

        ta_data_dict = {
            "close": price_vnd,
            "ema20": ema20_vnd,
            "ema50": ema50_vnd,
            "rsi14": rsi14,
            "volume": volume,
            "vol_ma20": vol_ma20,
            "volume_ratio": vol_ratio
        }

        # Đánh giá kịch bản bán dựa trên vị thế hiện tại
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
        chart_path = generate_chart(df_ind, symbol)
        await msg.delete()

        with open(chart_path, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption=report_html,
                parse_mode="HTML"
            )

        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Lỗi phân tích mã {symbol}: {e}")
        await update.message.reply_text(f"❌ Có lỗi xảy ra khi xử lý mã {symbol}: {e}")


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 4:
            await update.message.reply_text("⚠️ Cú pháp: <code>/trade &lt;MUA/BAN&gt; &lt;MÃ&gt; &lt;GIÁ&gt; &lt;KHỐI_LƯỢNG&gt;</code>", parse_mode="HTML")
            return

        action, symbol, price, volume = args[0].upper(), args[1].upper(), float(args[2]), int(args[3])
        side = "NB" if action in ["MUA", "NB", "BUY"] else "NS"

        await update.message.reply_text(f"🚀 Đang kết nối gửi lệnh <b>{action} {volume:,} {symbol}</b> giá <b>{price:,.2f}</b>...", parse_mode="HTML")
        success = execute_bot_trade(side=side, symbol=symbol, price=price, volume=volume)

        if success:
            await update.message.reply_text(f"✅ Đã gửi lệnh {action} {symbol} thành công!")
        else:
            await update.message.reply_text("❌ Không thể kết nối tới Gateway đặt lệnh.")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi xử lý lệnh: {e}")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"⚠️ Phát sinh lỗi hệ thống/mạng: {context.error}")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("trade", trade_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), analyze_ticker))
    app.add_error_handler(global_error_handler)

    print("🚀 Đang chạy Telegram Bot độc lập...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()