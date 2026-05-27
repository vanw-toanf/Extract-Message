#!/usr/bin/env python3
"""
Post-process vietnam_administrative.json:
- Cải thiện parsing của merged_from từ truocsapnhap text
- Loại bỏ nhiễu (phrases mô tả, không phải tên đơn vị)
- Tách tên cũ (old_ward) và tỉnh cũ (old_province) nếu có thể xác định
"""

import json
import re
import unicodedata

# Regex nhận biết tiền tố đơn vị hành chính cấp xã
UNIT_TYPE_PATTERNS = [
    r'^(Phường|Xã|Thị trấn|Thị xã|Đặc khu)\s+\S',
]

# Các pattern cần skip (không phải tên đơn vị)
NOISE_PATTERNS = [
    r'^m[oộ]t ph[aầ]n di[eệ]n t[íi]ch',
    r'^m[oộ]t ph[aầ]n quy m[oô]',
    r'^quy m[oô] d[aâ]n s[oố]',
    r'^ph[aầ]n c[oò]n l[aạ]i',
    r'^sau khi s[aắ]p',
    r'^v[àa] ph[aầ]n',
    r'^to[aà]n b[oộ]',
    r'^di[eệ]n t[íi]ch TN',
    r'^\d+',
    r'^v[àa]\s',
    r'^hay\s',
    r'^ho[aặ]c\s',
    r'^c[uù]ng',
]

# Mapping tên tỉnh cũ sang tỉnh mới (sau sáp nhập)
# Dùng để gán old_province_name đúng
# Ví dụ: nếu nói "xã A (huyện B, tỉnh Thái Bình)" thì old_province_name = "Tỉnh Thái Bình"

def is_noise(text: str) -> bool:
    """Kiểm tra xem text có phải là noise/mô tả không."""
    t = text.strip()
    if not t or len(t) < 2:
        return True
    # Không bắt đầu bằng chữ cái
    if not t[0].isalpha():
        return True
    t_lower = t.lower()
    for pat in NOISE_PATTERNS:
        if re.match(pat, t_lower, re.IGNORECASE):
            return True
    return False


def is_unit_name(text: str) -> bool:
    """Kiểm tra text có vẻ là tên đơn vị hành chính không."""
    t = text.strip()
    if is_noise(t):
        return False
    # Có tiền tố đơn vị
    for pat in UNIT_TYPE_PATTERNS:
        if re.match(pat, t, re.IGNORECASE):
            return True
    # Tên ngắn không có tiền tố (vd: "Kim Mã", "Điện Biên") - chấp nhận nếu >= 3 ký tự và không phải noise
    if len(t) >= 3 and t[0].isupper():
        return True
    return False


def extract_province_from_paren(text: str) -> tuple:
    """
    Tách tên đơn vị và tỉnh/huyện từ trong ngoặc.
    Ví dụ: "Xã Vĩnh Quang (thành phố Cao Bằng)" → ("Xã Vĩnh Quang", "thành phố Cao Bằng", None)
    Ví dụ: "Xã A (huyện B, tỉnh C)" → ("Xã A", None, "tỉnh C")
    Returns: (ward_name, district_name, province_name)
    """
    # Tìm ngoặc đơn
    paren_match = re.search(r'\(([^)]+)\)', text)
    if not paren_match:
        return text.strip(), None, None
    
    ward_name = text[:paren_match.start()].strip()
    paren_content = paren_match.group(1).strip()
    
    district_name = None
    province_name = None
    
    # Phân tích nội dung trong ngoặc
    parts = [p.strip() for p in paren_content.split(',')]
    for part in parts:
        part_lower = part.lower()
        if part_lower.startswith('tỉnh ') or part_lower.startswith('thành phố ') or part_lower.startswith('thành phố') or part_lower.startswith('tp.'):
            province_name = part
        elif part_lower.startswith('huyện ') or part_lower.startswith('quận ') or part_lower.startswith('thị xã '):
            district_name = part
        elif part_lower.startswith('thành phố '):
            district_name = part  # Có thể là đơn vị hành chính cấp huyện
        else:
            # Nếu chỉ có 1 phần, thường là tên huyện/TP cấp huyện
            if len(parts) == 1:
                district_name = part
    
    return ward_name, district_name, province_name


def parse_merged_from(truocsapnhap: str, current_province: str) -> list:
    """
    Parse text truocsapnhap → list các merged_from entries.
    """
    if not truocsapnhap:
        return []
    
    text = truocsapnhap.strip()
    
    # Giữ nguyên → không sáp nhập
    if 'giữ nguyên' in text.lower():
        return []
    
    merged = []
    
    # Xử lý ngoặc trước khi tách
    # Ngoặc có thể chứa: (huyện X, tỉnh Y) hoặc (thành phố X) hoặc (phần còn lại...)
    # Tách theo dấu phẩy nhưng giữ ngoặc nguyên vẹn
    
    # Strategy: tách text thành segments theo "Phường/Xã/Thị trấn" 
    # hoặc theo dấu phẩy (bỏ qua dấu phẩy trong ngoặc)
    
    # Bước 1: bỏ các cụm "phần còn lại..." trong ngoặc đơn
    # Ví dụ: "Phường A (phần còn lại sau khi ...)" → "Phường A"
    text_clean = re.sub(r'\s*\([^)]*(?:ph[aầ]n c[oò]n l[aạ]i|sau khi|tr[uướ]c khi)[^)]*\)', '', text, flags=re.IGNORECASE)
    
    # Bước 2: Tách các segment theo dấu phẩy, tôn trọng ngoặc đơn
    # Dùng regex để tách theo dấu phẩy không nằm trong ngoặc
    segments = re.split(r',\s*(?![^()]*\))', text_clean)
    
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        
        # Bỏ "và " ở đầu
        seg = re.sub(r'^v[àa]\s+', '', seg, flags=re.IGNORECASE).strip()
        
        # Kiểm tra noise
        if is_noise(seg):
            continue
        
        # Extract tên đơn vị và thông tin tỉnh/huyện từ ngoặc
        ward_name, district_name, province_name = extract_province_from_paren(seg)
        
        # Nếu không xác định được tỉnh → dùng tỉnh hiện tại
        if not province_name:
            province_name = current_province
        
        # Bỏ các entry noise
        if is_noise(ward_name) or len(ward_name) < 2:
            continue
        
        entry = {
            "old_ward_name": ward_name,
            "old_district_name": district_name,
            "old_province_name": province_name
        }
        merged.append(entry)
    
    return merged


def process_file(input_file: str, output_file: str):
    print(f"📂 Đọc file: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 Xử lý {len(data)} tỉnh/thành phố...")
    
    total_wards = 0
    total_merged = 0
    issues = []
    
    for province in data:
        prov_name = province['province_name']
        for ward in province['wards']:
            total_wards += 1
            
            if ward.get('is_merged') and ward.get('merged_from_raw'):
                raw = ward['merged_from_raw']
                new_merged = parse_merged_from(raw, prov_name)
                ward['merged_from'] = new_merged
                total_merged += 1
                
                # Debug: phát hiện entries có thể noise còn sót
                for entry in new_merged:
                    name = entry['old_ward_name']
                    if len(name) < 3 or not name[0].isalpha():
                        issues.append(f"[{prov_name}] {ward['ward_name']}: '{name}'")
            
            # Xóa trường raw sau khi đã xử lý (optional)
            # ward.pop('merged_from_raw', None)
    
    print(f"\n✅ Thống kê:")
    print(f"   → {total_wards} xã/phường tổng")
    print(f"   → {total_merged} xã/phường được sáp nhập")
    print(f"   → {total_wards - total_merged} giữ nguyên")
    
    if issues:
        print(f"\n⚠️  {len(issues)} entries có thể cần kiểm tra:")
        for iss in issues[:10]:
            print(f"   • {iss}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Đã lưu: {output_file}")
    
    # In mẫu
    print("\n--- Mẫu dữ liệu ---")
    for p in data[:1]:
        for w in p['wards'][:2]:
            print(json.dumps(w, ensure_ascii=False, indent=2))
            print()


if __name__ == "__main__":
    process_file('vietnam_administrative.json', 'vietnam_administrative.json')
