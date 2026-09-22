# ==============================================================================
# MODULE: database.py
# Chức năng:
#   - Quản lý Cache SQLite cho Dữ liệu Tài chính Cơ bản (FA)
#   - Khắc phục triệt để lỗi Thread-Lock & Ephemeral Filesystem trên Render
#   - Tự động invalidate Cache cũ (>24h) để dữ liệu Backtest luôn chính xác
# ==============================================================================
import sqlite3
import os
from datetime import datetime, timedelta

# Sử dụng đường dẫn tuyệt đối trong thư mục tạm hoặc thư mục gốc ứng dụng
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "finbot_cache.db")

# Cấu hình thời gian sống của Cache FA (24 giờ) để đảm bảo dữ liệu luôn mới nhất
CACHE_TTL_HOURS = 24


def get_connection():
    """Tạo kết nối SQLite an toàn với timeout chờ khóa tránh lỗi 'database is locked'."""
    conn = sqlite3.connect(DB_FILE, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Khởi tạo bảng cache nếu chưa tồn tại."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Kích hoạt WAL Mode để tối ưu tốc độ Đọc/Ghi đa tiến trình trên Render
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS finbot_cache (
                ticker TEXT PRIMARY KEY,
                period TEXT,
                roe_annualized REAL,
                debt_equity REAL,
                nim_ratio REAL,
                gross_margin REAL,
                net_profit_bil REAL,
                is_bank INTEGER,
                listed_status TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo database: {e}")


def get_fa_from_db(ticker: str) -> dict:
    """
    Lấy dữ liệu FA từ Database Cache.
    Chỉ trả về dữ liệu nếu Cache còn hiệu lực (chưa quá CACHE_TTL_HOURS).
    """
    if not os.path.exists(DB_FILE):
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT *, datetime(updated_at, 'localtime') as local_updated FROM finbot_cache WHERE ticker = ?",
            (ticker.upper(),)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            data = dict(row)
            
            # KIỂM TRẢ HẠN CACHE (TỐI ƯU BACKTEST DỮ LIỆU MỚI)
            updated_str = data.get("updated_at")
            if updated_str:
                try:
                    # Parse thời gian cập nhật
                    updated_time = datetime.strptime(updated_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    if datetime.now() - updated_time > timedelta(hours=CACHE_TTL_HOURS):
                        print(f"🔄 Cache FA của mã {ticker} đã hết hạn (>24h). Cần làm mới.")
                        return None
                except Exception:
                    pass  # Nếu lỗi parse ngày tháng thì vẫn dùng tạm data

            data["is_bank"] = bool(data["is_bank"])
            return data

    except Exception as e:
        print(f"⚠️ Lỗi đọc database cache: {e}")
    return None


def save_fa_to_db(data: dict):
    """Ghi hoặc làm mới dữ liệu FA vào SQLite Cache."""
    if not data or "ticker" not in data:
        return
        
    if not os.path.exists(DB_FILE):
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO finbot_cache (
                ticker, period, roe_annualized, debt_equity, 
                nim_ratio, gross_margin, net_profit_bil, is_bank, listed_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            data.get("ticker").upper().strip(),
            data.get("period", "N/A"),
            float(data.get("roe_annualized", 0.0) or 0.0),
            float(data.get("debt_equity", 0.0) or 0.0),
            float(data.get("nim_ratio", 0.0) or 0.0),
            float(data.get("gross_margin", 0.0) or 0.0),
            float(data.get("net_profit_bil", 0.0) or 0.0),
            1 if data.get("is_bank") else 0,
            data.get("listed_status", "Normal")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi ghi database cache: {e}")


# Tự động tạo bảng một cách an toàn khi module được nạp
init_db()