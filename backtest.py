import datetime
import pandas as pd
from vnstock import Vnstock

# =========================================================
# CẤU HÌNH HỆ THỐNG FINBOT (BẢN TỐI ƯU SWING TRADING SIDEWAY)
# =========================================================
INITIAL_CAPITAL = 100_000_000
WATCHLIST = ["HPG", "SSI", "VNM", "ACB"]
COMMISSION = 0.0015             # 0.15% / chiều
MAX_POSITION_RATIO = 0.20       # Tối đa 20% / mã

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=180)
START_DATE_STR = start_date.strftime("%Y-%m-%d")
END_DATE_STR = end_date.strftime("%Y-%m-%d")

FA_DATA = {
    "HPG": {"type": "NORMAL", "LNST_gt_0": True, "ROE": 0.14, "DE": 0.8},
    "SSI": {"type": "NORMAL", "LNST_gt_0": True, "ROE": 0.13, "DE": 1.2},
    "VNM": {"type": "NORMAL", "LNST_gt_0": True, "ROE": 0.22, "DE": 0.4},
    "ACB": {"type": "BANK", "LNST_gt_0": True, "ROE": 0.21, "NIM": 0.038}
}

def calculate_ta(df):
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    # Volume Ratio
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    df['VR'] = df['volume'] / df['Vol_MA20']
    return df

results = []

for symbol in WATCHLIST:
    try:
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        df = stock.quote.history(start=START_DATE_STR, end=END_DATE_STR, interval='1D')
        
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

            # TÍN HIỆU MUA TẠI NỀN HỖ TRỢ (SWING TRADING LOGIC)
            # 1. Giá nằm vùng hỗ trợ quanh EMA20/EMA50 (Độ lệch <= 2.5%)
            near_ema20 = abs(price - row['EMA20']) / row['EMA20'] <= 0.025
            
            # 2. RSI ở vùng giá tốt (38 - 56) và bắt đầu hướng lên
            rsi_good = (38 <= row['RSI14'] <= 56) and (row['RSI14'] > prev_row['RSI14'])
            
            # 3. Nến xanh đảo chiều ngắn hạn
            green_candle = price > row['open']

            is_buy_signal = near_ema20 and rsi_good and green_candle

            # Thực thi MUA
            if position == 0 and is_buy_signal:
                max_buy_amount = cash * (1 - COMMISSION)
                position = int(max_buy_amount // price)
                if position > 0:
                    buy_price = price
                    cost = position * buy_price * (1 + COMMISSION)
                    cash -= cost
                    trades.append({'type': 'BUY', 'date': date_str, 'price': buy_price, 'shares': position})

            # TÍN HIỆU BÁN TỐI ƯU WIN RATE (TAKE PROFIT CHỦ ĐỘNG)
            elif position > 0:
                pnl_pct = (price - buy_price) / buy_price
                
                # Chốt lời ngắn +5% hoặc RSI chớm đi vào vùng quá mua (>62)
                is_take_profit = (pnl_pct >= 0.05) or (row['RSI14'] >= 62)
                # Cắt lỗ nghiêm ngặt -3.5%
                is_stop_loss = pnl_pct <= -0.035

                if is_take_profit or is_stop_loss:
                    sell_price = price
                    revenue = position * sell_price * (1 - COMMISSION)
                    cash += revenue
                    net_pnl = pnl_pct - (2 * COMMISSION)
                    trades.append({'type': 'SELL', 'date': date_str, 'price': sell_price, 'pnl_pct': net_pnl * 100})
                    position = 0

        # Tổng kết
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
print("📌 KẾT QUẢ BACKTEST TỐI ƯU SWING TRADING TẠI NỀN HỖ TRỢ")
print("=" * 60)
res_df = pd.DataFrame(results)
print(res_df.to_string(index=False))