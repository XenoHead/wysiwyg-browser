import re

lines = open('C:/Git/WysiWyg-Browser/Adds/discogs_add.py').readlines()

# Fix the tracklist parser to strip "Track " / "Side N " prefixes (line ~286 area)
# Find the tracklist section
tracklist_start = None
for i, line in enumerate(lines):
    if '# --- Tracklist ---' in line:
        tracklist_start = i
        break

if tracklist_start:
    # Find the line with _tl = re.sub(r'(?i)^\\s*track\\s+', '', ln)
    for i in range(tracklist_start, tracklist_start + 40):
        if '_tl = re.sub' in lines[i] and 'track' in lines[i]:
            print(f"Found tracklist strip at line {i+1}: {lines[i].rstrip()}")
            break
    
    # Check current state
    print(f"\nCurrent tracklist section (lines {tracklist_start+1}-{tracklist_start+50}):")
    for i in range(tracklist_start, min(tracklist_start + 50, len(lines))):
        print(f"{i+1}|{lines[i].rstrip()}")

# Fix the catalog regex to not match words like "Title", "Here", etc.
# Find the catalog section
catalog_start = None
for i, line in enumerate(lines):
    if '# --- Catalog number ---' in line:
        catalog_start = i
        break

if catalog_start:
    print(f"\nCatalog section start: line {catalog_start+1}")
    for i in range(catalog_start, min(catalog_start + 50, len(lines))):
        print(f"{i+1}|{lines[i].rstrip()}")
