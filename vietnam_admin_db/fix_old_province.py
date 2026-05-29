#!/usr/bin/env python3
"""
Fix old_province_name trong vietnam_administrative.json
Sử dụng dữ liệu xã/phường cũ từ madnh/hanhchinhvn để tra cứu chính xác.

Chiến lược disambiguation khi 1 tên xã ứng với nhiều tỉnh:
1. Lọc theo danh sách tỉnh cũ đã merge vào tỉnh mới (từ truocsapnhap cấp tỉnh)
2. Nếu vẫn ambiguous -> giữ kết quả đầu và lưu vào ambiguous_wards.json
"""

import json
import re
import unicodedata

from post_process_admin import parse_merged_from


def normalize_name(s: str) -> str:
    s = s.strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('đ', 'd').replace('Đ', 'D')
    return re.sub(r'\s+', ' ', s).lower()


print("=== FIX OLD_PROVINCE_NAME ===\n")
print("📂 Tải dữ liệu cũ...")

with open('old_wards.json', 'r', encoding='utf-8') as f:
    wards_old = json.load(f)
with open('old_districts.json', 'r', encoding='utf-8') as f:
    districts_old = json.load(f)
with open('old_provinces.json', 'r', encoding='utf-8') as f:
    provinces_old = json.load(f)

# ── Build lookup by full name (normalized) ────────────────────────────────────
lookup_by_fullname = {}   # "xa an thai" → [entries]
lookup_by_shortname = {}  # "an thai" -> [entries]

for code, w in wards_old.items():
    full_name = w.get('name_with_type', '')
    short_name = w.get('name', '')
    
    parent_district_code = w.get('parent_code', '')
    district_info = districts_old.get(parent_district_code, {})
    district_full = district_info.get('name_with_type', '')
    
    province_code = district_info.get('parent_code', '')
    province_info = provinces_old.get(province_code, {})
    province_full = province_info.get('name_with_type', '')
    
    entry = {
        "old_ward_name": full_name,
        "old_district_name": district_full or None,
        "old_province_name": province_full or None,
        "old_ward_code": code
    }
    
    key_full = normalize_name(full_name)
    if key_full not in lookup_by_fullname:
        lookup_by_fullname[key_full] = []
    lookup_by_fullname[key_full].append(entry)
    
    key_short = normalize_name(short_name)
    if key_short not in lookup_by_shortname:
        lookup_by_shortname[key_short] = []
    lookup_by_shortname[key_short].append(entry)

print(f"   → {len(lookup_by_fullname)} full-name keys")
print(f"   → {len(lookup_by_shortname)} short-name keys")

# ── Load province merger mapping (đã fix thủ công) ───────────────────────────
print("\n📂 Tải dữ liệu hành chính mới...")
with open('vietnam_administrative.json', 'r', encoding='utf-8') as f:
    new_data = json.load(f)

# Load province_merger_map đã được build và fix thủ công
with open('province_merger_map.json', 'r', encoding='utf-8') as f:
    _raw_map = json.load(f)
province_merger_map = {
    k: {normalize_name(p) for p in v}
    for k, v in _raw_map.items()
}

print("\n📊 Province merger map (sample):")
for p in new_data[:5]:
    pma = p['province_code']
    old_set = province_merger_map.get(pma, set())
    print(f"  {p['province_name']} ({pma}) <- {old_set}")


# ── Lookup function ───────────────────────────────────────────────────────────

def find_old_info(raw_name: str, new_province_code: str, district_hint: str | None = None) -> dict:
    allowed_norm = province_merger_map.get(new_province_code, set())
    district_hint_norm = normalize_name(district_hint or "")

    # Strategy 1: match full name
    key = normalize_name(raw_name)
    candidates = lookup_by_fullname.get(key, [])

    # Strategy 2: match short name (strip prefix)
    if not candidates:
        short_key = key
        for prefix in ['xa ', 'phuong ', 'thi tran ', 'thi xa ', 'dac khu ']:
            if short_key.startswith(prefix):
                short_key = short_key[len(prefix):]
                break
        candidates = lookup_by_shortname.get(short_key, [])

    if not candidates:
        return {"old_ward_name": raw_name, "old_district_name": None,
                "old_province_name": None, "_conf": "not_found"}

    # Filter by allowed provinces trước cả nhánh exact.
    # Một tên xã chỉ xuất hiện 1 lần trong old_wards.json vẫn có thể là sai tỉnh
    # nếu bản raw của xã mới đang nằm ở tỉnh mới khác.
    if allowed_norm:
        filtered = [c for c in candidates
                    if normalize_name(c.get('old_province_name', '')) in allowed_norm]
        if district_hint_norm and filtered:
            district_filtered = [
                c for c in filtered
                if normalize_name(c.get('old_district_name') or '') == district_hint_norm
            ]
            if len(district_filtered) == 1:
                c = district_filtered[0]
                return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                        "old_province_name": c['old_province_name'], "_conf": "district_hint"}
            if district_filtered:
                c = district_filtered[0]
                return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                        "old_province_name": c['old_province_name'], "_conf": "ambiguous_district_hint",
                        "_all": [f"{x['old_district_name']}, {x['old_province_name']}" for x in district_filtered]}
        if len(candidates) == 1 and len(filtered) == 1:
            c = filtered[0]
            return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                    "old_province_name": c['old_province_name'], "_conf": "exact"}
        if len(filtered) == 1:
            c = filtered[0]
            return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                    "old_province_name": c['old_province_name'], "_conf": "filtered"}
        if filtered:
            # Multiple matches within allowed → pick first, flag ambiguous
            c = filtered[0]
            return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                    "old_province_name": c['old_province_name'], "_conf": "ambiguous_region",
                    "_all": [f"{x['old_district_name']}, {x['old_province_name']}" for x in filtered]}

        # Có candidate theo tên, nhưng tất cả nằm ngoài tập tỉnh cũ hợp lệ của tỉnh mới.
        # Không được chọn đại candidate đầu tiên vì sẽ tạo lỗi trùng tên xã khác tỉnh
        # như Xã Phong Thịnh (Phú Thọ) bị gán sang Nghệ An.
        return {"old_ward_name": raw_name, "old_district_name": None,
                "old_province_name": None, "_conf": "not_allowed",
                "_all": [f"{x['old_district_name']}, {x['old_province_name']}" for x in candidates]}

    if len(candidates) == 1:
        c = candidates[0]
        return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
                "old_province_name": c['old_province_name'], "_conf": "exact"}

    # Fallback chỉ dùng khi không có province_merger_map cho tỉnh mới.
    c = candidates[0]
    return {"old_ward_name": raw_name, "old_district_name": c['old_district_name'],
            "old_province_name": c['old_province_name'], "_conf": "ambiguous",
            "_all": [f"{x['old_district_name']}, {x['old_province_name']}" for x in candidates]}


# ── Quick test ────────────────────────────────────────────────────────────────
print("\n--- Test Xã A Sào (tỉnh Hưng Yên mới code=33) ---")
for wn in ["Xã An Đồng", "Xã An Hiệp", "Xã An Thái", "Xã An Khê"]:
    r = find_old_info(wn, "33")
    print(f"  {wn}: {r['old_district_name']} | {r['old_province_name']} [{r['_conf']}]")


# ── Process all data ──────────────────────────────────────────────────────────
print("\n🔄 Cập nhật toàn bộ dữ liệu...")

stats = {}
ambiguous_cases = []
not_found_cases = []

for province in new_data:
    pma = province['province_code']
    for ward in province['wards']:
        if not ward.get('is_merged') or not ward.get('merged_from'):
            continue
        resolved_items = []
        source_entries = ward.get('merged_from') or []
        if ward.get('merged_from_raw'):
            source_entries = parse_merged_from(
                ward['merged_from_raw'], province['province_name']
            )

        for entry in source_entries:
            raw_name = entry['old_ward_name']
            district_hint = entry.get('old_district_name')

            # Tách các tên bị ghép bằng "và" thành nhiều entries riêng
            # Ví dụ: "Phường Khương Thượng và Phường Nam Đồng" → 2 entries
            sub_names = re.split(r'\s+v[àa]\s+', raw_name, flags=re.IGNORECASE)
            sub_names = [s.strip() for s in sub_names if s.strip()]

            for sub_name in sub_names:
                result = find_old_info(sub_name, pma, district_hint)
                conf = result.get('_conf', 'unknown')
                resolved_items.append((sub_name, result, conf))

        # Nếu một xã bị trùng tên ở tỉnh ngoài allowed set, nhưng các entry còn lại
        # trong cùng cụm sáp nhập đều chỉ về cùng huyện/tỉnh cũ hợp lệ, suy luận theo cụm.
        sibling_counts = {}
        for _, result, conf in resolved_items:
            district = result.get('old_district_name')
            old_province = result.get('old_province_name')
            if not district or not old_province:
                continue
            if conf not in {'exact', 'filtered', 'district_hint', 'ambiguous_region', 'ambiguous_district_hint'}:
                continue
            key = (district, old_province)
            sibling_counts[key] = sibling_counts.get(key, 0) + 1

        dominant_sibling = None
        if sibling_counts:
            ranked = sorted(sibling_counts.items(), key=lambda item: item[1], reverse=True)
            if ranked[0][1] >= 2 and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
                dominant_sibling = ranked[0][0]

        new_mf = []
        for sub_name, result, conf in resolved_items:
            old_district = result['old_district_name']
            old_province = result['old_province_name']

            if conf == 'not_allowed' and dominant_sibling:
                old_district, old_province = dominant_sibling
                conf = 'inferred_from_siblings'

            stats[conf] = stats.get(conf, 0) + 1

            clean_entry = {
                "old_ward_name": sub_name,
                "old_district_name": old_district,
                "old_province_name": old_province
            }
            new_mf.append(clean_entry)

            if 'ambiguous' in conf or conf == 'not_allowed':
                ambiguous_cases.append({
                    'province': province['province_name'],
                    'ward': ward['ward_name'],
                    'old_ward': sub_name,
                    'chosen': f"{old_district}, {old_province}",
                    'all_options': result.get('_all', [])
                })
            elif conf == 'not_found':
                not_found_cases.append({
                    'province': province['province_name'],
                    'ward': ward['ward_name'],
                    'old_ward': sub_name
                })

        ward['merged_from'] = new_mf


# ── Save ──────────────────────────────────────────────────────────────────────
total = sum(stats.values())
print(f"\n📊 Thống kê ({total} entries):")
for k in ['exact', 'district_hint', 'filtered', 'inferred_from_siblings', 'ambiguous_district_hint', 'ambiguous_region', 'ambiguous', 'not_allowed', 'not_found']:
    v = stats.get(k, 0)
    print(f"   {k:25s}: {v:5d} ({v/total*100:.1f}%)")

with open('vietnam_administrative.json', 'w', encoding='utf-8') as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)
print("\n✅ Đã lưu vietnam_administrative.json")

if ambiguous_cases:
    with open('ambiguous_wards.json', 'w', encoding='utf-8') as f:
        json.dump(ambiguous_cases, f, ensure_ascii=False, indent=2)
    print(f"⚠️  {len(ambiguous_cases)} ambiguous cases → ambiguous_wards.json")

if not_found_cases:
    with open('not_found_wards.json', 'w', encoding='utf-8') as f:
        json.dump(not_found_cases, f, ensure_ascii=False, indent=2)
    print(f"❓ {len(not_found_cases)} not-found cases → not_found_wards.json")

# ── Verify Xã A Sào ──────────────────────────────────────────────────────────
print("\n--- Kiểm tra kết quả Xã A Sào ---")
for p in new_data:
    if p['province_code'] == '33':
        for w in p['wards']:
            if w['ward_name'] == 'Xã A Sào':
                print(json.dumps(w, ensure_ascii=False, indent=2))
        break
