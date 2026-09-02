import re

lines = open('C:/Git/WysiWyg-Browser/Adds/discogs_add.py').readlines()

# Replace lines 214-230 (0-indexed 213-229) with comprehensive catalog extraction
new_block = """    # --- Catalog number -----------------------------------------------------
    # Collect ALL catalog numbers found, not just the first match.
    cats_found = []  # list of strings, normalised
    # 1) XXX-NNNNNN  (e.g. ZMC-80005)
    for _m in re.finditer(r'(?i)\\b([A-Z]{1,4})[-\\s](\\d{3,6})\\b', text):
        _c = f"{_m.group(1).upper()}-{_m.group(2)}"
        if _c not in cats_found:
            cats_found.append(_c)
    # 2) spine "0 NNNNN - NNNNN - N"  (Discogs catalogue w/ prefix digits; the
    #    trailing N is the format suffix: -1 CD, -2 CD, -4 Cassette).
    _m2 = re.search(r'(?i)(?:\\b0\\b\\s*)?(\\d{4,6})\\s*[-–]\\s*(\\d{4,6})(?:\\s*[-–]\\s*(\\d))?', text)
    if _m2 and _m2.group(1) != _m2.group(2):
        _c = f"{_m2.group(1).strip()}-{_m2.group(2).strip()}"
        if _m2.group(3):
            _c += f"-{_m2.group(3)}"
        if _c not in cats_found:
            cats_found.append(_c)
    # 3) bare number-number patterns WITHOUT leading letters (e.g. "314-526", "542-4").
    #    Only match when both sides are purely numeric so we don't consume date ranges.
    for _m in re.finditer(r'(?i)\\b(\\d{2,6})[-.](\\d{1,6})\\b', text):
        _c = f"{_m.group(1)}-{_m.group(2)}"
        if _c not in cats_found:
            cats_found.append(_c)
    # 4) C-prefix IDs like C108068 (single uppercase letter + 4+ digits, NO separator).
    for _m in re.finditer(r'(?i)\\b([A-Z])(\\d{4,})\\b', text):
        _c = f"{_m.group(1).upper()}{_m.group(2)}"
        if _c not in cats_found:
            cats_found.append(_c)
    if cats_found:
        # Normalise internal spaces in the numeric part.
        cats_found = [re.sub(r'\\s+', '', _c) for _c in cats_found]
        # Prefer the longest/most-specific catalog number as primary spine cat.
        cat = max(cats_found, key=lambda c: (len(c), c))
        out["cat_no_spine"] = cat
        out["cat_no_all"] = cats_found
"""

lines[213:230] = [new_block]
open('C:/Git/WysiWyg-Browser/Adds/discogs_add.py', 'w').writelines(lines)
print("Done. Lines 214-237:")
for i in range(213, 237):
    print(f"{i+1}|{lines[i].rstrip()}")
