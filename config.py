# ==============================================================================
# MODULE: config.py
# Chức năng:
#   - Tải biến môi trường (Environment Variables) an toàn cho Render
#   - Quản lý cấu hình API, Telegram Token, Port Web Server
#   - Cấu hình bộ tham số Chiến lược MEAN REVERSION (Bắt đáy Sideway VN30/Midcap)
# ==============================================================================
import os

# --- 1. DỊCH VỤ DỮ LIỆU & API ---
DNSE_BASE_URL = "https://services.entrade.com.vn/chart-api/v2"

# --- 2. CẤU HÌNH TELEGRAM BOT (ĐỌC TỪ RENDER ENVIRONMENT VARIABLES) ---
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", 
    "8665430392:AAGk2aN9MwynAPE1V5eoXa_wGBcJFxT1FdI"
)
TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID", 
    ""  # Bạn điền Chat ID vào phần Environment Variables trên Render Dashboard
)

# --- 3. CẤU HÌNH RENDER WEB SERVER ---
PORT = int(os.getenv("PORT", 8080))
HOST = "0.0.0.0"

# --- 4. CẤU HÌNH QUÉT DỮ LIỆU (SCANNER & CACHE) ---
# Danh mục mở rộng: VN30 + Top Midcap cơ bản tốt
DEFAULT_WATCHLIST = [
    # Nhóm Ngân hàng
    "VCB", "BID", "CTG", "MBB", "TCB", "ACB", "VPB", "STB", "HDB", "TPB",
    # Nhóm Chứng khoán
    "SSI", "VND", "VCI", "HCM", "MBS", "SHS",
    # Nhóm Bất động sản / Thép
    "HPG", "NKG", "HSG", "NVL", "PDR", "DXG", "VHM", "VIC", "KDH", "NLG",
    # Nhóm Bán lẻ / Công nghệ / Khác
    "MWG", "FRT", "FPT", "DGC", "VNM", "MSN", "GAS", "PVD", "PVS"
]
SCAN_INTERVAL_SECONDS = 300  # Quét lại sau mỗi 5 phút (300 giây)
CACHE_TTL_HOURS = 24         # Hạn lưu Cache FA trong SQLite (24 giờ)

# --- 5. BỘ THAM SỐ CHIẾN LƯỢC MEAN REVERSION (BOLLINGER BANDS + RSI) ---
TECHNICAL_STRATEGY = {
    "NAME": "MEAN_REVERSION_SIDEWAY",
    "BB_WINDOW": 20,            # Chu kỳ Bollinger Bands
    "BB_STD": 2.0,              # Độ lệch chuẩn
    "RSI_WINDOW": 14,           # Chu kỳ RSI
    
    # Điều kiện kích hoạt mua
    "BUY_RSI_MAX": 42.0,        # RSI <= 42 (Vùng quá bán ngắn hạn)
    "BUY_BB_BUFFER": 1.01,      # Giá tiệm cận dải dưới Lower Band (1.01x)
    
    # Điều kiện chốt lời & cắt lỗ
    "TAKE_PROFIT_RSI": 56.0,    # Chốt lời khi RSI hồi phục lên >= 56
    "TAKE_PROFIT_PCT": 0.04,    # Target chốt lời tối thiểu +4%
    "STOP_LOSS_PCT": -0.03,     # Cắt lỗ cứng -3.0%
    
    # Bộ lọc thị trường VN-Index
    "USE_MARKET_FILTER": True,  # Bật/Tắt bộ lọc hoảng loạn VN-Index
    "VNINDEX_BB_BUFFER": 0.995  # VN-Index không được gãy quá 0.5% dưới Lower Band
}

FUNDAMENTAL_STRATEGY = {
    "NON_BANK_ROE_MIN": 8.0,    # ROE tối thiểu cho Doanh nghiệp sản xuất/thương mại
    "BANK_ROE_MIN": 10.0,       # ROE tối thiểu cho Ngân hàng
    "MAX_DEBT_EQUITY": 3.0      # Ngưỡng đòn bẩy D/E tối đa
}