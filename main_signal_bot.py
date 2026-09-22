# main_signal_bot.py
import time
from data_fundamental import (
    get_clean_financial_data,
    fundamental_signal,
    evaluate_sell_scenarios
)
from data_realtime import get_realtime_indicators
from telegram_bot import send_telegram_signal

# PORTFOLIO GIẢ ĐỊNH (Cổ phiếu đã Mua & Giá vốn)
PORTFOLIO_POSITIONS = {
    "HPG": 26500,  # Đang nắm giữ HPG giá vốn 26,500 VNĐ
    "SSI": None,   # Chưa sở hữu
    "VNM": 68000   # Đang nắm giữ VNM giá vốn 68,000 VNĐ
}

def calculate_trade_plan(entry_price: float) -> dict:
    """
    Tính toán chi tiết các mức giá cụ thể theo % Kế hoạch:
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
    symbol = symbol.upper()
    print(f"\n==================================================")
    print(f"🔍 BOT ĐANG TÌM TÍN HIỆU CHO MÃ: {symbol}")
    print(f"==================================================")

    # 1. Phân tích cơ bản (FA)
    fund_data = get_clean_financial_data(symbol)
    fund_decision = fundamental_signal(fund_data, mode=mode)

    # 2. Phân tích kỹ thuật (TA)
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

    # 3. KIỂM TRẢ BỘ LỌC 4 KỊCH BẢN BÁN (ƯU TIÊN HÀNG ĐẦU DỀ BẢO VỆ VỐN)
    sell_eval = evaluate_sell_scenarios(
        symbol=symbol,
        current_price=current_price,
        ta_data=ta_data,
        fund_data=fund_data,
        entry_price=entry_price
    )

    if sell_eval["signal"] == "SELL":
        print(f"🚨 [CẢNH BÁO BÁN] {symbol} | Lý do: {sell_eval['reason']}")
        send_telegram_signal(
            symbol=symbol,
            signal_type=f"SELL ({sell_eval['scenario']})",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data,
            extra_reason=sell_eval['reason']
        )
        return

    # 4. ĐÁNH GIÁ TÍN HIỆU MUA & TẠO LÝ DO KỸ THUẬT CHI TIẾT
    is_uptrend_alignment = (current_price > ema20) and (ema20 > ema50)
    is_volume_confirmed = vol_ratio >= 1.5
    is_rsi_safe = 50.0 <= rsi14 <= 70.0

    if fund_decision == "BUY" and is_uptrend_alignment and is_volume_confirmed and is_rsi_safe:
        pct_above_ema20 = ((current_price - ema20) / ema20) * 100.0
        
        # Xây dựng danh sách Lý do Kỹ thuật dạng liệt kê
        technical_reasons = [
            f"Giá ({current_price:,.0f}) nằm trên EMA20 ({ema20:,.0f}) +{pct_above_ema20:.1f}% (Đồng thuận Xu hướng tăng)",
            f"Khối lượng giao dịch đột biến đạt **{vol_ratio:.2f}x** so với Trung bình 20 phiên (MA20_vol)",
            f"Chỉ báo Động lượng RSI(14) đạt **{rsi14:.1f}** (Vùng mua tăng tốc an toàn 50-70)",
            f"Nền tảng Tài chính FA đạt chuẩn **{mode.upper()}** (ROE & LNST tăng trưởng)"
        ]

        # Tính toán Kế hoạch Giá cụ thể (Vùng Mua, Cắt Lỗ, Chốt Lời)
        trade_plan = calculate_trade_plan(entry_price=current_price)

        print(f"🎯 [PHÁT HIỆN ĐIỂM MUA] {symbol} | Giá: {current_price:,.0f}")
        
        send_telegram_signal(
            symbol=symbol,
            signal_type="BUY",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data,
            technical_reasons=technical_reasons,
            trade_plan=trade_plan
        )
    else:
        print(f"⏳ Mã {symbol}: Chưa có tín hiệu giao dịch mới.")


if __name__ == "__main__":
    WATCH_LIST = ["HPG", "SSI", "VNM"]
    print("🤖 Telegram Signal Bot đã sẵn sàng quét danh mục...")
    
    for ticker in WATCH_LIST:
        scan_and_notify_signal(ticker, mode="mao_hiem")
        time.sleep(2)