# database.py
import sqlite3

DB_FILE = "finbot_cache.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # Đã xóa npl_ratio khỏi bảng
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

def get_fa_from_db(ticker: str) -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM finbot_cache WHERE ticker = ?", (ticker.upper(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = dict(row)
            data["is_bank"] = bool(data["is_bank"])
            return data
    except Exception as e:
        print(f"⚠️ Lỗi đọc database: {e}")
    return None

def save_fa_to_db(data: dict):
    if not data or "ticker" not in data:
        return
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO finbot_cache (
                ticker, period, roe_annualized, debt_equity, 
                nim_ratio, gross_margin, net_profit_bil, is_bank, listed_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            data.get("ticker").upper(),
            data.get("period"),
            data.get("roe_annualized", 0.0),
            data.get("debt_equity", 0.0),
            data.get("nim_ratio", 0.0),
            data.get("gross_margin", 0.0),
            data.get("net_profit_bil", 0.0),
            1 if data.get("is_bank") else 0,
            data.get("listed_status", "Normal")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi ghi database: {e}")

init_db()