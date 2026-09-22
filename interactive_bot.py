# ==============================================================================
# MODULE: interactive_bot.py
# Chức năng:
#   - Giao diện dòng lệnh tương tác với AI FinBot
#   - Phân tích kỹ thuật (EMA20, EMA50, RSI14, Vol Ratio) & Cơ bản (FA)
#   - Đưa ra Khuyến nghị MUA/BÁN chuẩn hóa theo thuật toán Backtest tối ưu
# ==============================================================================
import sys
import pandas as pd
from data_fundamental import get_clean_financial_data, fundamental_signal, evaluate_sell_scenarios
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
    # Đưa limit lên 150 nến để EMA50 hội tụ chuẩn xác nhất
    raw_ohlcv = get_realtime_ohlcv(symbol, limit=150)
    
    if safe_check_df(raw_ohlcv):
        df_price = calculate_realtime_indicators(raw_ohlcv)
    else:
        df_price = pd.DataFrame()

    # --- 2. LẤY DỮ LIỆU TÀI CHÍNH CƠ BẢN (FA) ---
    fa_data = get_clean_financial_data(symbol)

    # --- 3. TRÍCH XUẤT CÁC CHỈ SỐ KỸ THUẬT & TÍNH TÍN HIỆU MUA/BÁN ---
    if safe_check_df(df_price) and len(df_price) >= 1:
        latest_row = df_price.iloc[-1]
        
        close_price = latest_row.get('close', 0.0)
        open_price = latest_row.get('open', 0.0)
        high_price = latest_row.get('high', 0.0)
        low_price = latest_row.get('low', 0.0)
        volume = latest_row.get('volume', 0.0)
        
        rsi_val = latest_row.get('rsi14', 0.0)
        # SỬA LỖI KEYERROR: Thay sma20/sma50 thành ema20/ema50
        ema20_val = latest_row.get('ema20', 0.0)
        ema50_val = latest_row.get('ema50', 0.0)
        vol_ma20 = latest_row.get('vol_ma20', 1.0)
        
        vol_ratio = (volume / vol_ma20) if vol_ma20 > 0 else 0.0

        # TẠO TÍN HIỆU ĐỒNG BỘ BACKTEST
        fa_buy_pass = (fundamental_signal(fa_data, mode="than_trong") == "BUY")
        
        # ĐIỀU KIỆN MUA TỐI ƯU TỪ BACKTEST:
        # 1. Xu hướng Tăng: Giá > EMA20 > EMA50
        # 2. RSI Tích cực: 45 <= RSI <= 60 (Không mua vùng quá mua)
        # 3. Dòng tiền xác nhận: Volume >= 1.2x VolMA20
        # 4. Nền tảng FA đạt chuẩn
        if (close_price > ema20_val > ema50_val) and (45.0 <= rsi_val <= 60.0) and (vol_ratio >= 1.2) and fa_buy_pass:
            action_recommendation = "🟢 MUA MỚI (BUY SIGNAL)"
            tech_signal = "BULLISH (Tăng giá mạnh & Khối lượng bùng nổ)"
        elif close_price > ema20_val > ema50_val:
            action_recommendation = "🟡 THEO DÕI / NẮM GIỮ (HOLD)"
            tech_signal = "BULLISH (Đang trong Uptrend nhưng thiếu Vol hoặc chưa đạt chuẩn FA)"
        elif close_price < ema50_val or rsi_val < 40:
            action_recommendation = "🔴 BÁN / KHÔNG MUA (SELL / AVOID)"
            tech_signal = "BEARISH (Xử lý vi phạm xu hướng / Downtrend)"
        else:
            action_recommendation = "⚪ QUAN SÁT (NEUTRAL)"
            tech_signal = "NEUTRAL (Đang đi ngang tích lũy)"

        # KIỂM TRA TÍN HIỆU BÁN THEO 4 KỊCH BẢN QUẢN TRỊ RỦI RO
        ta_dict = {"ema20": ema20_val, "ema50": ema50_val, "rsi14": rsi_val, "volume_ratio": vol_ratio}
        sell_eval = evaluate_sell_scenarios(symbol, close_price, ta_dict, fa_data)
        
        if sell_eval["signal"] == "SELL":
            action_recommendation = f"🚨 KHUYẾN NGHỊ BÁN: {sell_eval['scenario']}"

    else:
        close_price = open_price = high_price = low_price = volume = 0
        rsi_val = ema20_val = ema50_val = vol_ratio = 0.0
        tech_signal = "KHÔNG ĐỦ DỮ LIỆU GIÁ"
        action_recommendation = "N/A"
        sell_eval = {"reason": "Không có dữ liệu"}

    # --- 4. TRÍCH XUẤT CÁC CHỈ SỐ TÀI CHÍNH (FA) ---
    if isinstance(fa_data, dict) and fa_data:
        period = fa_data.get('period', 'N/A')
        roe = fa_data.get('roe_annualized', 0.0)
        debt_equity = fa_data.get('debt_equity', 0.0)
        gross_margin = fa_data.get('gross_margin', 0.0)
        net_profit = fa_data.get('net_profit_bil', 0.0)
        is_bank = fa_data.get('is_bank', False)
        nim_ratio = fa_data.get('nim_ratio', 0.0)
    else:
        period = "N/A"
        roe = debt_equity = gross_margin = net_profit = nim_ratio = 0.0
        is_bank = False

    # --- 5. HIỂN THỊ BÁO CÁO KẾT QUẢ TRỰC QUAN ---
    print("\n" + "=" * 65)
    print(f"📈 BÁO CÁO PHÂN TÍCH TỔNG HỢP (BACKTEST MATCH): #{symbol}")
    print(f"🗓️  Kỳ BCTC gần nhất: {period}")
    print("=" * 65)

    print("\n💵 1. CHỈ BÁO KỸ THUẬT & DỒNG TIỀN (TA):")
    print(f" • Giá đóng cửa: {format_number(close_price, 0)} VNĐ")
    print(f" • Biên độ phiên (High/Low): {format_number(high_price, 0)} / {format_number(low_price, 0)} VNĐ")
    print(f" • Khối lượng / Trung bình 20 phiên: {format_number(volume, 0)} (Gấp {format_number(vol_ratio, 2)}x MA20)")
    print(f" • Chỉ số RSI (14 kỳ): {format_number(rsi_val, 1)}")
    print(f" • Đường EMA 20 / EMA 50: {format_number(ema20_val, 0)} / {format_number(ema50_val, 0)}")
    print(f" 🎯 Trạng thái kỹ thuật: {tech_signal}")

    print("\n📊 2. SỨC KHỎE TÀI CHÍNH CƠ BẢN (FA):")
    print(f" • Lợi nhuận sau thuế: {format_number(net_profit, 2)} Tỷ VNĐ")
    print(f" • ROE (Quy năm): {format_number(roe, 2)}%")
    if is_bank:
        print(f" • Biên lãi thuần (NIM): {format_number(nim_ratio, 2)}% (Mã Ngân Hàng)")
    else:
        print(f" • Biên lợi nhuận gộp: {format_number(gross_margin, 2)}%")
        print(f" • Đòn bẩy tài chính (D/E): {format_number(debt_equity, 2)} lần")

    print("\n⚡ 3. KHUYẾN NGHỊ TỪ THUẬT TOÁN (STRATEGY DECISION):")
    print(f" 🔥 HÀNH ĐỘNG: {action_recommendation}")
    if sell_eval.get("signal") == "SELL":
        print(f" ⚠️ Lý do chi tiết: {sell_eval.get('reason')}")
    print("=" * 65 + "\n")


def main_interactive_loop():
    """Vòng lặp tương tác chính của Chatbot."""
    print("=" * 65)
    print("🚀 CHÀO MỪNG BẠN ĐẾN VỚI TRỢ LÝ PHÂN TÍCH CHỨNG KHOÁN (AI FINBOT)")
    print("Gõ mã cổ phiếu (ví dụ: FPT, HPG, MBB) để phân tích.")
    print("Gõ 'exit' hoặc 'quit' để thoát chương trình.")
    print("=" * 65)

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