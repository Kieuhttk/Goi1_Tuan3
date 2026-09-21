import time
from data_realtime import get_realtime_ohlcv, calculate_realtime_indicators
from data_fundamental import get_stock_info, fundamental_signal
from telegram_bot import send_telegram_signal

def scan_and_notify_signal(symbol: str, mode: str = "than_trong"):
    print(f"\n==================================================")
    print(f"🔍 BOT ĐANG TÌM TÍN HIỆU CHO MÃ: {symbol.upper()}")
    print(f"==================================================")

    # 1. Phân tích cơ bản (FA)
    fund_data = get_stock_info(symbol)
    fund_decision = fundamental_signal(fund_data, mode=mode)

    # 2. Phân tích kỹ thuật (TA)
    df_price = get_realtime_ohlcv(symbol)
    if df_price.empty:
        print("❌ Không thể lấy dữ liệu Realtime.")
        return

    indicators = calculate_realtime_indicators(df_price)
    current_price = indicators.get("current_price", 0)
    ema20 = indicators.get("ema20", 0)
    rsi14 = indicators.get("rsi14", 0)

    # 3. Tổng hợp Logic phát Tín hiệu
    # Điều kiện MUA: FA đạt tiêu chuẩn + TA ủng hộ (Giá > EMA20 & RSI < 70)
    if fund_decision == "BUY" and current_price > ema20 and rsi14 < 70:
        print(f"🎯 PHÁT HIỆN ĐIỂM MUA CHO MÃ {symbol}!")
        send_telegram_signal(
            symbol=symbol,
            signal_type="BUY",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data
        )
    
    # Điều kiện BÁN: Giá đâm thủng EMA20
    elif current_price < ema20:
        print(f"⚠️ PHÁT HIỆN ĐIỂM BÁN/CẮT LỖ CHO MÃ {symbol}!")
        send_telegram_signal(
            symbol=symbol,
            signal_type="SELL",
            price=current_price,
            ema20=ema20,
            rsi=rsi14,
            fund_info=fund_data
        )
    else:
        print("⏳ Thị trường đang tích lũy / Chưa có tín hiệu mới.")


if __name__ == "__main__":
    # Danh sách các mã cổ phiếu trong danh mục theo dõi của Bot
    WATCH_LIST = ["HPG", "SSI", "VNM"]
    
    print("🤖 Telegram Signal Bot đã sẵn sàng quét danh mục...")
    
    for ticker in WATCH_LIST:
        scan_and_notify_signal(ticker, mode="mao_hiem")
        time.sleep(2)  # Nghỉ 2 giây giữa các mã để tránh dính spam API