import re
import requests
import pandas as pd
from vnstock import Finance, Quote

# Cấu hình địa chỉ API Ami X
AMI_X_BASE_URL = "http://localhost:7979"


# ==============================================================================
# 1. BỘ HÀM XỬ LÝ BÁO CÁO TÀI CHÍNH (FA)
# ==============================================================================
def parse_quarter_key(col_name: str):
    """Chuyển chuỗi định dạng quý thành tuple (năm, quý) để sắp xếp."""
    col_str = str(col_name).strip()
    match = re.search(r'(\d{4})[^\d]*Q?(\d)', col_str, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def clean_number_val(val) -> float:
    """Chuyển đổi an toàn giá trị từ chuỗi/số sang float."""
    if pd.isna(val) or val is None:
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace(',', '').replace('%', '').strip()
        f = float(val)
        return f if f == f else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_sorted_time_cols(df: pd.DataFrame) -> list:
    """Lấy danh sách các cột quý sắp xếp từ mới nhất đến cũ nhất."""
    time_cols = [c for c in df.columns if parse_quarter_key(c) != (0, 0)]
    return sorted(time_cols, key=parse_quarter_key, reverse=True)


def extract_first_valid_value(df: pd.DataFrame, target_col: str, keywords: list) -> tuple:
    """
    Tìm dòng khớp keyword, sau đó duyệt qua từng cột quý (từ mới đến cũ)
    để lấy giá trị KHÁC 0 đầu tiên. Trả về (value, quarter_name).
    """
    time_cols = get_sorted_time_cols(df)
    if not time_cols:
        return 0.0, ""

    for kw in keywords:
        mask = df[target_col].astype(str).str.strip().str.lower() == kw.lower()
        matched = df[mask]
        
        if matched.empty:
            mask = df[target_col].astype(str).str.lower().str.contains(kw.lower(), regex=False)
            matched = df[mask]

        if not matched.empty:
            row = matched.iloc[0]
            for q_col in time_cols:
                val = clean_number_val(row[q_col])
                if val != 0.0:
                    return val, q_col

    return 0.0, time_cols[0] if time_cols else ""


def get_clean_financial_data(symbol: str) -> dict:
    """Lấy dữ liệu chỉ số tài chính cơ bản đã chuẩn hóa và tính toán chuẩn xác D/E."""
    try:
        sources = ["VCI", "TCBS", "KBS"]
        
        roe = 0.0
        debt_equity = 0.0
        gross_margin = 0.0
        net_profit_raw = 0.0
        latest_period = ""

        for src in sources:
            try:
                fin = Finance(symbol=symbol.upper(), source=src)
                ratio = fin.ratio(period="quarter", lang="vi")
                income = fin.income_statement(period="quarter", lang="vi")
                
                try:
                    balance = fin.balance_sheet(period="quarter", lang="vi")
                except Exception:
                    balance = None

                if ratio is None or ratio.empty or income is None or income.empty:
                    continue

                if 'item' not in ratio.columns:
                    ratio = ratio.reset_index()
                if 'item' not in income.columns:
                    income = income.reset_index()

                item_col_r = 'item' if 'item' in ratio.columns else ratio.columns[0]
                item_col_i = 'item' if 'item' in income.columns else income.columns[0]

                # 1. Trích xuất Lợi nhuận sau thuế & Quý chốt
                if net_profit_raw == 0.0:
                    net_profit_raw, latest_period = extract_first_valid_value(
                        income, item_col_i, 
                        ['Lợi nhuận của Cổ đông của Công ty mẹ', 'Lãi/(lỗ) thuần sau thuế', 'Lợi nhuận sau thuế']
                    )

                # 2. Trích xuất ROE (%)
                if roe == 0.0:
                    roe, _ = extract_first_valid_value(
                        ratio, item_col_r, 
                        ['ROE (%)', 'ROE', 'Tỷ suất lợi nhuận trên vốn chủ sở hữu']
                    )

                # 3. Tính D/E (Tổng nợ / Vốn chủ sở hữu) chuẩn từ Balance Sheet
                if debt_equity == 0.0 and balance is not None and not balance.empty:
                    if 'item' not in balance.columns:
                        balance = balance.reset_index()
                    item_col_b = 'item' if 'item' in balance.columns else balance.columns[0]
                    
                    total_liabilities, _ = extract_first_valid_value(
                        balance, item_col_b, ['NỢ PHẢI TRẢ', 'Tổng nợ phải trả', 'Liabilities']
                    )
                    equity_val, _ = extract_first_valid_value(
                        balance, item_col_b, ['VỐN CHỦ SỞ HỮU', 'Vốn chủ sở hữu', 'Equity']
                    )
                    
                    if equity_val > 0:
                        debt_equity = total_liabilities / equity_val

                # Fallback: Trích xuất D/E từ bảng ratio nếu Balance Sheet không lấy được
                if debt_equity == 0.0:
                    debt_equity, _ = extract_first_valid_value(
                        ratio, item_col_r, 
                        ['Nợ phải trả/Vốn chủ', 'Nợ/Vốn chủ', 'Nợ trên vốn chủ', 'Nợ/Vốn chủ sở hữu', 'D/E']
                    )
                    if debt_equity > 10.0:
                        debt_equity = debt_equity / 100.0

                # 4. Trích xuất Biên lợi nhuận gộp (%)
                if gross_margin == 0.0:
                    gross_margin, _ = extract_first_valid_value(
                        ratio, item_col_r, 
                        ['Biên LN gộp (%)', 'Biên lợi nhuận gộp', 'Gross Margin']
                    )

                if gross_margin == 0.0:
                    gp, _ = extract_first_valid_value(income, item_col_i, ['Lợi nhuận gộp'])
                    rev, _ = extract_first_valid_value(income, item_col_i, ['Doanh thu thuần'])
                    if rev > 0:
                        gross_margin = (gp / rev) * 100

                if roe != 0.0 and net_profit_raw != 0.0 and debt_equity != 0.0:
                    break

            except Exception:
                continue

        net_profit_bil = net_profit_raw / 1e9 if abs(net_profit_raw) > 1e6 else net_profit_raw

        return {
            "ticker": symbol.upper(),
            "period": latest_period if latest_period else "N/A",
            "roe_annualized": round(roe, 2),
            "debt_equity": round(debt_equity, 2),
            "gross_margin": round(gross_margin, 2),
            "net_profit_bil": round(net_profit_bil, 2),
            "listed_status": "Normal"
        }

    except Exception as e:
        print(f"❌ Lỗi xử lý dữ liệu FA cho {symbol}: {e}")
        return {}


# ==============================================================================
# 2. BỘ HÀM LẤY GIÁ NẾN & CHỈ BÁO KỸ THUẬT (TA)
# ==============================================================================
def get_realtime_ohlcv(symbol: str, limit: int = 60, interval: str = "1D") -> pd.DataFrame:
    """Lấy dữ liệu nến OHLCV từ VCI."""
    try:
        quote = Quote(symbol=symbol.upper(), source="VCI")
        df = quote.history(interval=interval, start="2024-01-01")

        if df is not None and not df.empty:
            return df.tail(limit).reset_index(drop=True)
    except Exception as e:
        print(f"❌ Lỗi lấy dữ liệu giá mã {symbol}: {e}")

    return pd.DataFrame()


def calculate_realtime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Tính toán các chỉ báo kỹ thuật (EMA20, EMA50, RSI14 chuẩn TradingView)."""
    if df is None or df.empty or len(df) < 14:
        return df

    df = df.copy()
    close_col = "close" if "close" in df.columns else "Close"

    # EMA 20 & EMA 50
    df['ema20'] = df[close_col].ewm(span=20, adjust=False).mean()
    df['ema50'] = df[close_col].ewm(span=50, adjust=False).mean()
    df['sma20'] = df['ema20']

    # RSI 14 Wilders Smoothing
    delta = df[close_col].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean().replace(0, 0.00001)

    rs = avg_gain / avg_loss
    df['rsi14'] = 100 - (100 / (1 + rs))

    return df


# ==============================================================================
# 3. BỘ HÀM ĐẶT LỆNH AMI X
# ==============================================================================
def execute_bot_trade(side: str, symbol: str, price: float, volume: int) -> bool:
    """Gửi lệnh Mua ('NB') hoặc Bán ('NS') qua HTTP GET tới Ami X."""
    url = f"{AMI_X_BASE_URL}/trade"
    params = {
        "side": side.upper(),
        "symbol": symbol.upper(),
        "price": price,
        "volume": volume,
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            print(f"🚀 Đã gửi lệnh {side.upper()} {volume:,} {symbol.upper()} giá {price:,.2f}")
            return True
    except Exception as e:
        print(f"❌ Lỗi kết nối Ami X: {e}")

    return False


if __name__ == "__main__":
    print("🚀 Đang kiểm tra chạy thử cho VIC...")
    res_fa = get_clean_financial_data("VIC")
    print("FA Data:", res_fa)

    df_price = get_realtime_ohlcv("VIC", limit=20)
    if not df_price.empty:
        df_ind = calculate_realtime_indicators(df_price)
        print("\nTA Data (Phiên mới nhất):")
        print(df_ind[['close', 'ema20', 'rsi14']].tail(1))