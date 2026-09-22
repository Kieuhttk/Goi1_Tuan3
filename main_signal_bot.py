# ==============================================================================
# MODULE: main_signal_bot.py
# Chức năng:
#   - Tự động quét danh mục cổ phiếu theo thời gian thực (Realtime)
#   - Tích hợp bộ lọc Kỹ thuật (EMA, RSI, Vol) + Cơ bản (FA)
#   - Phát tín hiệu Mua/Bán trực tiếp qua Telegram theo kế hoạch Backtest tối ưu
# ==============================================================================
import time
from data_fundamental import (
    get_clean_financial_data,
    fundamental_signal,
    evaluate_sell_scenarios
)
from data_realtime import get_realtime_indicators
from telegram_bot import send_telegram_signal

# PORTFOLIO GIẢ ĐỊNH (Mã cổ phiếu & Giá vốn để quản trị rủi ro)
PORTFOLIO_POSITIONS = {
    "HPG": 26500,  # Đang nắm giữ HPG giá vốn 26,500 VNĐ
    "SSI": None,   # Chưa sở hữu
    "VNM": 68000   # Đang nắm giữ VNM giá vốn 68,000 VNĐ
}


def calculate_trade_plan(entry_price: float) -> dict:
    """
    Tính toán chi tiết các mức giá cụ thể theo % Kế hoạch Quản trị vốn:
    - Vùng giá mua: Entry +/- 1%
    - Cắt lỗ mềm (-7%), Cắt lỗ cứng (-10%)
    - Chốt lời Từng phần (+15%), Chốt lời Toàn bộ (+25%)
    """
    return {
        "buy_zone_min": round(entry_price * 0.99, -2),
        "buy_zone_max": round(entry_price * 1.01, -2),
        "stop_loss_soft": round(entry_price * 0.93, -2),
        "stop_loss_hard": round(entry_price * 0.90, -2),
        "take_profit_1": round(entry_price * 1.15, -2),
        "take_profit_2": round(entry_price * 1.25, -2)
    }


def scan_and_notify_signal(symbol: str, mode: str = "than_trong"):
    symbol = symbol.upper().strip()
    print(f"\n==================================================")
    print(f"🔍 BOT ĐANG TÌM TÍN HIỆU CHO MÃ: {symbol} (Mode: {mode.upper()})")
    print(f"==================================================")

    # --- 1. PHÂN TÍCH TÀI CHÍNH CƠ BẢN (FA) ---
    fund_data = get_clean_financial_data(symbol)
    fund_decision = fundamental_signal(fund_data, mode=mode)

    # --- 2. PHÂN TÍCH KỸ THUẬT REALTIME (TA) ---
    ta_data = get_realtime_indicators(symbol)
    if not ta_data:
        print(f"❌ Không thể lấy dữ liệu kỹ thuật Realtime cho mã {symbol}.")
        return

    current_price = ta_data.get("close", 0.0)
    ema20 = ta_data.get("ema20", 0.0)
    ema50 = ta_data.get("ema50", 0.0)
    rsi14 = ta_data.get("rsi14", 0.0)
    vol_ratio = ta_data.get("volume_ratio", 0.0)
    
    entry_price = PORTFOLIO_POSITIONS.get(symbol)

    # --- 3. KIỂM TRẢ BỘ LỌC 4 KỊCH BẢN BÁN (ƯU TIÊN BẢO VỆ VỐN) ---
    sell_eval = evaluate_sell_scenarios(
        symbol=symbol,
        current_price=current_price,
        ta_data=ta_data,
        fund_data=fund_data,
        entry_price=entry_price
    )

    if sell_eval["signal"] == "SELL":
        print(f"🚨 [CẢNH BÁO BÁN] {symbol} | Lý do: {sell_eval['reason']}")
        # SỬA LỖI TRUYỀN THAM SỐ: Đưa về tham số chuẩn của telegram_bot.py
        send_telegram_signal(
            symbol=symbol,
            signal_type=f"SELL ({sell_eval['scenario']})",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data,
            trade_plan=sell_eval['reason']  # Nội dung thông báo bán chi tiết
        )
        return

    # --- 4. TỐI ƯU ĐIỀU KIỆN MUA THEO BACKTEST (TĂNG WIN RATE) ---
    # 1. Xu hướng Tăng: Giá > EMA20 > EMA50
    is_uptrend_alignment = (current_price > ema20) and (ema20 > ema50)
    # 2. Xác nhận dòng tiền: Volume >= 1.2x MA20 (Tối ưu thay vì 1.5x)
    is_volume_confirmed = vol_ratio >= 1.2
    # 3. RSI Vùng tích lũy tăng tốc: 45 <= RSI <= 60 (Tối ưu tránh đu đỉnh)
    is_rsi_safe = 45.0 <= rsi14 <= 60.0

    if fund_decision == "BUY" and is_uptrend_alignment and is_volume_confirmed and is_rsi_safe:
        pct_above_ema20 = ((current_price - ema20) / ema20) * 100.0 if ema20 > 0 else 0.0
        
        # Tạo chuỗi Kế hoạch Giao dịch định dạng rõ ràng
        trade_plan_dict = calculate_trade_plan(entry_price=current_price)
        plan_str = (
            f"• Vùng mua: {trade_plan_dict['buy_zone_min']:,.0f} - {trade_plan_dict['buy_zone_max']:,.0f}\n"
            f"• Cắt lỗ (Soft/Hard): {trade_plan_dict['stop_loss_soft']:,.0f} / {trade_plan_dict['stop_loss_hard']:,.0f}\n"
            f"• Chốt lời (TP1/TP2): {trade_plan_dict['take_profit_1']:,.0f} / {trade_plan_dict['take_profit_2']:,.0f}"
        )

        # Xây dựng danh sách Lý do Kỹ thuật
        tech_reasons_str = (
            f"1. Giá ({current_price:,.0f}) > EMA20 ({ema20:,.0f}) (+{pct_above_ema20:.1f}%)\n"
            f"2. Vol bùng nổ đạt {vol_ratio:.2f}x so với MA20\n"
            f"3. RSI(14) = {rsi14:.1f} (Vùng tích lũy bùng nổ 45-60)\n"
            f"4. FA đạt chuẩn chế độ {mode.upper()}"
        )

        print(f"🎯 [PHÁT HIỆN ĐIỂM MUA BACKTEST] {symbol} | Giá: {current_price:,.0f}")
        
        # SỬA LỖI TRUYỀN THAM SỐ Telegram chuẩn hóa
        send_telegram_signal(
            symbol=symbol,
            signal_type="BUY",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data,
            technical_reasons=tech_reasons_str,
            trade_plan=plan_str
        )
    else:
        print(f"⏳ Mã {symbol}: Không thỏa mãn bộ điều kiện Backtest tối ưu.")


if __name__ == "__main__":
    WATCH_LIST = ["HPG", "SSI", "VNM"]
    print("🤖 Telegram Signal Bot đã sẵn sàng quét danh mục...")
    
    for ticker in WATCH_LIST:
        scan_and_notify_signal(ticker, mode="than_trong")
        time.sleep(2)