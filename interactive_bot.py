import sys
import pandas as pd
from data_fundamental import get_clean_financial_data
from data_realtime import calculate_realtime_indicators, get_realtime_ohlcv


def safe_check_df(df) -> bool:
    """Kiểm tra an toàn DataFrame xem có hợp lệ và chứa dữ liệu không."""
    return df is not None and isinstance(df, pd.DataFrame) and not df.empty


def format_number(val, decimal_places=2) -> str:
    """Định dạng số hiển thị cho gọn gàng."""
    try:
        val = float(val)
        if decimal_places == 0:
            return f"{val:,.0f}"
        return f"{val:,.{decimal_places}f}"
    except (ValueError, TypeError):
        return "N/A"


def analyze_stock(symbol: str):
    """Hàm phân tích kỹ thuật và tài chính tổng hợp cho một mã cổ phiếu."""
    symbol = symbol.upper().strip()
    print(f"\n🤖 [AI FinBot] Đang phân tích chuyên sâu mã #{symbol}...")

    # --- 1. LẤY & XỬ LÝ DỮ LIỆU GIÁ REAL-TIME (OHLCV) ---
    raw_ohlcv = get_realtime_ohlcv(symbol, limit=100)
    
    # SỬA LỖI TRITH VALUE: Kiểm tra safe_check_df thay vì 'if raw_ohlcv:'
    if safe_check_df(raw_ohlcv):
        df_price = calculate_realtime_indicators(raw_ohlcv)
    else:
        df_price = pd.DataFrame()

    # --- 2. LẤY DỮ LIỆU TÀI CHÍNH CƠ BẢN (FA) ---
    fa_data = get_clean_financial_data(symbol)

    # --- 3. TRÍCH XUẤT CÁC CHỈ SỐ KỸ THUẬT ---
    if safe_check_df(df_price) and len(df_price) >= 1:
        latest_row = df_price.iloc[-1]
        
        close_price = latest_row.get('close', 0.0)
        open_price = latest_row.get('open', 0.0)
        high_price = latest_row.get('high', 0.0)
        low_price = latest_row.get('low', 0.0)
        volume = latest_row.get('volume', 0)
        
        rsi_val = latest_row.get('rsi14', 0.0)
        sma20_val = latest_row.get('sma20', 0.0)
        sma50_val = latest_row.get('sma50', 0.0)
        
        # Đánh giá xu hướng kỹ thuật đơn giản
        tech_signal = "NEUTRAL (Trung lập)"
        if close_price > sma20_val > sma50_val and rsi_val > 50:
            tech_signal = "BULLISH (Tích cực / Tăng giá)"
        elif close_price < sma20_val < sma50_val or rsi_val < 35:
            tech_signal = "BEARISH (Tiêu cực / Giảm giá)"
    else:
        close_price = open_price = high_price = low_price = volume = 0
        rsi_val = sma20_val = sma50_val = 0.0
        tech_signal = "KHÔNG ĐỦ DỮ LIỆU GIÁ"

    # --- 4. TRÍCH XUẤT CÁC CHỈ SỐ TÀI CHÍNH (FA) ---
    if isinstance(fa_data, dict) and fa_data:
        period = fa_data.get('period', 'N/A')
        roe = fa_data.get('roe_annualized', 0.0)
        debt_equity = fa_data.get('debt_equity', 0.0)
        gross_margin = fa_data.get('gross_margin', 0.0)
        net_profit = fa_data.get('net_profit_bil', 0.0)
    else:
        period = "N/A"
        roe = debt_equity = gross_margin = net_profit = 0.0

    # --- 5. HIỂN THỊ BÁO CÁO KẾT QUẢ ---
    print("\n" + "=" * 60)
    print(f"📈 BÁO CÁO PHÂN TÍCH TỔNG HỢP: #{symbol}")
    print(f"🗓️  Kỳ báo cáo tài chính gần nhất: {period}")
    print("=" * 60)

    print("\n💵 1. THÔNG TIN GIÁ & CHỈ BÁO KỸ THUẬT:")
    print(f" • Giá đóng cửa gần nhất: {format_number(close_price, 0)} VNĐ")
    print(f" • Biên độ phiên (High/Low): {format_number(high_price, 0)} / {format_number(low_price, 0)} VNĐ")
    print(f" • Khối lượng giao dịch: {format_number(volume, 0)}")
    print(f" • Chỉ số RSI (14 kỳ): {format_number(rsi_val, 1)}")
    print(f" • Đường SMA 20 / SMA 50: {format_number(sma20_val, 0)} / {format_number(sma50_val, 0)}")
    print(f" 🎯 Tín hiệu kỹ thuật: {tech_signal}")

    print("\n📊 2. SỨC KHỎE TÀI CHÍNH CƠ BẢN (FA):")
    print(f" • Lợi nhuận sau thuế: {format_number(net_profit, 2)} Tỷ VNĐ")
    print(f" • ROE (Quy năm): {format_number(roe, 2)}%")
    print(f" • Biên lợi nhuận gộp: {format_number(gross_margin, 2)}%")
    print(f" • Nợ / Vốn chủ sở hữu (D/E): {format_number(debt_equity, 2)} lần")
    print("=" * 60 + "\n")


def main_interactive_loop():
    """Vòng lặp tương tác chính của Chatbot."""
    print("=" * 60)
    print("🚀 CHÀO MỪNG BẠN ĐẾN VỚI TRỢ LÝ PHÂN TÍCH CHỨNG KHOÁN (AI FINBOT)")
    print("Gõ mã cổ phiếu (ví dụ: VIC, VNM, FPT) để phân tích.")
    print("Gõ 'exit' hoặc 'quit' để thoát chương trình.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n👉 Nhập mã cổ phiếu cần kiểm tra: ").strip()
            
            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("👋 Cảm ơn bạn đã sử dụng AI FinBot. Tạm biệt!")
                sys.exit(0)

            # Thực hiện phân tích mã người dùng nhập
            analyze_stock(user_input)

        except KeyboardInterrupt:
            print("\n👋 Đã dừng chương trình. Tạm biệt!")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Có lỗi phát sinh trong quá trình xử lý: {e}")


if __name__ == "__main__":
    main_interactive_loop()