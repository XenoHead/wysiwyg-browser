import sys, json
sys.path.insert(0, 'C:/Git/WysiWyg-Browser/Adds')
from discogs_add import parse_raw_text, discogs_add_macro
from Amazon_add_scraper import generate_html_block

print("=" * 60)
print("END-TO-END TEST: Mercury Nashville - Greatest Hits")
print("=" * 60)

# Simulate the EXACT raw_discogs_data that would come from a Discogs API URL lookup
# This is what the Amazon_add_scraper receives
raw_discogs = """Mercury Nashville - Greatest Hits
Label: Mercury Nashville 314-526 542-4, C108068
Format: Audio Cassette
Country: US
Released: January 15, 2024
Genre: Country
Style: Southern Rock
Track 1. Song One 3:45
Track 2. Song Two 4:12
Track 3. Song Three 3:30
Copyright © 2024 Mercury Nashville
Manufactured by Sony Music Entertainment
Barcode: 6 12345 67890 2"""

print("\n--- PHASE 1: discogs_add.py parse_raw_text ---")
parsed = parse_raw_text(raw_discogs)
print(f"artist:     {parsed.get('artist')}")
print(f"title:      {parsed.get('title')}")
print(f"label:      {parsed.get('label_literal')}")
print(f"cat_spine:  {parsed.get('cat_no_spine')}")
print(f"cat_all:    {parsed.get('cat_no_all')}")
print(f"tracklist:  {len(parsed.get('tracklist_raw', []))} tracks")
for t in parsed.get('tracklist_raw', []):
    print(f"  #{t['num']} {t['title']} ({t['duration']})")

print("\n--- PHASE 2: discogs_add_macro (with spine image 2160x838) ---")
extracted = {
    "raw_text": raw_discogs,
    "tracks": ["1. Song One 3:45", "2. Song Two 4:12", "3. Song Three 3:30"]
}
photos = [{"pixels": "2160 x 838", "raw_text": raw_discogs}]
result = discogs_add_macro(uploaded_media_photos=photos, extracted_data=extracted)
print(f"artist:     {result.get('artist')}")
print(f"title:      {result.get('title')}")
print(f"label:      {result.get('label_literal')}")
print(f"cat_spine:  {result.get('cat_no_spine')}")
print(f"cat_all:    {result.get('cat_no_all')}")
print(f"tracklist:  {len(result.get('tracklist_raw', []))} tracks")

print("\n--- PHASE 3: Amazon_add_scraper (generate_html_block) ---")
# The Amazon scraper receives the Discogs data and the artist from the API
html_blocks = generate_html_block(raw_discogs, result, "Real Artist Name")
print("HTML output snippet:")
print(html_blocks[:500])

print("\n" + "=" * 60)
print("VERIFICATION SUMMARY")
print("=" * 60)
print("1. Artist should NOT be company label name:")
artist_val = result.get('artist')
if artist_val is None:
    print("   PASS - artist=None (spine has no real artist; comes from Discogs API URL)")
else:
    print(f"   CHECK - artist={artist_val}")

print("2. Label should be 'Mercury Nashville':")
label_val = result.get('label_literal')
if label_val == 'MERCURY NASHVILLE':
    print("   PASS")
else:
    print(f"   FAIL - got '{label_val}'")

print("3. Catalog numbers present (314-526, 542-4, C108068):")
cats = result.get('cat_no_all', [])
if '314-526' in cats and '542-4' in cats and 'C108068' in cats:
    print(f"   PASS - all 3 found: {cats}")
else:
    print(f"   FAIL - got {cats}")

print("4. Tracklist parsed:")
tl = result.get('tracklist_raw', [])
if len(tl) == 3:
    print(f"   PASS - {len(tl)} tracks")
else:
    print(f"   FAIL - {len(tl)} tracks")
