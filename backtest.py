import datetime
import pandas as pd
from vnstock.api.quote import Quote

# =========================================================
# CẤU HÌNH FINBOT - CHIẾN LƯỢC MEAN REVERSION (BẮT ĐÁY SIDEWAY)
# =========================================================
INITIAL_CAPITAL = 100_000_000
WATCHLIST = ["HPG", "SSI", "VNM", "ACB"]
COMMISSION = 0.0015             # 0.15% / chiều
MAX_POSITION_RATIO = 0.20       # Tối đa 20% / mã

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=180)
START_DATE_STR = start_date.strftime("%Y-%m-%d")
END_DATE_STR = end_date.strftime("%Y-%m-%d")

def calculate_ta(df):
    # MA20 & Bollinger Bands
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['STD20'] = df['close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD20'] * 2.0)
    df['Lower_Band'] = df['MA20'] - (df['STD20'] * 2.0)
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    return df

results = []

for symbol in WATCHLIST:
    try:
        q = Quote(symbol=symbol, source='VCI')
        df = q.history(start=START_DATE_STR, end=END_DATE_STR, interval='1D')
        
        if df is None or df.empty or len(df) < 50:
            continue
            
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time').reset_index(drop=True)
        df = calculate_ta(df)

        position = 0          
        buy_price = 0.0
        trades = []
        cash = INITIAL_CAPITAL * MAX_POSITION_RATIO 

        for i in range(20, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            price = row['close']
            date_str = row['time'].strftime('%Y-%m-%d')

            # TÍN HIỆU MUA MEAN REVERSION (BẮT ĐÁY BIÊN DƯỚI)
            # 1. Giá tiệm cận / rớt khỏi dải Bollinger Band dưới HOẶC RSI quá bán (RSI <= 42)
            near_lower_bb = price <= (row['Lower_Band'] * 1.01)
            rsi_oversold = row['RSI14'] <= 42
            
            # 2. Nến xanh xác nhận rút chân / đảo chiều ngắn hạn
            rebound_candle = (price > row['open']) and (row['RSI14'] > prev_row['RSI14'])

            is_buy_signal = (near_lower_bb or rsi_oversold) and rebound_candle

            # THỰC THI MUA
            if position == 0 and is_buy_signal:
                max_buy_amount = cash * (1 - COMMISSION)
                position = int(max_buy_amount // price)
                if position > 0:
                    buy_price = price
                    cost = position * buy_price * (1 + COMMISSION)
                    cash -= cost
                    trades.append({'type': 'BUY', 'date': date_str, 'price': buy_price, 'shares': position})

            # THỰC THI BÁN (CHỐT LỜI KHI CHẠM ĐƯỜNG GIỮA MA20 HOẶC RSI HỒI PHỤC)
            elif position > 0:
                pnl_pct = (price - buy_price) / buy_price

                # Chốt lời chủ động khi giá chạm lại đường trung bình MA20 hoặc RSI >= 56
                is_take_profit = (price >= row['MA20']) or (row['RSI14'] >= 56) or (pnl_pct >= 0.04)
                
                # Cắt lỗ ngắn nghiêm ngặt -3.0%
                is_stop_loss = pnl_pct <= -0.03

                if is_take_profit or is_stop_loss:
                    sell_price = price
                    revenue = position * sell_price * (1 - COMMISSION)
                    cash += revenue
                    net_pnl = pnl_pct - (2 * COMMISSION)
                    trades.append({'type': 'SELL', 'date': date_str, 'price': sell_price, 'pnl_pct': net_pnl * 100})
                    position = 0

        # TỔNG KẾT
        final_val = cash + (position * df.iloc[-1]['close'] * (1 - COMMISSION))
        profit_pct = ((final_val - (INITIAL_CAPITAL * MAX_POSITION_RATIO)) / (INITIAL_CAPITAL * MAX_POSITION_RATIO)) * 100
        
        num_trades = len(trades) // 2
        winning_trades = len([t for t in trades if t.get('type') == 'SELL' and t.get('pnl_pct', 0) > 0])
        win_rate = round((winning_trades / num_trades) * 100, 2) if num_trades > 0 else 0.0

        results.append({
            'Ticker': symbol,
            'FA Status': 'PASS',
            'Số lệnh': num_trades,
            'Lợi nhuận (%)': round(profit_pct, 2),
            'Tỷ lệ thắng (%)': win_rate
        })

    except Exception as e:
        print(f"❌ Lỗi khi backtest mã {symbol}: {e}")

# =========================================================
# BÁO CÁO KẾT QUẢ
# =========================================================
print("=" * 60)
print("📌 KẾT QUẢ BACKTEST MEAN REVERSION (BOLLINGER BANDS + RSI)")
print("=" * 60)
res_df = pd.DataFrame(results)
print(res_df.to_string(index=False))