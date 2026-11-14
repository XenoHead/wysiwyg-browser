import re
import html
import pyperclip

def format_discogs_to_html(raw_text):
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    lines = [line for line in lines if "scraped via master release" not in line.lower()]
    if not lines: return "No text provided."

    # --- Header with Color Logic ---
    header_text = lines[0].replace('*', '')
    header_text = re.sub(r'\s*\(\d+\)', '', header_text)

    color = "black"
    if "vinyl" in raw_text.lower():
        color = "blue"
    elif "cd" in raw_text.lower():
        color = "red"

    header_text = re.sub(r'\s+(LP|EP)\s+\1', r' \1', header_text, flags=re.IGNORECASE)
    album_header = f'<p><span style="color: {color};"><b><u>{header_text.strip()}</u></b></span></p>'

    # --- Metadata Block ---
    metadata_lines = []
    tracklist_start_index = len(lines)

    for i, line in enumerate(lines[1:], 1):
        if line.lower().startswith("tracklist") or re.match(r'^[A-Z]?\d+', line):
            tracklist_start_index = i 
            break
        
        clean_line = line.replace('*', '')
        clean_line = re.sub(r'\s*\(\d+\)', '', clean_line)
        # "Track Count: 4" is scraper bookkeeping (it feeds the description text),
        # never part of the HTML listing.
        if re.match(r'^track\s*count\s*:', clean_line, re.IGNORECASE):
            continue
        if ":" in clean_line:
            key, val = clean_line.split(":", 1)
            clean_line = f"<b>{key}:</b>&nbsp;{val.strip()}"
        metadata_lines.append(clean_line)

    metadata_block = f"<p>{'<br>'.join(metadata_lines)}</p>"
    tracklist_header = "<p><b><u>Tracklist</u></b></p>"

    # --- Tracklist Body ---
    track_data = lines[tracklist_start_index:]
    # main.py emits the header as "Tracklist:" (with colon) - accept both forms so
    # it never leaks into the body as a stray line.
    if track_data and track_data[0].lower().startswith("tracklist"):
        track_data = track_data[1:]

    formatted_tracks = []
    for line in track_data:
        line = line.replace('*', '')
        line = re.sub(r'\s*\(\d+\)', '', line)

        # Improved Regex: Handles Tabs and various spacing
        # Group 1: Position, Group 2: Title, Group 3: Duration (optional)
        match = re.match(r'^([A-Z]?\d+)\s+(.*?)(?:\s+(\d+:\d+))?$', line)
        if match:
            pos, title, duration = match.groups()
            if duration:
                formatted_line = f"{pos} - {title.strip()} - {duration}"
            else:
                formatted_line = f"{pos} - {title.strip()}"
            formatted_tracks.append(html.escape(formatted_line))
        else:
            # If no match, just preserve the line (handles headings or odd formatting)
            formatted_tracks.append(html.escape(line))

    tracklist_body = f"<p>{'<br>'.join(formatted_tracks)}</p>"

    final_output = f"{album_header}{metadata_block}{tracklist_header}{tracklist_body}"

    try:
        pyperclip.copy(final_output)
    except:
        pass # Prevents crash if clipboard is busy

    return final_output
    
if __name__ == "__main__":
    print("Run main.py to start the web-based tool.")