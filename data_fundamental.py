import re
import pandas as pd
from vnstock import Finance


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


def get_latest_time_col(df: pd.DataFrame) -> str:
    """Lấy cột thời gian quý mới nhất có trong DataFrame."""
    time_cols = [c for c in df.columns if parse_quarter_key(c) != (0, 0)]
    time_cols_sorted = sorted(time_cols, key=parse_quarter_key, reverse=True)
    return time_cols_sorted[0] if time_cols_sorted else None


def get_clean_financial_data(symbol: str) -> dict:
    try:
        ratio = None
        income = None
        
        # Tải dữ liệu từ vnstock
        for src in ["VCI", "KBS", "TCBS"]:
            try:
                fin = Finance(symbol=symbol.upper(), source=src)
                r_df = fin.ratio(period="quarter", lang="vi")
                i_df = fin.income_statement(period="quarter", lang="vi")
                
                if r_df is not None and not r_df.empty and i_df is not None and not i_df.empty:
                    ratio = r_df
                    income = i_df
                    break
            except Exception:
                continue

        if ratio is None or ratio.empty or income is None or income.empty:
            print(f"⚠️ Không tìm thấy dữ liệu tài chính cho mã {symbol}")
            return {}

        # Reset index nếu cần
        if 'item' not in ratio.columns:
            ratio = ratio.reset_index()
        if 'item' not in income.columns:
            income = income.reset_index()

        item_col_ratio = 'item' if 'item' in ratio.columns else ratio.columns[0]
        item_col_income = 'item' if 'item' in income.columns else income.columns[0]

        # 🎯 FIX TỬ HUYỆT 1: Tìm quý mới nhất RIÊNG BIỆT cho từng bảng
        latest_q_income = get_latest_time_col(income)
        latest_q_ratio = get_latest_time_col(ratio)

        if not latest_q_income or not latest_q_ratio:
            return {}

        def get_val_by_exact_or_kw(df: pd.DataFrame, target_col: str, time_col: str, keywords: list) -> float:
            for kw in keywords:
                # Ưu tiên so sánh khớp chính xác tên dòng
                mask = df[target_col].astype(str).str.strip().str.lower() == kw.lower()
                matched = df[mask]
                if matched.empty:
                    # Nếu không thấy khớp 100%, tìm khớp chứa từ khóa
                    mask = df[target_col].astype(str).str.lower().str.contains(kw.lower(), regex=False)
                    matched = df[mask]
                
                if not matched.empty and time_col in matched.columns:
                    raw_val = matched.iloc[0][time_col]
                    return clean_number_val(raw_val)
            return 0.0

        # 🎯 FIX TỬ HUYỆT 2: Trích xuất chỉ số khớp 100% danh mục terminal của bạn

        # 1. ROE (%) -> Row 18
        roe = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
            'ROE (%)', 'ROE', 'Tỷ suất lợi nhuận trên vốn chủ sở hữu'
        ])

        # 2. Debt / Equity -> Row 16 / Row 17
        debt_equity = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
            'Nợ/Vốn chủ', 'Nợ trên vốn chủ', 'Nợ/Vốn chủ sở hữu'
        ])
        if debt_equity > 10.0:  # Nếu trả về % (VD: 120%)
            debt_equity = debt_equity / 100.0

        # 3. Gross Margin (%) -> Row 23 bảng RATIO hoặc tự tính từ INCOME
        gross_margin = get_val_by_exact_or_kw(ratio, item_col_ratio, latest_q_ratio, [
            'Biên LN gộp (%)', 'Biên lợi nhuận gộp'
        ])
        
        # Nếu bảng RATIO không có Biên LN gộp, tự tính từ bảng INCOME (Row 4 / Row 2)
        if gross_margin == 0.0:
            gross_profit = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, ['Lợi nhuận gộp'])
            revenue = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, ['Doanh thu thuần'])
            if revenue > 0:
                gross_margin = (gross_profit / revenue) * 100

        # 4. Net Profit (Tỷ đồng) -> Row 21 hoặc Row 19 bảng INCOME
        net_profit_raw = get_val_by_exact_or_kw(income, item_col_income, latest_q_income, [
            'Lợi nhuận của Cổ đông của Công ty mẹ',
            'Lãi/(lỗ) thuần sau thuế',
            'Lợi nhuận sau thuế'
        ])
        
        # Quy đổi ra tỷ đồng (Nếu đơn vị trả về là Đồng)
        net_profit_bil = net_profit_raw / 1e9 if abs(net_profit_raw) > 1e6 else net_profit_raw

        return {
            "ticker": symbol.upper(),
            "period": latest_q_income,
            "roe_annualized": round(roe, 2),
            "debt_equity": round(debt_equity, 2),
            "gross_margin": round(gross_margin, 2),
            "net_profit_bil": round(net_profit_bil, 2),
            "listed_status": "Normal"
        }

    except Exception as e:
        print(f"❌ Lỗi xử lý dữ liệu cơ bản cho mã {symbol}: {e}")
        return {}


if __name__ == "__main__":
    print("🚀 Đang kiểm tra dữ liệu thực tế FA...")
    data = get_clean_financial_data("VNM")
    print("\nKết quả trích xuất tài chính:", data)