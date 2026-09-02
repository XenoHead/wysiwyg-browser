import sys, json, re
sys.path.insert(0, 'C:/Git/WysiWyg-Browser')
from Adds.discogs_add import parse_raw_text, discogs_add_macro

print("=== BUG 1: Artist should NOT be label name ===")
raw = """Mercury Nashville - Greatest Hits
(c) 2024 Mercury Nashville
Manufactured by Sony Music Entertainment
314-526 542-4
C108068"""
parsed = parse_raw_text(raw)
print(f"  artist: {parsed.get('artist')}")
print(f"  title: {parsed.get('title')}")
print(f"  label_literal: {parsed.get('label_literal')}")
print(f"  cat_no_spine: {parsed.get('cat_no_spine')}")
print()

print("=== BUG 2: Label 'Mercury Nashville' regex test ===")
m = re.search(r'(?i)\b((?:revolution|discos?|sony|bmc?|warner|capitol|mca|universal|emi|atlantic|arista|geffen|mercury|polydor|island|elektra|epic|virgin|columbia)\s+records?)\b', "label Mercury Nashville")
print(f"  Match (records): {m.group(1) if m else 'NONE'}")
m2 = re.search(r'(?i)\b((?:mercury|polydor)\s+[A-Z][a-z]+)\b', "Mercury Nashville")
print(f"  Match (mercury+nashville): {m2.group(1) if m2 else 'NONE'}")
print()

print("=== BUG 3: Catalog numbers ===")
raw2 = """Some Artist - Some Title
314-526
542-4
C108068
(c) 2024 Label Name"""
parsed2 = parse_raw_text(raw2)
print(f"  cat_no_spine: {parsed2.get('cat_no_spine')}")
print(f"  cat_no_all: {parsed2.get('cat_no_all')}")
print()

print("=== BUG 4: Tracklist ===")
raw3 = """Mercury Nashville - Greatest Hits
314-526 542-4
C108068
Track 1. Song One 3:45
Track 2. Song Two 4:12
Track 3. Song Three 3:30
(c) 2024 Mercury Nashville"""
parsed3 = parse_raw_text(raw3)
print(f"  tracklist_raw: {json.dumps(parsed3.get('tracklist_raw'), indent=2)}")
print()

print("=== FULL TEST: discogs_add_macro with spine image ===")
extracted = {
    "raw_text": """Mercury Nashville - Greatest Hits
314-526 542-4 C108068
(c) 2024 Mercury Nashville
Track 1. Song One 3:45
Track 2. Song Two 4:12
Track 3. Song Three 3:30""",
    "tracks": ["1. Song One 3:45", "2. Song Two 4:12", "3. Song Three 3:30"]
}
photos = [
    {"pixels": "2160 x 838", "raw_text": """Mercury Nashville - Greatest Hits
314-526 542-4 C108068
(c) 2024 Mercury Nashville
Track 1. Song One 3:45
Track 2. Song Two 4:12
Track 3. Song Three 3:30"""},
    {"pixels": "838 x 2160", "raw_text": "Some other image OCR"}
]
result = discogs_add_macro(uploaded_media_photos=photos, extracted_data=extracted)
print(f"  artist: {result.get('artist')}")
print(f"  title: {result.get('title')}")
print(f"  label_literal: {result.get('label_literal')}")
print(f"  cat_no_spine: {result.get('cat_no_spine')}")
print(f"  cat_no_all: {result.get('cat_no_all')}")
print(f"  tracklist_raw: {json.dumps(result.get('tracklist_raw'), indent=2)}")
