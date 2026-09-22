# 🤖 AI FinBot - Telegram Stock Analysis Bot

AI FinBot là robot Telegram hỗ trợ phân tích tự động cổ phiếu Việt Nam (FA & TA), vẽ biểu đồ kỹ thuật trực quan và đưa ra khuyến nghị giao dịch theo thời gian thực.

---

## 📌 Tính năng chính

- 📊 **Phân tích Kỹ thuật (TA):** 
  - Tự động vẽ biểu đồ Giá, đường **EMA20** và chỉ báo **RSI(14)**.
  - Nhận diện chính xác xu hướng độ dốc của EMA20 (*Uptrend*, *Downtrend*, *Đi ngang*).
- 🏢 **Phân tích Cơ bản (FA):** 
  - Đánh giá chỉ số sức khỏe tài chính: ROE, LNST, Biên lợi nhuận gộp, Đòn bẩy tài chính (D/E).
  - Tự động nhận diện mô hình đặc thù cho các nhóm ngành (Ngân hàng / Tài chính).
- 💡 **Khuyến nghị & Cảnh báo:** Đưa ra tín hiệu MUA / BÁN / THEO DÕI dựa trên sự kết hợp giữa FA & TA.
- 🚀 **Đặt lệnh tự động:** Hỗ trợ gửi lệnh giao dịch nhanh qua cú pháp `/trade`.

---

## 🛠️ Công nghệ sử dụng

- **Ngôn ngữ:** Python 3.10+
- **Thư viện chính:**
  - `python-telegram-bot`: Xử lý tương tác Bot Telegram.
  - `pandas`: Xử lý & tính toán dữ liệu tài chính.
  - `matplotlib`: Vẽ và xuất biểu đồ kỹ thuật.
- **Deployment:** Render.com (Background Worker 24/7).

---

## 🚀 Hướng dẫn Cài đặt & Chạy Local

### 1. Yêu cầu hệ thống
- Python >= 3.10
- Git

### 2. Cài đặt

```bash
# Clone project về máy
git clone [https.github.com/USERNAME/telegram-finbot.git](https://https.github.com/USERNAME/telegram-finbot.git)
cd telegram-finbot

# Tạo môi trường ảo (Virtual Environment)
python -m venv venv

# Kích hoạt môi trường ảo
# Trên Windows:
venv\Scripts\activate
# Trên Linux/macOS:
source venv/bin/activate

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
pip install flask python-telegram-bot pandas matplotlib
