# ==============================================================================
# MODULE: data_fundamental.py
# Chức năng:
#   - Trích xuất, chuẩn hóa dữ liệu BCTC từ VnStock (Xoay vòng nguồn VCI, TCBS, KBS)
#   - Phân loại Doanh nghiệp thường vs Ngân hàng (Loại bỏ D/E, bổ sung chỉ tiêu Ngân hàng)
#   - Quản lý Cache dữ liệu tài chính qua SQLite Database
#   - Đánh giá Điểm Mua (FA) & Bộ lọc 4 KỊCH BẢN BÁN Quản trị rủi ro
# ==============================================================================
import re
import pandas as pd
from vnstock import Finance  # Thư viện vnstock3
from database import get_fa_from_db, save_fa_to_db

# Danh sách nhận diện các mã cổ phiếu thuộc nhóm Ngân hàng
BANK_SYMBOLS = [
    "ACB", "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "STB", "HDB", "TPB",
    "VIB", "EIB", "MSB", "LPB", "OCB", "SSB", "BAB", "NAB", "ABB", "BVB"
]

# ==============================================================================
# 1. HÀM CHUẨN HÓA DỮ LIỆU & BẢNG TÀI CHÍNH
# ==============================================================================
def parse_quarter_key(col_name: str):
    """Chuyển chuỗi định dạng quý/năm thành tuple (năm, quý) để sắp xếp theo thứ tự thời gian."""
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


def get_latest_time_col(df: pd.DataFrame) -> str:
    """Lấy cột thời gian quý mới nhất có trong DataFrame."""
    time_cols = [c for c in df.columns if parse_quarter_key(c) != (0, 0)]
    time_cols_sorted = sorted(time_cols, key=parse_quarter_key, reverse=True)
    return time_cols_sorted[0] if time_cols_sorted else None


def get_val_by_exact_or_kw(df: pd.DataFrame, target_col: str, time_col: str, keywords: list) -> float:
    """Trích xuất giá trị theo danh sách từ khóa ưu tiên."""
    for kw in keywords:
        mask = df[target_col].astype(str).str.strip().str.lower() == kw.lower()
        matched = df[mask]
        if matched.empty:
            mask = df[target_col].astype(str).str.lower().str.contains(kw.lower(), regex=False)
            matched = df[mask]
        
        if not matched.empty and time_col in matched.columns:
            raw_val = matched.iloc[0][time_col]
            return clean_number_val(raw_val)
    return 0.0


# ==============================================================================
# 2. ĐÁNH GIÁ ĐIỂM MUA FA & TÍNH TOÁN 4 KỊCH BẢN BÁN
# ==============================================================================
def check_fa_violation(fund_data: dict) -> tuple[bool, str]:
    """
    KỊCH BẢN BÁN 4: Kiểm tra vi phạm nền tảng tài chính cơ bản (FA).
    Phân tách riêng biệt giữa Doanh Nghiệp Thường và Ngân Hàng.
    Trả về: (Có vi phạm hay không, Lý do vi phạm cụ thể)
    """
    if not fund_data:
        return False, ""
        
    symbol = fund_data.get("ticker", "").upper()
    is_bank = fund_data.get("is_bank", False) or (symbol in BANK_SYMBOLS)

    net_profit = fund_data.get("net_profit_bil", 0.0)
    roe = fund_data.get("roe_annualized", 0.0)

    reasons = []

    # --------------------------------------------------------------------------
    # LOGIC KIỂM TRA CHO NHÓM NGÂN HÀNG (Không xét D/E)
    # --------------------------------------------------------------------------
    
    if net_profit < 0:
            reasons.append("Ngân hàng báo lỗ trong kỳ")
    if roe < 8.0:
            reasons.append(f"ROE suy yếu nghiêm trọng (ROE = {roe:.2f}% < 8%)")
    if reasons:
            return True, "❌ BÁN VI PHẠM FA NGÂN HÀNG: " + "; ".join(reasons)
            return False, ""

    # --------------------------------------------------------------------------
    # LOGIC KIỂM TRA CHO DOANH NGHIỆP THƯỜNG (Sản xuất, Thương mại, BĐS...)
    # --------------------------------------------------------------------------
    else:
        debt_equity = fund_data.get("debt_equity", 0.0)

        if net_profit < 0:
            reasons.append("Doanh nghiệp báo lỗ trong kỳ")
        if roe < 5.0:
            reasons.append(f"ROE quá thấp (ROE = {roe:.2f}% < 5%)")
        if debt_equity > 3.5:
            reasons.append(f"Tỷ lệ đòn bẩy D/E quá cao (D/E = {debt_equity:.2f}x > 3.5x)")

        if reasons:
            return True, "❌ BÁN VI PHẠM FA: " + "; ".join(reasons)
        return False, ""


def fundamental_signal(fund_data: dict, mode: str = "than_trong") -> str:
    """Hàm đánh giá lọc điểm MUA theo phân tích cơ bản (FA)."""
    if not fund_data:
        return "HOLD"
    
    symbol = fund_data.get("ticker", "").upper()
    is_bank = fund_data.get("is_bank", False) or (symbol in BANK_SYMBOLS)

    roe = fund_data.get("roe_annualized", 0.0)
    net_profit = fund_data.get("net_profit_bil", 0.0)

    if net_profit <= 0:
        return "HOLD"

    if is_bank:
        # Ngân hàng không xét D/E, nâng tiêu chuẩn ROE
        if mode == "than_trong" and roe >= 15.0:
            return "BUY"
        elif mode == "mao_hiem" and roe >= 10.0:
            return "BUY"
    else:
        # Doanh nghiệp thường
        debt_equity = fund_data.get("debt_equity", 0.0)
        if mode == "than_trong" and roe >= 12.0 and debt_equity <= 1.5:
            return "BUY"
        elif mode == "mao_hiem" and roe >= 8.0 and debt_equity <= 2.5:
            return "BUY"
            
    return "HOLD"


def evaluate_sell_scenarios(symbol: str, current_price: float, ta_data: dict, fund_data: dict, entry_price: float = None) -> dict:
    """
    TỔNG HỢP TRỌN BỘ 4 KỊCH BẢN BÁN TRONG QUẢN TRỊ RỦI RO:
    1. Stop-Loss Động (-7% cảnh báo hạ tỷ trọng / -10% cắt lỗ cứng)
    2. Take-Profit Từng Phần (+15% chốt 50% / +25% chốt hết)
    3. Trailing Stop (Gãy EMA20 kèm Volume xả lớn > 1.2x MA20)
    4. Vi phạm Cơ bản FA (Phân loại riêng cho Doanh nghiệp thường và Ngân hàng)
    """
    ema20 = ta_data.get("ema20", 0.0)
    vol_ratio = ta_data.get("volume_ratio", 0.0)
    
    profit_pct = 0.0
    if entry_price and entry_price > 0:
        profit_pct = ((current_price - entry_price) / entry_price) * 100.0

    # KỊCH BẢN 1: STOP-LOSS ĐỘNG (-7% / -10%)
    if entry_price and profit_pct <= -10.0:
        return {
            "signal": "SELL",
            "scenario": "STOP_LOSS_HARD",
            "reason": f"🚨 CẮT LỖ BẮT BUỘC: Vi phạm ngưỡng dừng lỗ tối đa (Lỗ: {profit_pct:.1f}% <= -10%)."
        }
    elif entry_price and profit_pct <= -7.0:
        return {
            "signal": "SELL",
            "scenario": "STOP_LOSS_SOFT",
            "reason": f"⚠️ CẮT LỖ BẢO VỆ: Vi phạm ngưỡng cảnh báo -7% (Lỗ: {profit_pct:.1f}%). Nên hạ 50% vị thế."
        }

    # KỊCH BẢN 2: TAKE-PROFIT TỪNG PHẦN (+15% / +25%)
    if entry_price and profit_pct >= 25.0:
        return {
            "signal": "SELL",
            "scenario": "TAKE_PROFIT_FULL",
            "reason": f"🎯 CHỐT LỜI MỤC TIÊU LỚN: Đạt lợi nhuận kỳ vọng (+{profit_pct:.1f}% >= +25%). Chốt toàn bộ vị thế."
        }
    elif entry_price and profit_pct >= 15.0:
        return {
            "signal": "SELL",
            "scenario": "TAKE_PROFIT_PARTIAL",
            "reason": f"💰 CHỐT LỜI TỪNG PHẦN: Lợi nhuận đạt {profit_pct:.1f}% (>= +15%). Khuyến nghị bán 50% hiện thực hóa lợi nhuận."
        }

    # KỊCH BẢN 3: TRAILING STOP (GÃY TREND + VOL LỚN)
    if current_price < ema20 and vol_ratio >= 1.2:
        return {
            "signal": "SELL",
            "scenario": "TRAILING_STOP",
            "reason": f"🛑 TRAILING STOP: Giá đâm thủng EMA20 kèm áp lực xả hàng mạnh (Volume = {vol_ratio:.1f}x MA20)."
        }

    # KỊCH BẢN 4: VI PHẠM NỀN TẢNG FA (Chỉ gọi hàm kiểm tra riêng biệt)
    is_violated, fa_reason = check_fa_violation(fund_data)
    if is_violated:
        return {
            "signal": "SELL",
            "scenario": "FA_VIOLATION",
            "reason": fa_reason
        }

    return {"signal": "HOLD", "scenario": "NONE", "reason": "Chưa chạm ngưỡng vi phạm 4 kịch bản bán."}


# ==============================================================================
# ==============================================================================
# TRUY XUẤT & CACHE DỮ LIỆU BCTC (ĐÃ SỬA LỖI LẤY NIM CHO NGÂN HÀNG)
# ==============================================================================
def get_clean_financial_data(symbol: str) -> dict:
    """
    Lấy dữ liệu FA cơ bản. Tự động kiểm tra SQLite Database Cache trước, 
    nếu chưa có mới cào từ VnStock (tự động xoay vòng VCI -> TCBS -> KBS).
    """
    symbol = symbol.upper()
    is_bank = symbol in BANK_SYMBOLS

    # BƯỚC 1: ĐỌC TỪ DATABASE CACHE
    cached_data = get_fa_from_db(symbol)
    if cached_data:
        # Nếu cache cũ thiếu thông tin nim của ngân hàng, bỏ qua cache để cào mới
        if is_bank and cached_data.get("nim_ratio", 0.0) == 0.0:
            pass
        else:
            cached_data["is_bank"] = is_bank
            print(f"⚡ [CACHE HIT] Lấy dữ liệu FA của mã #{symbol} từ Database thành công.")
            return cached_data

    # BƯỚC 2: TẢI DỮ LIỆU TỪ VNSTOCK (XOAY VÒNG NGUỒN)
    print(f"🌐 [API CALL] Đang truy xuất dữ liệu FA mới cho mã #{symbol} từ VnStock...")
    sources = ["VCI", "TCBS", "KBS"]
    
    for src in sources:
        try:
            fin = Finance(symbol=symbol, source=src)
            income = fin.income_statement(period="quarter", lang="vi")
            ratio = fin.ratio(period="quarter", lang="vi")
            
            try:
                bs = fin.balance_sheet(period="quarter", lang="vi")
            except Exception:
                bs = None

            if income is None or income.empty:
                continue

            if 'item' not in income.columns:
                income = income.reset_index()

            item_col_income = 'item' if 'item' in income.columns else income.columns[0]
            latest_q_income = get_latest_time_col(income)

            if not latest_q_income:
                continue

            debt_equity = 0.0
            nim_ratio = 0.0

            # ------------------------------------------------------------------
            # XỬ LÝ DOANH NGHIỆP THƯỜNG
            # ------------------------------------------------------------------
            if not is_bank:
                if bs is not None and not bs.empty:
                    if 'item' not in bs.columns:
                        bs = bs.reset_index()
                    item_col_bs = 'item' if 'item' in bs.columns else bs.columns[0]
                    latest_q_bs = get_latest_time_col(bs)
                    
                    if latest_q_bs:
                        total_liabilities = get_val_by_exact_or_kw(bs, item_col_bs, latest_q_bs, [
                            'NỢ PHẢI TRẢ', 'Tổng nợ phải trả', 'Nợ phải trả'
                        ])
                        owner_equity = get_val_by_exact_or_kw(bs, item_col_bs, latest_q_bs, [
                            'VỐN CHỦ SỞ HỮU', 'Tổng vốn chủ sở hữu', 'Vốn chủ sở hữu'
                        ])
                        
                        if owner_equity > 0 and total_liabilities > 0:
                            debt_equity = total_liabilities / owner_equity

                if debt_equity == 0.0 and ratio is not None and not ratio.empty:
                    if 'item' not in ratio.columns:
                        ratio = ratio.reset_index()
                    item_col_ratio = 'item' if 'item' in ratio.columns else ratio.columns[0]
                    latest_q_ratio = get_latest_time_col(ratio)
                    
                    if latest_q_ratio:
                        debt_equity = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
                            'Nợ phải trả/Vốn chủ sở hữu', 'Nợ/Vốn chủ sở hữu', 'Hệ số nợ/VCSH', 'D/E'
                        ])
                        if debt_equity > 50.0:
                            debt_equity /= 100.0

            # ------------------------------------------------------------------
            # XỬ LÝ RIÊNG BẢNG CHỈ TIỂU CHO NGÂN HÀNG (NIM)
            # ------------------------------------------------------------------
            else:
                if ratio is not None and not ratio.empty:
                    if 'item' not in ratio.columns:
                        ratio = ratio.reset_index()
                    item_col_ratio = 'item' if 'item' in ratio.columns else ratio.columns[0]
                    latest_q_ratio = get_latest_time_col(ratio)

                    if latest_q_ratio:
                        
                        # Trích xuất NIM (Biên lãi thuần)
                        nim_ratio = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
                            'Tỷ lệ thu nhập lãi thuần (NIM)', 'Biên lãi thuần (NIM)', 
                            'NIM (%)', 'NIM', 'Net interest margin'
                        ])

                # Tính dự phòng NIM từ Báo cáo kết quả kinh doanh & Cân đối kế toán nếu Ratio bị thiếu
                if nim_ratio == 0.0:
                    net_interest_income = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, [
                        'Thu nhập lãi thuần', 'Thu nhập lãi thuần quý', 'Net interest income'
                    ])
                    if bs is not None and not bs.empty:
                        if 'item' not in bs.columns:
                            bs = bs.reset_index()
                        item_col_bs = 'item' if 'item' in bs.columns else bs.columns[0]
                        latest_q_bs = get_latest_time_col(bs)
                        total_assets = get_val_by_exact_or_kw(bs, item_col_bs, latest_q_bs, [
                            'TỔNG CỘNG TÀI SẢN', 'Tổng tài sản', 'Total assets'
                        ])
                        if total_assets > 0 and net_interest_income > 0:
                            # NIM quý quy năm tương đối = (Thu nhập lãi thuần quý * 4) / Tổng tài sản
                            nim_ratio = ((net_interest_income * 4) / total_assets) * 100.0

            # ------------------------------------------------------------------
            # LẤY ROE & GROSS MARGIN & NET PROFIT
            # ------------------------------------------------------------------
            roe = 0.0
            gross_margin = 0.0
            
            if ratio is not None and not ratio.empty:
                if 'item' not in ratio.columns:
                    ratio = ratio.reset_index()
                item_col_ratio = 'item' if 'item' in ratio.columns else ratio.columns[0]
                latest_q_ratio = get_latest_time_col(ratio)

                if latest_q_ratio:
                    roe = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
                        'ROE (%)', 'ROE', 'Tỷ suất lợi nhuận trên vốn chủ sở hữu'
                    ])
                    gross_margin = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
                        'Biên LN gộp (%)', 'Biên lợi nhuận gộp (%)', 'Biên lợi nhuận gộp'
                    ])

            if gross_margin == 0.0 and not is_bank:
                gross_profit = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, [
                    'Lợi nhuận gộp', 'Lợi nhuận gộp về bán hàng và cung cấp dịch vụ'
                ])
                revenue = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, [
                    'Doanh thu thuần', 'Doanh thu thuần về bán hàng và cung cấp dịch vụ'
                ])
                if revenue > 0:
                    gross_margin = (gross_profit / revenue) * 100.0

            net_profit_raw = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, [
                'Lợi nhuận của Cổ đông của Công ty mẹ', 'Lợi nhuận sau thuế của công ty mẹ',
                'Lãi/(lỗ) thuần sau thuế', 'Lợi nhuận sau thuế'
            ])

            # Chuẩn hóa tỷ lệ % (Tránh trường hợp nguồn trả về 0.0121 thay vì 1.21%)
            if 0 < abs(roe) < 1.0:
                roe *= 100.0
            if 0 < abs(gross_margin) < 1.0:
                gross_margin *= 100.0
            if 0 < abs(nim_ratio) < 1.0:
                nim_ratio *= 100.0

            net_profit_bil = net_profit_raw / 1e9 if abs(net_profit_raw) > 1e6 else net_profit_raw

            final_data = {
                "ticker": symbol,
                "period": latest_q_income,
                "roe_annualized": round(roe, 2),
                "debt_equity": round(debt_equity, 2) if not is_bank else 0.0,
                "nim_ratio": round(nim_ratio, 2) if is_bank else 0.0,
                "gross_margin": round(gross_margin, 2),
                "net_profit_bil": round(net_profit_bil, 2),
                "is_bank": is_bank,
                "listed_status": "Normal"
            }

            # BƯỚC 3: LƯU CACHE VÀO DB VÀ TRẢ VỀ
            save_fa_to_db(final_data)
            return final_data

        except Exception as e:
            print(f"⚠️ Nguồn {src} lỗi với mã {symbol}: {e}. Đang thử nguồn kế tiếp...")
            continue

    print(f"❌ Không thể lấy dữ liệu FA cho mã {symbol} từ tất cả các nguồn VnStock.")
    return {}


# ==============================================================================
# MAIN TEST MODULE
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Kiểm tra thử mã Ngân Hàng (ACB)...")
    acb_fa_dummy = {
        "ticker": "ACB",
        "period": "2026-Q2",
        "roe_annualized": 27.73,
        "debt_equity": 0.0,
        "nim_ratio": 2.34,
        "net_profit_bil": 4292.5,
        "is_bank": True
    }
    
    dummy_ta = {"ema20": 22.28, "volume_ratio": 0.97}
    
    sell_res = evaluate_sell_scenarios(
        symbol="ACB", 
        current_price=22.0, 
        ta_data=dummy_ta, 
        fund_data=acb_fa_dummy, 
        entry_price=0.0
    )
    print("👉 Kết quả kiểm tra ACB (Mong đợi: HOLD):", sell_res)