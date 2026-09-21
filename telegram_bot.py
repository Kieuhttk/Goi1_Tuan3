import os
import logging
import asyncio
import pandas as pd
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

from data_realtime import (
    get_clean_financial_data,
    get_realtime_ohlcv,
    calculate_realtime_indicators,
    execute_bot_trade,
)

# Cấu hình Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8665430392:AAGk2aN9MwynAPE1V5eoXa_wGBcJFxT1FdI"

# Danh sách Ngân hàng & Tài chính
BANK_AND_FINANCE_SYMBOLS = [
    "ACB", "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "STB", "HDB", "TPB",
    "VIB", "EIB", "MSB", "LPB", "OCB", "SSB", "BAB", "NAB", "ABB", "BVB"
]


# ==============================================================================
# 1. HÀM VẼ BIỂU ĐỒ KỸ THUẬT (TA CHART)
# ==============================================================================
def generate_chart(df: pd.DataFrame, symbol: str) -> str:
    """Vẽ biểu đồ Giá, EMA20 và RSI, sau đó lưu ra file ảnh temp_chart.png."""
    chart_filename = f"temp_{symbol}.png"
    
    # Tạo Figure 2 đồ thị (Giá + RSI)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2.5, 1]})
    fig.patch.set_facecolor('#1e1e1e')
    
    # --- Ax1: Giá & EMA20 ---
    ax1.set_facecolor('#1e1e1e')
    ax1.plot(df['close'], label='Giá đóng cửa', color='#00e676', linewidth=2)
    if 'ema20' in df.columns:
        ax1.plot(df['ema20'], label='EMA20', color='#ff9100', linestyle='--', linewidth=1.5)
    
    ax1.set_title(f"Biểu đồ Phân tích Kỹ thuật #{symbol}", color='white', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left', facecolor='#2a2a2a', edgecolor='none', labelcolor='white')
    ax1.tick_params(colors='white')
    ax1.grid(True, linestyle=':', alpha=0.3)

    # --- Ax2: Chỉ báo RSI ---
    ax2.set_facecolor('#1e1e1e')
    if 'rsi14' in df.columns:
        ax2.plot(df['rsi14'], color='#29b6f6', label='RSI(14)', linewidth=1.5)
        ax2.axhline(70, color='#ff5252', linestyle=':', alpha=0.7)  # Vùng quá mua
        ax2.axhline(30, color='#69f0ae', linestyle=':', alpha=0.7)  # Vùng quá bán
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
# 2. XỬ LÝ LỆNH PHÂN TÍCH & LỆNH START
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 **Chào mừng bạn đến với AI FinBot!**\n\n"
        "Nhập mã cổ phiếu (VD: `VIC`, `HPG`, `ACB`) để nhận báo cáo phân tích kèm biểu đồ minh họa."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def analyze_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()

    if not symbol.isalpha() or len(symbol) != 3:
        return

    await update.message.reply_text(f"🔍 Đang truy xuất dữ liệu & vẽ biểu đồ cho mã **{symbol}**...", parse_mode="Markdown")

    try:
        # 1. Lấy dữ liệu FA & TA
        fa_data = get_clean_financial_data(symbol)
        df_p = get_realtime_ohlcv(symbol, limit=60, interval="1D")

        if df_p.empty:
            await update.message.reply_text(f"⚠️ Không tìm thấy dữ liệu giá cho mã `{symbol}`.")
            return

        df_ind = calculate_realtime_indicators(df_p)
        latest = df_ind.iloc[-1]

        # Đơn vị giá
        raw_price = float(latest.get("close", 0))
        price = raw_price / 1000.0 if raw_price > 1000 else raw_price
        
        raw_ema20 = float(latest.get("ema20", 0))
        ema20 = raw_ema20 / 1000.0 if raw_ema20 > 1000 else raw_ema20

        rsi14 = float(latest.get("rsi14", 0))
        volume = float(latest.get("volume", 0))

        # ----------------------------------------------------------------------
        # (1) BỔ SUNG ĐIỀU KIỆN SO SÁNH CHO ROE, BIÊN LN GỘP & NỢ/VỐN CHỦ
        # ----------------------------------------------------------------------
        period = fa_data.get("period", "N/A")
        net_profit_bil = fa_data.get("net_profit_bil", 0.0)
        
        # ROE
        raw_roe = fa_data.get("roe_annualized", 0.0)
        roe = raw_roe * 100.0 if 0 < raw_roe <= 1.0 else raw_roe
        roe_assess = "Tốt / Đạt" if roe >= 15.0 else ("Trung bình" if roe >= 10.0 else "Yếu")

        # LNST
        lnst_assess = "Đạt" if net_profit_bil > 0 else "Cảnh báo (Lỗ)"

        # BIÊN LỢI NHUẬN GỘP
        gross_margin = fa_data.get("gross_margin", 0.0)
        if gross_margin >= 25.0:
            gm_assess = "Tốt (Lợi thế cạnh tranh cao)"
        elif gross_margin >= 12.0:
            gm_assess = "Trung bình"
        else:
            gm_assess = "Thấp (Tỉ suất lợi nhuận mỏng)"

        # NỢ / VỐN CHỦ (D/E)
        debt_equity = fa_data.get("debt_equity", 0.0)
        if debt_equity <= 1.2:
            de_assess = "An toàn (Rủi ro tài chính thấp)"
        elif debt_equity <= 2.5:
            de_assess = "Mức độ vừa phải"
        else:
            de_assess = "Rủi ro cao (Đòn bẩy tài chính lớn)"

        is_bank = symbol in BANK_AND_FINANCE_SYMBOLS

        # ----------------------------------------------------------------------
        # (2) ĐÁNH GIÁ TÍN HIỆU KỸ THUẬT (ĐÃ SỬA CHÍNH XÁC XU HƯỚNG EMA20)
        # ----------------------------------------------------------------------
        # So sánh với EMA20 của 5 phiên trước (1 tuần)
        lookback = 5 if len(df_ind) >= 5 else len(df_ind) - 1
        ema20_prev_raw = float(df_ind['ema20'].iloc[-1 - lookback]) if lookback > 0 else raw_ema20
        ema20_prev = ema20_prev_raw / 1000.0 if ema20_prev_raw > 1000 else ema20_prev_raw

        # Tính phần trăm thay đổi của đường EMA20
        ema20_change_pct = ((ema20 - ema20_prev) / ema20_prev) * 100 if ema20_prev > 0 else 0

        # Xác định độ dốc đường EMA20 với ngưỡng 0.05%
        if ema20_change_pct > 0.05:
            ema_slope_str = "Uptrend (Dốc lên)"
        elif ema20_change_pct < -0.05:
            ema_slope_str = "Downtrend (Dốc xuống)"
        else:
            ema_slope_str = "Đi ngang tích lũy"

        # Vị thế Giá so với EMA20
        price_pos_str = "Giá trên EMA20" if price >= ema20 else "Giá dưới EMA20"

        trend_str = f"{ema_slope_str} ({price_pos_str})"

        # Đánh giá RSI
        if rsi14 >= 70:
            rsi_str = f"{rsi14:.1f} (Quá Mua)"
        elif rsi14 >= 50:
            rsi_str = f"{rsi14:.1f} (Động lượng Tốt/An toàn)"
        else:
            rsi_str = f"{rsi14:.1f} (Động lượng Yếu)"

        # Khuyến nghị
        if price > ema20 and ema20_change_pct > -0.05 and 50 <= rsi14 <= 68 and roe >= 12.0:
            recommendation = "💡 **TÍN HIỆU MUA xuất hiện!** (Giá tích lũy trên EMA20 & FA ổn định)"
        elif price < ema20:
            recommendation = "🚨 **CẢNH BÁO BÁN / NÊN HẠ TỶ TRỌNG** (Giá gãy EMA20)"
        else:
            recommendation = "🟡 **ĐỨNG NGOÀI THEO DÕI** (Chưa đủ điều kiện bứt phá)"

        # ----------------------------------------------------------------------
        # TẠO NỘI DUNG VĂN BẢN
        # ----------------------------------------------------------------------
        if is_bank:
            fa_section = (
                f"🏛️ **Điểm mạnh cơ bản (Mô hình Ngân hàng):**\n"
                f"• ROE : `{roe:.2f}%` ➔ **{roe_assess}**\n"
                f"• LNST ({period}): `{net_profit_bil:,.1f}` tỷ đồng ➔ **{lnst_assess}**\n"
                f"• Đòn bẩy & Biên LN: _Đặc thù Ngân hàng (không áp dụng tiêu chuẩn thường)_\n"
            )
        else:
            fa_section = (
                f"🏢 **Chỉ số Tài chính Trọng yếu ({period}):**\n"
                f"• ROE : `{roe:.2f}%` ➔ **{roe_assess}**\n"
                f"• LNST : `{net_profit_bil:,.1f}` tỷ đồng ➔ **{lnst_assess}**\n"
                f"• Biên LN Gộp: `{gross_margin:.2f}%` ➔ **{gm_assess}**\n"
                f"• Nợ / Vốn chủ (D/E): `{debt_equity:.2f}` lần ➔ **{de_assess}**\n"
            )

        report = (
            f"📊 **PHÂN TÍCH CHI TIẾT CỔ PHIẾU #{symbol}**\n\n"
            f"💵 **Giá giao dịch:** `{price:,.2f} VNĐ` (Tương đương `{price * 1000:,.0f}` đ)\n\n"
            f"{fa_section}\n"
            f"📈 **Phân tích Dòng tiền & Động lượng (TA):**\n"
            f"• Đường EMA20: `{ema20:,.2f} VNĐ` ➔ Trạng thái: **{trend_str}**\n"
            f"• Khối lượng giao dịch: `{volume:,.0f}` cổ phiếu\n"
            f"• Chỉ báo RSI(14): **{rsi_str}**\n\n"
            f"🎯 **KHUYẾN NGHỊ CUỐI CÙNG:**\n{recommendation}\n"
            f"───────────────────────\n"
            f"_Disclaimer: Đây là phân tích tự động từ AI FinBot, không phải cam kết lợi nhuận._"
        )

        # ----------------------------------------------------------------------
        # VẼ VÀ GỬI ẢNH BIỂU ĐỒ QUA TELEGRAM
        # ----------------------------------------------------------------------
        chart_path = generate_chart(df_ind, symbol)

        with open(chart_path, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption=report,
                parse_mode="Markdown"
            )

        # Xóa file ảnh tạm sau khi gửi
        if os.path.exists(chart_path):
            os.remove(chart_path)

    except Exception as e:
        logger.error(f"Lỗi phân tích mã {symbol}: {e}")
        await update.message.reply_text(f"❌ Có lỗi xảy ra khi xử lý mã {symbol}: {e}")


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh đặt tự động."""
    try:
        args = context.args
        if len(args) < 4:
            await update.message.reply_text("⚠️ Cú pháp: `/trade <MUA/BAN> <MÃ> <GIÁ> <KHỐI_LƯỢNG>`", parse_mode="Markdown")
            return

        action, symbol, price, volume = args[0].upper(), args[1].upper(), float(args[2]), int(args[3])
        side = "NB" if action in ["MUA", "NB", "BUY"] else "NS"

        await update.message.reply_text(f"🚀 Đang gửi lệnh **{action} {volume:,} {symbol}** giá **{price:,.2f}**...")
        success = execute_bot_trade(side=side, symbol=symbol, price=price, volume=volume)

        if success:
            await update.message.reply_text(f"✅ Đã đặt lệnh thành công cho {symbol}.")
        else:
            await update.message.reply_text("❌ Không thể kết nối tới Ami X.")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"⚠️ Phát sinh lỗi mạng: {context.error}")


if __name__ == "__main__":
    print("🚀 Đang khởi chạy Telegram Bot AI FinBot...")
    app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("trade", trade_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), analyze_ticker))
    app.add_error_handler(global_error_handler)

    print("✅ Bot đã sẵn sàng nhận lệnh từ Telegram!")
    app.run_polling(poll_interval=1.0, timeout=30)
from threading import Thread
from flask import Flask

# Tạo web server nhẹ để giữ Render không báo lỗi Port
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    # Render sẽ tự cấp biến môi trường PORT, nếu không có thì mặc định 8080
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    keep_alive()  # Khởi chạy web server song song
    print("🚀 Đang khởi chạy Telegram Bot AI FinBot...")
    # ... các dòng app.add_handler và app.run_polling giữ nguyên