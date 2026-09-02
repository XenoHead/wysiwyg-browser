import sys, json
sys.path.insert(0, 'C:/Git/WysiWyg-Browser')

from Adds.discogs_add import parse_raw_text, discogs_add_macro

print("=== TEST 1: parse_raw_text - Mercury Nashville spine ===")
raw = """Mercury Nashville - Greatest Hits
(c) 2024 Mercury Nashville
Manufactured by Sony Music Entertainment
314-526 542-4
C108068"""
parsed = parse_raw_text(raw)
print(json.dumps(parsed, indent=2))

print("\n=== TEST 2: discogs_add_macro with spine image (2160x838) ===")
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
for k, v in sorted(result.items()):
    if k not in ("Submission Notes",):
        print(f"  {k}: {v}")

print("\n=== TEST 3: Spine priority - label not mistaken for artist ===")
extracted2 = {
    "raw_text": """Mercury Nashville - Greatest Hits
314-526 542-4
(c) 2024 Mercury Nashville""",
    "artist": "Real Artist Name"  # This should NOT be overridden by spine parse
}
photos2 = [
    {"pixels": "2160 x 838", "raw_text": """Mercury Nashville - Greatest Hits
314-526 542-4
(c) 2024 Mercury Nashville"""}
]
result2 = discogs_add_macro(uploaded_media_photos=photos2, extracted_data=extracted2)
for k, v in sorted(result2.items()):
    if k not in ("Submission Notes",):
        print(f"  {k}: {v}")
