# ==============================================================================
# MODULE: data_realtime.py (MEAN REVERSION STRATEGY & VN-INDEX FILTER)
# ==============================================================================
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import zoneinfo

try:
    from vnstock import Quote
except ImportError:
    Quote = None

from config import TECHNICAL_STRATEGY


def get_realtime_ohlcv(symbol: str, limit: int = 150, resolution: str = "1D", interval: str = None, **kwargs) -> pd.DataFrame:
    symbol = symbol.upper()
    res_key = interval if interval else resolution

    # 1. Lấy dữ liệu nến lịch sử
    df = _fetch_dnse_ohlcv(symbol, limit, res_key)
    if df is None or df.empty:
        df = _fetch_vnstock_ohlcv(symbol, limit, res_key)

    # 2. Bắt buộc vá giá Realtime cho phiên hôm nay
    if df is not None and not df.empty:
        df = _patch_today_realtime_candle(symbol, df)

    return df


def _fetch_dnse_ohlcv(symbol: str, limit: int = 150, resolution: str = "1D") -> pd.DataFrame:
    try:
        to_time = int(time.time())
        from_time = int((datetime.now() - timedelta(days=int(limit * 2.2))).timestamp())

        url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
        params = {
            "symbol": symbol,
            "from": from_time,
            "to": to_time,
            "resolution": "1D" if resolution in ["1D", "D", "day"] else resolution
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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
                
                if len(df) > 0 and df["close"].iloc[-1] < 1000:
                    df["open"] *= 1000
                    df["high"] *= 1000
                    df["low"] *= 1000
                    df["close"] *= 1000

                return df.tail(limit).reset_index(drop=True)
    except Exception as e:
        print(f"⚠️ DNSE OHLCV Error: {e}")
    
    return None


def _fetch_vnstock_ohlcv(symbol: str, limit: int = 150, resolution: str = "1D") -> pd.DataFrame:
    if Quote is None:
        return None

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=int(limit * 2.5))).strftime("%Y-%m-%d")

    for src in ["VCI", "TCBS"]:
        try:
            quote = Quote(symbol=symbol, source=src)
            df = quote.history(start=start_date, end=end_date, interval="1D")

            if df is not None and not df.empty:
                df = df.rename(columns={
                    "time": "time", "open": "open", "high": "high",
                    "low": "low", "close": "close", "volume": "volume"
                })
                df["time"] = pd.to_datetime(df["time"])
                if len(df) > 0 and df["close"].iloc[-1] < 1000:
                    df["close"] *= 1000
                    df["open"] *= 1000
                    df["high"] *= 1000
                    df["low"] *= 1000

                return df.tail(limit).reset_index(drop=True)
        except Exception:
            continue

    return None


def _patch_today_realtime_candle(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    HÀM VÁ GIÁ REALTIME CHUẨN (HTTP REQUESTS THUẦN):
    Sử dụng trực tiếp API Bảng giá VPS/TCBS/DNSE không qua thư viện trung gian.
    """
    price, vol = 0.0, 0.0

    # Nguồn 1: API Bảng giá VPS / Direct Quote
    try:
        url_vps = f"https://bgapidatafeed.vps.com.vn/getliststockdata/{symbol}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url_vps, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                price = float(item.get("lastPrice", 0.0) or item.get("lastMatchedPrice", 0.0) or item.get("closePrice", 0.0))
                vol = float(item.get("lot", 0.0) or item.get("totalVol", 0.0))
                if price > 0:
                    print(f"🔍 [VPS Board API] Lấy thành công giá {symbol}: {price:,.0f}")
    except Exception as e:
        print(f"⚠️ VPS API error: {e}")

    # Nguồn 2: TCBS Stock Detail API
    if price == 0:
        try:
            url_tcbs = f"https://apipub.tcbs.com.vn/stock-insight/v1/stock/second-ticker?ticker={symbol}"
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url_tcbs, headers=headers, timeout=3)
            if res.status_code == 200:
                data = res.json()
                if "data" in data and len(data["data"]) > 0:
                    last_tick = data["data"][0]
                    price = float(last_tick.get("price", 0.0))
                    vol = float(last_tick.get("vol", 0.0))
                    if price > 0:
                        print(f"🔍 [TCBS API] Lấy thành công giá {symbol}: {price:,.0f}")
        except Exception as e:
            print(f"⚠️ TCBS API error: {e}")

    # Nguồn 3: Gọi VnStock Quote cơ bản nếu có cài đặt
    if price == 0 and Quote is not None:
        try:
            q = Quote(symbol=symbol, source="VCI")
            hist = q.history(start=datetime.now().strftime("%Y-%m-%d"), end=datetime.now().strftime("%Y-%m-%d"), interval="1m")
            if hist is not None and not hist.empty:
                price = float(hist["close"].iloc[-1])
                vol = float(hist["volume"].iloc[-1])
                if price > 0:
                    print(f"🔍 [VnStock History 1m] Lấy thành công giá {symbol}: {price:,.0f}")
        except Exception as e:
            print(f"⚠️ VnStock 1m fallback error: {e}")

    # Chuẩn hóa đơn vị giá về VNĐ
    if 0 < price < 1000:
        price *= 1000

    # Thực hiện chèn/cập nhật nến ngày hôm nay
    if price > 0:
        try:
            tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
            today_dt = datetime.now(tz_vn).replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        today_date = today_dt.date()

        df["_time_clean"] = pd.to_datetime(df["time"]).dt.date
        last_date = df["_time_clean"].iloc[-1]

        if last_date == today_date:
            df.loc[df.index[-1], "close"] = price
            if price > df.loc[df.index[-1], "high"]:
                df.loc[df.index[-1], "high"] = price
            if price < df.loc[df.index[-1], "low"] or df.loc[df.index[-1], "low"] == 0:
                df.loc[df.index[-1], "low"] = price
            if vol > 0:
                df.loc[df.index[-1], "volume"] = vol
            df.loc[df.index[-1], "time"] = pd.to_datetime(today_dt)
            print(f"✅ [SUCCESS] Đã CẬP NHẬT nến hôm nay ({today_date}) - Giá Realtime: {price:,.0f} VNĐ")
        else:
            new_row = {
                "time": pd.to_datetime(today_dt),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": vol if vol > 0 else 1.0
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            print(f"✅ [SUCCESS] Đã CHÈN NẾN MỚI hôm nay ({today_date}) - Giá Realtime: {price:,.0f} VNĐ")

        df = df.drop(columns=["_time_clean"], errors="ignore")
    else:
        print(f"❌ [FAIL] Không lấy được giá Realtime cho mã {symbol} từ bất kỳ nguồn nào!")

    return df


# ==============================================================================
# HÀM TÍNH TOÁN CÁC CHỈ BÁO CHIẾN LƯỢC MEAN REVERSION (BOLLINGER BANDS & RSI)
# ==============================================================================

def calculate_realtime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates MA20, Bollinger Bands (2.0), and RSI(14) for Mean Reversion Strategy."""
    if df is None or df.empty or len(df) < 20:
        return df

    df = df.copy()
    
    # 1. Lấy tham số cấu hình từ config.py
    bb_window = TECHNICAL_STRATEGY.get("BB_WINDOW", 20)
    bb_std = TECHNICAL_STRATEGY.get("BB_STD", 2.0)
    rsi_window = TECHNICAL_STRATEGY.get("RSI_WINDOW", 14)

    # 2. Tính đường MA20 & Bollinger Bands
    df["ma20"] = df["close"].rolling(window=bb_window).mean()
    df["std20"] = df["close"].rolling(window=bb_window).std()
    df["upper_band"] = df["ma20"] + (df["std20"] * bb_std)
    df["lower_band"] = df["ma20"] - (df["std20"] * bb_std)

    # 3. Tính RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/rsi_window, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/rsi_window, adjust=False).mean()
    
    rs = gain / loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))
    df["rsi14"] = df["rsi14"].fillna(50.0)

    return df


def get_realtime_indicators(symbol: str) -> dict:
    """Trả về dictionary đầy đủ tham số kỹ thuật Mean Reversion mới nhất của mã cổ phiếu."""
    df = get_realtime_ohlcv(symbol, limit=150)
    if df is None or df.empty or len(df) < 20:
        return {}

    df_ind = calculate_realtime_indicators(df)
    latest = df_ind.iloc[-1]
    prev = df_ind.iloc[-2]

    close_val = float(latest.get("close", 0.0))
    open_val = float(latest.get("open", 0.0))

    return {
        "symbol": symbol.upper(),
        "close": close_val,
        "open": open_val,
        "ma20": float(latest.get("ma20", 0.0)),
        "upper_band": float(latest.get("upper_band", 0.0)),
        "lower_band": float(latest.get("lower_band", 0.0)),
        "rsi14": float(latest.get("rsi14", 0.0)),
        "prev_rsi14": float(prev.get("rsi14", 0.0)),
        "volume": float(latest.get("volume", 0.0)),
        "updated_at": latest.get("time")
    }


def check_vnindex_safe() -> bool:
    """
    KTL Bộ lọc An toàn VN-Index:
    Ngăn Bot mở vị thế nếu VN-Index sụp gãy sâu hơn ngưỡng cho phép dưới dải Lower Band.
    """
    if not TECHNICAL_STRATEGY.get("USE_MARKET_FILTER", True):
        return True

    try:
        df_vn = get_realtime_ohlcv("VNINDEX", limit=100)
        if df_vn is None or df_vn.empty or len(df_vn) < 20:
            return True

        df_vn_ind = calculate_realtime_indicators(df_vn)
        latest_vn = df_vn_ind.iloc[-1]
        
        vn_close = float(latest_vn.get("close", 0.0))
        vn_lower_band = float(latest_vn.get("lower_band", 0.0))
        buffer = TECHNICAL_STRATEGY.get("VNINDEX_BB_BUFFER", 0.995)

        # Trả về False nếu VN-Index sụp hoảng loạn dưới Lower Band * buffer
        if vn_close > 0 and vn_lower_band > 0:
            is_safe = vn_close >= (vn_lower_band * buffer)
            if not is_safe:
                print(f"⚠️ [MARKET FILTER] VN-Index ({vn_close:,.2f}) gãy dải Lower Band ({vn_lower_band:,.2f}). TẠM DỪNG MUA!")
            return is_safe
    except Exception as e:
        print(f"⚠️ Lỗi khi kiểm tra bộ lọc VN-Index: {e}")
        
    return True


if __name__ == "__main__":
    test_symbol = "SSI"
    print(f"🚀 Testing realtime indicators (Mean Reversion) for {test_symbol}...")
    res = get_realtime_indicators(test_symbol)
    print("👉 Output:", res)
    print("👉 VN-Index Market Safe Check:", check_vnindex_safe())