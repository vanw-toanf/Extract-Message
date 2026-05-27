#!/usr/bin/env python3
"""
Crawl dữ liệu đơn vị hành chính Việt Nam sau sáp nhập từ sapnhap.bando.com.vn
Nguồn: Bộ Nông nghiệp và Môi trường - NXB Tài nguyên - Môi trường và Bản đồ Việt Nam
"""

import requests
import json
import re
import time
import unicodedata
from typing import Optional

BASE_URL = "https://sapnhap.bando.com.vn"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Referer': BASE_URL + '/',
    'Origin': BASE_URL,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def post_api(endpoint: str, data: dict, retries: int = 3) -> Optional[str]:
    """Gọi POST API với retry."""
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(retries):
        try:
            r = SESSION.post(url, data=data, timeout=30)
            r.raise_for_status()
            return r.text.strip()
        except Exception as e:
            print(f"  [WARN] Attempt {attempt+1}/{retries} failed for {endpoint}: {e}")
            time.sleep(2 ** attempt)
    return None


def get_all_units():
    """Lấy toàn bộ đơn vị hành chính (34 tỉnh + 3321 xã/phường)."""
    print("📥 Đang tải danh sách toàn bộ đơn vị hành chính...")
    raw = post_api('p.co_dvhc', {'ma': '0'})
    if not raw:
        raise RuntimeError("Không thể tải danh sách đơn vị hành chính!")
    data = json.loads(raw)
    print(f"   → Tổng: {len(data)} đơn vị")
    return data


def get_province_with_wards(province_malk: str):
    """Lấy dữ liệu chi tiết của một tỉnh gồm cả danh sách xã/phường."""
    raw = post_api('p.co_bangbieu', {'ma': province_malk})
    if not raw or raw == '.synt.[]':
        return None, []

    # Response format: {tinh_json}.synt.[{xa_json},{xa_json},...]
    parts = raw.split('.synt.')
    if len(parts) != 2:
        return None, []

    try:
        tinh_data = json.loads(parts[0]) if parts[0].strip() else None
    except:
        tinh_data = None

    try:
        wards_data = json.loads(parts[1])
    except:
        wards_data = []

    return tinh_data, wards_data


def normalize_text(s: str) -> str:
    """Chuẩn hóa khoảng trắng."""
    if not s:
        return s
    return re.sub(r'\s+', ' ', s).strip()


def make_ward_code(ward_name: str, province_code: str, ward_ma: str) -> str:
    """Tạo ward_code từ tên xã + mã tỉnh."""
    # Dùng mã đơn vị hành chính chính thức nếu có
    if ward_ma:
        return ward_ma
    # Fallback: tạo slug từ tên
    name = ward_name.upper()
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = re.sub(r'[^A-Z0-9]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return f"W_{name}"


def parse_merged_from_text(truocsapnhap: str, province_name: str) -> list:
    """
    Parse text 'truocsapnhap' thành danh sách merged_from.
    
    Text thường có dạng:
    - "Phường A, Xã B, Thị trấn C"
    - "một phần ... của phường X, phường Y"
    - "giữ nguyên" (không sáp nhập)
    
    Trả về list các dict với old_ward_name, old_district_name (None nếu ko xác định),
    old_province_name (None nếu không xác định)
    """
    if not truocsapnhap:
        return []

    text = normalize_text(truocsapnhap)

    # Trường hợp giữ nguyên
    if 'giữ nguyên' in text.lower():
        return []

    merged = []
    
    # Tách các phần tử bằng dấu phẩy, sau đó lọc
    # Các pattern không phải tên đơn vị:
    SKIP_PATTERNS = [
        r'^m[oộ]t ph[aầ]n',
        r'^ph[aầ]n c[oò]n l[aạ]i',
        r'^sau khi s[aắ]p x[eế]p',
        r'^sau khi s[aắ]p nh[aậ]p',
        r'^to[aà]n b[oộ]',
        r'^\d+',
        r'^v[àa]\s',
        r'^c[aá]c ',
    ]
    
    # Các prefix nhận biết đơn vị hành chính
    UNIT_PREFIXES = [
        'phường', 'xã', 'thị trấn', 'thị xã', 'đặc khu', 'huyện', 'quận',
        'phuong', 'xa ', 'thi tran', 'thi xa'
    ]
    
    # Tách theo dấu phẩy và dấu ";", xử lý từng phần
    # Nhưng cần cẩn thận vì tên đơn vị có thể không có prefix
    # → Parse heuristic: mỗi segment sau dấu phẩy là 1 đơn vị nếu bắt đầu bằng chữ hoa
    # và không phải các pattern cần skip
    
    # Xử lý ngoặc đơn: "Phường A (phần còn lại sau khi...)" → lấy "Phường A"
    text_clean = re.sub(r'\s*\([^)]*\)', '', text)
    
    # Tách segment
    raw_segments = re.split(r',|;', text_clean)
    
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        
        # Bỏ qua các cụm mô tả không phải tên đơn vị
        is_skip = False
        seg_lower = seg.lower()
        for pat in SKIP_PATTERNS:
            if re.match(pat, seg_lower, re.IGNORECASE):
                is_skip = True
                break
        
        # Bỏ qua nếu quá ngắn
        if len(seg) < 3:
            is_skip = True
        
        # Bỏ qua nếu không bắt đầu bằng chữ cái
        if seg and not seg[0].isalpha():
            is_skip = True
            
        if is_skip:
            continue
        
        # Tạo entry merged_from
        # Cố gắng xác định loại và tên đơn vị
        entry = {
            "old_ward_name": seg,
            "old_district_name": None,  # Không có trong API này
            "old_province_name": province_name  # Mặc định là cùng tỉnh
        }
        merged.append(entry)
    
    return merged


def build_json_structure(all_units: list) -> list:
    """
    Xây dựng cấu trúc JSON theo định dạng yêu cầu từ dữ liệu API.
    """
    # Tách tỉnh và xã/phường
    provinces_raw = {d['ma']: d for d in all_units if d['magoc'] == '0'}
    wards_raw = [d for d in all_units if d['magoc'] != '0']

    print(f"\n📊 Dữ liệu tổng hợp:")
    print(f"   → {len(provinces_raw)} tỉnh/thành phố")
    print(f"   → {len(wards_raw)} xã/phường")

    result = []

    for province_ma, prov in sorted(provinces_raw.items(), key=lambda x: x[0]):
        print(f"\n🏛  Đang xử lý: {prov['ten']} (mã: {province_ma})...")

        # Lấy chi tiết province và wards từ bangbieu API (có thêm tentinh cho mỗi ward)
        tinh_detail, wards_detail = get_province_with_wards(prov['malk'])
        time.sleep(0.3)  # Rate limiting

        # Lấy wards từ bangbieu nếu có, không thì dùng dữ liệu gốc
        if wards_detail:
            prov_wards = wards_detail
        else:
            prov_wards = [w for w in wards_raw if w['magoc'] == province_ma]

        # Xây dựng province entry
        province_entry = {
            "province_code": province_ma,
            "province_name": prov['ten'],
            "wards": []
        }

        for ward in sorted(prov_wards, key=lambda x: x.get('ten', '')):
            truocsapnhap = normalize_text(ward.get('truocsapnhap', ''))
            is_merged = truocsapnhap and 'giữ nguyên' not in truocsapnhap.lower()

            ward_name = ward.get('ten', '')
            ward_ma = ward.get('ma', '')
            
            ward_entry = {
                "ward_code": ward_ma,
                "ward_name": ward_name,
                "is_merged": is_merged,
            }
            
            if is_merged:
                ward_entry["merged_from_raw"] = truocsapnhap
                ward_entry["merged_from"] = parse_merged_from_text(
                    truocsapnhap, 
                    province_name=prov['ten']
                )
            else:
                ward_entry["merged_from"] = []

            province_entry["wards"].append(ward_entry)

        print(f"   → {len(province_entry['wards'])} xã/phường")
        result.append(province_entry)

    return result


def main():
    print("=" * 60)
    print("🇻🇳 CRAWL DỮ LIỆU HÀNH CHÍNH VIỆT NAM SAU SÁP NHẬP")
    print(f"   Nguồn: {BASE_URL}")
    print("=" * 60)

    # Bước 1: Lấy toàn bộ đơn vị
    all_units = get_all_units()

    # Lưu raw data để debug
    with open('raw_all_units.json', 'w', encoding='utf-8') as f:
        json.dump(all_units, f, ensure_ascii=False, indent=2)
    print("✅ Đã lưu raw data vào raw_all_units.json")

    # Bước 2: Xây dựng cấu trúc JSON theo định dạng yêu cầu
    result = build_json_structure(all_units)

    # Bước 3: Lưu file kết quả
    output_file = 'vietnam_administrative.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Hoàn thành! Đã lưu vào: {output_file}")
    print(f"   → {len(result)} tỉnh/thành phố")
    total_wards = sum(len(p['wards']) for p in result)
    total_merged = sum(
        sum(1 for w in p['wards'] if w['is_merged']) 
        for p in result
    )
    print(f"   → {total_wards} xã/phường")
    print(f"   → {total_merged} xã/phường được sáp nhập")
    print(f"   → {total_wards - total_merged} xã/phường giữ nguyên")
    print("=" * 60)


if __name__ == "__main__":
    main()
