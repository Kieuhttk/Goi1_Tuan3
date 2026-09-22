# ==============================================================================
# MODULE: config.py
# Chức năng:
#   - Tải biến môi trường (Environment Variables) an toàn cho Render
#   - Quản lý cấu hình API, Telegram Token, Port Web Server
#   - Chuẩn hóa bộ tham số Backtest Kỹ thuật & Tài chính (TA/FA)
# ==============================================================================
import os

# --- 1. DỊCH VỤ DỮ LIỆU & API ---
DNSE_BASE_URL = "https://services.entrade.com.vn/chart-api/v2"

# --- 2. CẤU HÌNH TELEGRAM BOT (ĐỌC TỪ RENDER ENVIRONMENT VARIABLES) ---
# Đặt giá trị mặc định làm Fallback nếu chạy ở máy Local
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
DEFAULT_WATCHLIST = ["HPG", "SSI", "VNM", "FPT", "TCB", "ACB", "MBB"]
SCAN_INTERVAL_SECONDS = 300  # Quét lại sau mỗi 5 phút (300 giây)
CACHE_TTL_HOURS = 24         # Hạn lưu Cache FA trong SQLite (24 giờ)

# --- 5. BỘ THAM SỐ LỌC BACKTEST TỐI ƯU WIN RATE (TA / FA CONFIG) ---
TECHNICAL_STRATEGY = {
    "RSI_MIN": 45.0,            # Vùng RSI bắt đầu nhịp tăng tốc
    "RSI_MAX": 60.0,            # Vùng RSI an toàn (tránh Mua ở điểm Quá Mua >65)
    "VOLUME_RATIO_MIN": 1.2,    # Khối lượng xấp xỉ/vượt 1.2x MA20 để xác nhận dòng tiền
    "MA_TREND": "EMA20_EMA50"   # Điều kiện Xu hướng: Giá > EMA20 > EMA50
}

FUNDAMENTAL_STRATEGY = {
    "NON_BANK_ROE_MIN": 8.0,    # ROE tối thiểu cho Doanh nghiệp sản xuất/thương mại
    "BANK_ROE_MIN": 10.0,       # ROE tối thiểu cho Ngân hàng
    "MAX_DEBT_EQUITY": 3.0      # Ngưỡng đòn bẩy D/E tối đa
}