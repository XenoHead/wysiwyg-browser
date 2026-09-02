import os
import sys
import json
import re
import logging
from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

router = APIRouter()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        base_local = os.path.dirname(sys.executable)
        try:
            base_bundled = sys._MEIPASS # pyright: ignore[reportAttributeAccessIssue]
        except Exception:
            base_bundled = os.path.abspath(".")
        
        local_path = os.path.join(base_local, relative_path)
        bundled_path = os.path.join(base_bundled, relative_path)
        
        if os.path.exists(local_path):
            return local_path
        return bundled_path
    else:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

@router.get("/walmart-sheet")
async def serve_walmart_sheet():
    """Serves the new blank page for the Walmart feature."""
    return FileResponse(resource_path("WalmartSheet/walmart.html"))

@router.get("/WalmartSheet/walmart.js")
async def serve_walmart_js():
    return FileResponse(resource_path("WalmartSheet/walmart.js"))

@router.get("/walmart.js")
async def serve_walmart_js_root():
    """Fallback route if walmart.html requests walmarts.js from root"""
    return FileResponse(resource_path("WalmartSheet/walmart.js"))

def parse_walmart_raw_text(text):
    """Parses the Discogs raw text blob for Walmart data."""
    info = { 'artist': '', 'title': '', 'label': '', 'cat': '', 'format': '', 'year': '', 'country': '', 'tracklist': [] }
    if not text: return info
    lines = text.split('\n')
    if not lines: return info

    # Line 1: Artist - Title
    parts = lines[0].split(' - ', 1)
    if len(parts) == 2:
        info['artist'] = parts[0].strip()
        info['title'] = parts[1].strip()
    else:
        info['artist'] = lines[0].strip()

    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if line.startswith('Label:'):
            clean = line.replace('Label:', '').strip()
            tokens = clean.split(' ')
            cat_parts = []
            temp_label = []
            for token in tokens:
                # Strip trailing punctuation (commas, semicolons, colons) for detection only
                token_clean = token.rstrip(',;:')
                if (re.search(r'[A-Z]', token_clean) and re.search(r'[0-9]', token_clean) and not any(l.islower() for l in token_clean if l.isalpha())) or re.match(r'^[A-Z0-9\-]{4,}$', token_clean):
                     cat_parts.append(token_clean)
                else:
                     temp_label.append(token)
            
            info['label'] = " ".join(temp_label).strip()
            info['cat'] = " / ".join(cat_parts).strip()

            if not info['cat'] and len(tokens) > 1:
                info['cat'] = tokens[-1].rstrip(',;:')
                info['label'] = " ".join(tokens[:-1]).strip()
            if not info['label'] and info['cat']:
                info['label'] = clean.replace(info['cat'], '').strip()
            elif not info['label'] and not info['cat']:
                info['label'] = clean

        elif line.startswith('Format:'):
            info['format'] = line.replace('Format:', '').strip()
        elif line.startswith('Released:'):
            info['year'] = line.replace('Released:', '').strip()
        elif line.startswith('Country:'):
            info['country'] = line.replace('Country:', '').strip()
        elif i > 0 and re.match(r'^\d+[\.\)]\s+', stripped):
            # Tracklist entry: "1. Track Title" or "1) Track Title"
            track_title = re.sub(r'^\d+[\.\)]\s*', '', stripped)
            info['tracklist'].append(track_title.strip())
        elif i > 0 and re.match(r'^\d+:\d+\s+', stripped):
            # Tracklist entry with timestamp: "3:45 Track Title"
            track_title = re.sub(r'^\d+:\d+\s*', '', stripped)
            info['tracklist'].append(track_title.strip())
            
    return info

def map_walmart_media_format(raw_fmt):
    """Maps Discogs format to Walmart format and gets dimensions key."""
    lower_fmt = raw_fmt.lower()
    walmart_fmt = "CD"
    
    if "cassette" in lower_fmt:
        walmart_fmt = "Cassette Tape"
    elif "lp" in lower_fmt or "vinyl" in lower_fmt:
        walmart_fmt = "Vinyl Record"
    elif "dvd" in lower_fmt:
        walmart_fmt = "DVD"
    elif "blu-ray" in lower_fmt:
        walmart_fmt = "Blu-ray"
    elif '7"' in lower_fmt:
        walmart_fmt = "Vinyl Record"
        
    return walmart_fmt

@router.post("/api/walmart/process-item")
async def process_walmart_item(data: dict = Body(...)):
    raw_text = data.get("raw_text", "")
    builder_desc = data.get("generatedDescription", "").strip()
    builder_label_input = data.get("label", "").strip() # Prioritize data from Builder Tab
    
    parsed = parse_walmart_raw_text(raw_text)
    artist = re.sub(r'\s*\(\d+\)$', '', parsed['artist']).strip()
    title = parsed['title']

    # Determine Label and Cat primarily from the Builder tab input
    extracted_cat = ""
    if builder_label_input:
        # Split by '/' to handle multiple labels and take the first one
        first_entry = builder_label_input.split('/')[0].strip()
        
        # Separate Name and Cat from this entry using the token heuristic
        tokens = first_entry.split()
        builder_cat_parts = []
        name_parts = []
        for token in tokens:
            token_clean = token.rstrip(',;:')
            if (re.search(r'[A-Z]', token_clean) and re.search(r'[0-9]', token_clean) and not any(l.islower() for l in token_clean if l.isalpha())) or re.match(r'^[A-Z0-9\-]{4,}$', token_clean):
                builder_cat_parts.append(token_clean)
            else:
                name_parts.append(token)
        
        label = " ".join(name_parts).strip()
        extracted_cat = " ".join(builder_cat_parts).strip()
        
        # Fallback: if heuristic missed the Cat# but there are multiple tokens, assume last is Cat#
        if not extracted_cat and len(tokens) > 1:
            extracted_cat = tokens[-1]
            label = " ".join(tokens[:-1]).strip()
    else:
        # Fallback to API-based parsing if Builder field is empty
        label = parsed['label'].split('/')[0].strip() if '/' in parsed['label'] else parsed['label']
        extracted_cat = parsed['cat'].split('/')[0].strip() if '/' in parsed['cat'] else parsed['cat']

    # If no catalog number was found from the builder label field or API parsing,
    # try to find a UPC/GTIN (12 or 13 digits) in the raw_text.
    if not extracted_cat:
        gtin_match = re.search(r'\b(\d{12,13})\b', raw_text.replace('-', '').replace(' ', ''))
        if gtin_match:
            extracted_cat = gtin_match.group(1) # Use the found GTIN as the manufacturerPartNumber

    # Clean up any Discogs duplicate identifiers (e.g., "Arista (2)")
    label = re.sub(r'\s*\(\d+\)$', '', label).strip()
    year = parsed['year']
    
    media_fmt = map_walmart_media_format(parsed['format'])
    media_count = 1
    count_match = re.search(r'(\d+)x', parsed['format'])
    if count_match:
        media_count = int(count_match.group(1))
        
    # Standardize format naming and apply "Audio " prefix for specific categories
    display_fmt = "Cassette" if media_fmt == "Cassette Tape" else media_fmt
    if "Vinyl" in display_fmt:
        display_fmt = "LP Vinyl"
    
    media_desc_no_audio = f"{media_count}x{display_fmt}" if media_count > 1 else display_fmt
    
    # Validation: Ensure "Audio " is only prepended to specific audio formats
    # and explicitly excluded for non-audio formats like DVD or Blu-ray.
    audio_whitelist = ["CD", "Vinyl", "Cassette Tape"]
    is_video = any(vid in media_fmt for vid in ["DVD", "Blu-ray", "Video"])
    audio_prefix = "Audio " if media_fmt in audio_whitelist and not is_video else ""
    product_name_media_desc = f"{audio_prefix}{media_desc_no_audio}"

    product_name = f"{artist} - {title} - {product_name_media_desc}"

    if builder_desc:
        # Remove Out-of-Print mentions for Walmart specifically
        builder_desc = builder_desc.replace("is Out-of-Print", "").replace("Out-of-Print", "").replace("  ", " ").strip()
        
        # Deduplicate: Remove the redundant media format string from the builder description part
        patterns_to_remove = [
            rf'\b{media_count}x{re.escape(display_fmt)}\b',
            rf'\b{media_count}x{re.escape(media_fmt)}\b',
            rf'\b{re.escape(display_fmt)}\b',
            rf'\b{re.escape(media_fmt)}\b'
        ]
        
        clean_builder_desc = builder_desc
        for pattern in patterns_to_remove:
            clean_builder_desc = re.sub(pattern, '', clean_builder_desc, flags=re.IGNORECASE).strip()
            
        clean_builder_desc = re.sub(r'\s+', ' ', clean_builder_desc).strip()
        site_desc = f"{artist} - {title} - {product_name_media_desc} - {clean_builder_desc}"
    else:
        site_desc = ""

    release_date = ""
    if year and len(year) == 4:
        release_date = f"{year}-01-01"
    elif year:
        release_date = year

    return {
        "productName": product_name,
        "sellingPrice": "",
        "siteDescription": site_desc,
        "condition": "New" if ("Factory Sealed" in builder_desc or "Factory New Not Sealed" in builder_desc) else "Used",
        "manufacturerPartNumber": extracted_cat,
        "mediaFormat": media_fmt,
        "musicGenre": "",
        "musicMediaFormat": media_fmt,
        "numberOfDiscs": media_count,
        "originalReleaseDate": release_date,
        "performer": artist,
        "recordLabel": label,
        "title": title,
        "tracklist": parsed.get('tracklist', []),
    }

@router.post("/api/walmart/save-pulldowns")
async def save_walmart_pulldowns(new_data: dict = Body(...)):
    """Saves the pulldowns configuration to WalmartSheet/pulldowns.json."""
    local_path = resource_path(os.path.join("WalmartSheet", "pulldowns.json"))
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/api/walmart/cache-context")
async def cache_walmart_context(data: dict = Body(...)):
    cache_path = resource_path("walmart_context_cache.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/walmart/cache-context")
async def get_cached_walmart_context():
    cache_path = resource_path("walmart_context_cache.json")
    if not os.path.exists(cache_path):
        return JSONResponse(status_code=404, content={"status": "error", "message": "No cached context found."})
    try:
        return FileResponse(cache_path, media_type="application/json")
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
