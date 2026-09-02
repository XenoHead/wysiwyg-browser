import sys
lines = open('C:/Git/WysiWyg-Browser/Adds/discogs_add.py').readlines()

# Fix TITLE extraction: the spine text "Mercury Nashville - Greatest Hits" is being
# treated as title because artist=None and title_cands picks up the LAST consecutive
# title candidate. The title should be "Greatest Hits", not "Mercury Nashville - Greatest Hits".
# Fix: when title_cands has multiple entries on consecutive lines, pick the LAST one
# (which should be the actual album title, not the label prefix).
for i, line in enumerate(lines):
    if 'out["title"] = _last_in_run[2]' in line:
        print(f"Found title assignment at line {i+1}: {line.rstrip()}")
        # Show context
        for j in range(max(0,i-10), min(len(lines), i+5)):
            print(f"{j+1}|{lines[j].rstrip()}")
        break

print("\n--- Checking title_cands logic ---")
for i, line in enumerate(lines):
    if '_last_in_run = _run[0]' in line:
        print(f"Line {i+1}: {line.rstrip()}")
    if 'for t in _run[1:]' in line:
        print(f"Line {i+1}: {line.rstrip()}")
