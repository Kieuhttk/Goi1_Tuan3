# ==============================================================================
# MODULE: data_realtime.py
# Chức năng:
#   - Lấy dữ liệu OHLCV Realtime (Ưu tiên API DNSE Entrade, Backup VnStock3 Quote)
#   - Tính toán các chỉ báo TA (EMA20, EMA50, RSI14, Vol MA20)
#   - Trả về DataFrame hoặc Dictionary phục vụ phân tích kỹ thuật
# ==============================================================================
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import VnStock3 làm Nguồn Dự Phòng (Backup)
try:
    from vnstock import Quote
except ImportError:
    Quote = None


# ==============================================================================
# 1. HÀM LẤY DỮ LIỆU NẾN OHLCV (DNSE API PRIMARY + VNSTOCK BACKUP)
# ==============================================================================
def get_realtime_ohlcv(symbol: str, limit: int = 60, resolution: str = "1D", interval: str = None, **kwargs) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV. 
    Lần 1: Gọi Public API Entrade/DNSE.
    Lần 2 (Backup): Gọi VnStock nếu DNSE lỗi/timeout.
    
    * Chấp nhận cả 'resolution' lẫn 'interval' hoặc các tham số thừa kwargs để tránh lỗi TypeError.
    """
    symbol = symbol.upper()
    # Nếu caller truyền 'interval' thay vì 'resolution', ưu tiên lấy interval
    res_key = interval if interval else resolution

    df = _fetch_dnse_ohlcv(symbol, limit, res_key)
    
    # Nếu DNSE thất bại -> Dùng VnStock làm phương án dự phòng
    if df is None or df.empty:
        df = _fetch_vnstock_ohlcv(symbol, limit, res_key)

    return df


def _fetch_dnse_ohlcv(symbol: str, limit: int = 60, resolution: str = "1D") -> pd.DataFrame:
    """Nguồn chính: Entrade / DNSE Charting API."""
    try:
        to_time = int(time.time())
        # Lấy khoảng thời gian trước đó ~100 ngày để đảm bảo đủ dữ liệu tính EMA50
        from_time = int((datetime.now() - timedelta(days=limit * 2)).timestamp())

        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
        params = {
            "symbol": symbol,
            "from": from_time,
            "to": to_time,
            "resolution": "1D" if resolution in ["1D", "D", "day"] else resolution
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        res = requests.get(url, params=params, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "t" in data and len(data["t"]) > 0:
                df = pd.DataFrame({
                    "time": pd.to_datetime(data["t"], unit="s"),
                    "open": data["o"],
                    "high": data["h"],
                    "low": data["l"],
                    "close": data["c"],
                    "volume": data["v"]
                })
                # Đảm bảo chuẩn hóa đơn vị giá khớp hệ thống (VNĐ)
                if df["close"].iloc[-1] < 1000:
                    df["open"] *= 1000
                    df["high"] *= 1000
                    df["low"] *= 1000
                    df["close"] *= 1000

                return df.tail(limit).reset_index(drop=True)
    except Exception as e:
        print(f"⚠️ DNSE API Timeout/Error cho mã {symbol}: {e}. Đang chuyển sang VnStock Backup...")
    
    return None


def _fetch_vnstock_ohlcv(symbol: str, limit: int = 60, resolution: str = "1D") -> pd.DataFrame:
    """Nguồn dự phòng: VnStock 3 Quote (Xoay vòng VCI -> TCBS)."""
    if Quote is None:
        print("❌ Chưa cài đặt thư viện vnstock.")
        return None

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=int(limit * 2.5))).strftime("%Y-%m-%d")
    sources = ["VCI", "TCBS"]

    for src in sources:
        try:
            quote = Quote(symbol=symbol, source=src)
            df = quote.history(start=start_date, end=end_date, interval="1D")

            if df is not None and not df.empty:
                df = df.rename(columns={
                    "time": "time", "open": "open", "high": "high",
                    "low": "low", "close": "close", "volume": "volume"
                })
                # Chuẩn hóa giá về đơn vị VNĐ nếu dữ liệu trả về theo ngàn đồng
                if df["close"].iloc[-1] < 1000:
                    df["close"] *= 1000
                    df["open"] *= 1000
                    df["high"] *= 1000
                    df["low"] *= 1000

                return df.tail(limit).reset_index(drop=True)
        except Exception as e:
            print(f"⚠️ Nguồn VnStock ({src}) lỗi cho mã {symbol}: {e}")
            continue

    return None


# ==============================================================================
# 2. HÀM TÍNH TOÁN CÁC CHỈ BÁO KĨ THUẬT (TA)
# ==============================================================================
def calculate_realtime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Tính các đường EMA20, EMA50, RSI14, Vol MA20 trên DataFrame."""
    if df is None or df.empty or len(df) < 20:
        return df

    df = df.copy()

    # EMA 20 & EMA 50
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    # Khối lượng trung bình 20 phiên (Vol MA20)
    df["vol_ma20"] = df["volume"].rolling(window=20).mean()

    # RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    rs = gain / loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    return df


# ==============================================================================
# 3. HÀM TRẢ VỀ DICTIONARY CHỈ BÁO REALTIME MỚI NHẤT
# ==============================================================================
def get_realtime_indicators(symbol: str) -> dict:
    """
    Hàm tiện ích trả về 1 Dictionary duy nhất chứa toàn bộ chỉ báo kỹ thuật 
    của nến gần nhất để các module khác dễ trích xuất.
    """
    df = get_realtime_ohlcv(symbol, limit=60)
    if df is None or df.empty:
        return {}

    df_ind = calculate_realtime_indicators(df)
    latest = df_ind.iloc[-1]

    close_val = float(latest.get("close", 0.0))
    vol_val = float(latest.get("volume", 0.0))
    vol_ma20_val = float(latest.get("vol_ma20", 1.0)) if pd.notna(latest.get("vol_ma20")) else 1.0
    vol_ratio = (vol_val / vol_ma20_val) if vol_ma20_val > 0 else 0.0

    return {
        "symbol": symbol.upper(),
        "close": close_val,
        "ema20": float(latest.get("ema20", 0.0)),
        "ema50": float(latest.get("ema50", 0.0)),
        "rsi14": float(latest.get("rsi14", 0.0)),
        "volume": vol_val,
        "vol_ma20": vol_ma20_val,
        "volume_ratio": vol_ratio,
        "updated_at": latest.get("time")
    }