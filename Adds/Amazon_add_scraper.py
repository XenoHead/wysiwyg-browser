import os
import re
import json

# --- Load rules from JSON (single source of truth) ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_RULES_PATH = os.path.join(_THIS_DIR, "Amazon_add_scraper_rules.json")
try:
    with open(_RULES_PATH, "r", encoding="utf-8") as _rf:
        _RULES = json.load(_rf)
except Exception as _e:  # pragma: no cover - defensive
    _RULES = {}

BINDING_MAP = _RULES.get("binding_map", {})
EDITION_LOG = _RULES.get("edition_log", [])
VINYL_DETAILS_LOG = _RULES.get("vinyl_details_log", [])
AMAZON_FORMAT_LOG = _RULES.get("amazon_format_log", [])
SPELLING_CORRECTIONS = _RULES.get("spelling_corrections", {})


def clean_name(name):
    """Removes asterisks, (Number) notations, and converts subtitles in () to - """
    if not name: return ""
    cleaned = name.replace('*', '')
    # 1. Remove the (2) or (3) Discogs artist numbers
    cleaned = re.sub(r'\s*\(\d+\)', '', cleaned)
    
    # 2. NEW RULE: Convert (Subtitle) to - Subtitle
    # This looks for a space followed by text in parentheses at the end of the string
    cleaned = re.sub(r'\s*\(([^)]+)\)', r' - \1', cleaned)
    
    # 3. Clean up any resulting double dashes or trailing spaces
    cleaned = cleaned.replace(' -  - ', ' - ').strip()
    return cleaned.strip()

# --- VERSION 3.0 LABEL LOGIC: ISOLATED FOR HTML ONLY ---
def process_labels_3_0(label_info_list):
    """
    Refined 4.19: If 'Not On Label' or 'none' is detected, 
    returns None to trigger a full line deletion in HTML.
    """
    names = []
    cats = []
    
    for item in label_info_list:
        # Strict Omission Check
        if item['name'].lower() in ['not on label', 'none', '']:
            continue
        if item['name'] not in names:
            names.append(item['name'])
        if item['cat'] and item['cat'].lower() != 'none' and item['cat'] not in cats:
            cats.append(item['cat'])
    
    if not names: # Trigger for total line removal
        return None
        
    label_str = " / ".join(names)
    if cats:
            cat_str = " / ".join(cats) # Define cat_str first
            return f"{label_str} – {cat_str}"
    return label_str

def infer_bullet_point(format_string):
    f_lower = format_string.lower()
    # NEW RULE: Specific mapping for CD Video (CDV)
    if 'cdv' in f_lower:
        return 'Audio - CDV'
    
    if 'vinyl' in f_lower and '12"' in f_lower:
        return '12" - Vinyl'     
    if 'blu-ray' in f_lower:
        if 'audio' in f_lower: return 'Blu-ray - Audio'
        return 'Blu-ray - Video'
    format_map = {
        'cd': 'Audio - CD', 
        'lp': 'LP - Vinyl', 
        'vinyl': 'LP - Vinyl', 
        'cassette': 'Audio - Cassette', 
        'dvd': 'DVD - Video'
    }
    for key, value in format_map.items():
        if key in f_lower: return value
    return 'Music - Various Format'

def calculate_accurate_disc_count(raw_discogs_data):
    """
    Cross-references the multi-line Format block and the Tracklist 
    to accurately total all physical media components (LPs, CDs, DVDs).
    """
    lines = raw_discogs_data.split('\n')
    
    # --- STEP 1: Parse Multi-Line Format Header ---
    format_lines = []
    in_format = False
    for line in lines:
        if line.startswith('Format:'):
            in_format = True
            format_lines.append(line.replace('Format:', '').strip())
            continue
        if in_format:
            # Stop when hitting the next standard Discogs header
            if any(line.startswith(h) for h in ['Country:', 'Released:', 'Genre:', 'Style:', 'Label:', 'Series:']):
                break
            if line.strip():
                format_lines.append(line.strip())

    full_format_str = "\n".join(format_lines)

    # Sum all explicitly listed quantity multipliers (e.g., "2 x Vinyl", "5 x CD")
    multipliers = re.findall(r'(\d+)\s*[x×]', full_format_str, re.I)
    
    # Sum single media occurrences (e.g., "Vinyl, LP", "DVD, DVD-Video" without an 'x')
    single_media_lines = [
        l for l in format_lines 
        if not re.search(r'\d+\s*[x×]', l, re.I) and 
        re.search(r'\b(Vinyl|LP|CD|DVD|Blu-ray|Cassette)\b', l, re.I)
    ]

    total_from_format = sum(int(m) for m in multipliers) + len(single_media_lines)
    
    if total_from_format > 0:
        return str(total_from_format)

    # --- STEP 2: Fallback Cross-Reference via Tracklist Prefixes ---
    # Scans track prefixes like "CD1-1", "CD6-2", "DVD-1", "LP1-A1", etc.
    track_prefixes = re.findall(r'^\s*([A-Z]+(?:\d+)?)\s*[\.-]', raw_discogs_data, re.MULTILINE | re.I)
    
    if track_prefixes:
        # Standardize and isolate unique disc identifiers (e.g., 'CD1', 'CD2', 'DVD')
        unique_discs = set(p.upper() for p in track_prefixes if re.match(r'^(CD|DVD|LP|BD|CASSETTE)\d*', p, re.I))
        if len(unique_discs) > 0:
            return str(len(unique_discs))

    return '1'

def generate_html_block(raw_discogs_data, stored_data, artist_name):
    corrected_data = raw_discogs_data
    for misspelled, correct in SPELLING_CORRECTIONS.items():
        corrected_data = re.sub(r'\b' + re.escape(misspelled) + r'\b', correct, corrected_data, flags=re.IGNORECASE)
    
    html_output = ""
    lines = corrected_data.split('\n')
    header_clean = clean_name(lines[0].replace('More images', ''))
    html_output += f"<p><b><u>{header_clean}</u></b></p>"

    metadata_lines = []
    tracklist_start_index = -1
    is_tape_or_vinyl = False
    target_headers = ['Label:', 'Series:', 'Format:', 'Country:', 'Released:', 'Genre:', 'Style:']
    for i, line in enumerate(lines):
        header_match = next((h for h in target_headers if line.startswith(h)), None)
        if header_match:
            if header_match == 'Label:':
                label_val = stored_data.get('Html_Label_Display')
                if not label_val or artist_name.lower() in label_val.lower():
                    continue
                metadata_lines.append(f"Label: {label_val}")
            elif header_match in ['Country:', 'Released:']:
                val = line.split(':', 1)[1].strip()
                if val and val.lower() not in ['none', 'unknown', '']:
                    metadata_lines.append(line)
            elif header_match in ['Format:', 'Genre:', 'Style:']:
                clean_line = line.strip()
                clean_line = re.sub(r',?\s*Unofficial Release\s*', '', clean_line, flags=re.IGNORECASE).strip()
                clean_line = clean_line.rstrip(',')
                if header_match == 'Format:':
                    if any(x in clean_line.lower() for x in ['cassette', 'vinyl', 'lp']): 
                        is_tape_or_vinyl = True
                metadata_lines.append(clean_line)
        elif re.match(r'([A-Z]\d+|\d+\.)', line):
            tracklist_start_index = i
            break
    metadata_block = "<br>".join(metadata_lines).replace('Not On Label', '').strip()
    metadata_block = metadata_block.replace(': ', ':&nbsp;').replace('&', '&amp;')
    metadata_block = re.sub(r'(Label:&nbsp;)\s*–\s*', r'\1', metadata_block)
    metadata_block = re.sub(r'(Label:&nbsp;[^<]+?)\s*–\s*([^<]+)', r'\1 – \2', metadata_block)
    metadata_block = re.sub(r'<br>Style:&nbsp;$', '', metadata_block).strip()
    metadata_block = re.sub(r'^Style:&nbsp;$', '', metadata_block).strip() 
    html_output += f"<p>{metadata_block}</p><p><b><u>Tracklist</u></b></p>"
    tracklist_lines = []
    seq_counter = 0
    if tracklist_start_index != -1:
        for line in lines[tracklist_start_index:]:
            if any(line.startswith(x) for x in ['Copyright', 'Phonographic', 'Manufactured By']): break
            cleaned = line.strip().replace('PositionTitle/CreditsDuration', '').replace('*', '').replace('\t', ' ')
            if not cleaned: continue      
            match_pos = re.match(r'^([A-Z]\d+|\d+\.|\d+|MP3\s\d+|Video\s\d+)', cleaned, re.I)
            if match_pos:
                raw_pos = match_pos.group(1).replace('.', '').strip()
                remainder = cleaned[len(match_pos.group(0)):].strip().lstrip('-').strip()
                match_duration = re.search(r'(\d+:\d{2})$', remainder)
                if match_duration:
                    track_title_only = remainder[:match_duration.start()].strip()
                    tracklist_lines.append(f"{raw_pos} - {track_title_only}")
                else:
                    tracklist_lines.append(f"{raw_pos} - {remainder}")
            else:
                if len(cleaned) > 2: # Ignore stray characters
                    tracklist_lines.append(f"<b>{cleaned}</b>")
    html_output += f"<p>{'<br>'.join(tracklist_lines)}</p>"
    stored_data['HTML Product Description'] = html_output
    return stored_data
def process_discogs_raw_data(raw_discogs_data):
    """PHASE 1: INGESTION ONLY."""
    global DISCOGS_DATA_STORAGE
    lines = raw_discogs_data.split('\n')   
    artist_title_raw = lines[0].replace('—', '-').replace('–', '-')
    artist_title = clean_name(artist_title_raw)
    if '-' in artist_title:
        parts = artist_title.split('-', 1)
        artist_only = clean_name(parts[0])
        title_only = clean_name(parts[1])
    else:
        artist_only = clean_name(artist_title)
        title_only = "Unknown Title"
    final_item_name = title_only
    artist = clean_name(artist_title.split('-')[0]) if '-' in artist_title else clean_name(artist_title) 
    format_line = next((l for l in lines if l.startswith('Format:')), '').strip()
    series_line = next((l for l in lines if l.startswith('Series:')), '').replace('Series:', '').strip()
    series_line = re.sub(r'Record Store Day,?\s*', '', series_line, flags=re.I).strip().rstrip(',')
    genre_line = next((l for l in lines if l.startswith('Genre:')), '').replace('Genre:', '').strip()
    style_line = next((l for l in lines if l.startswith('Style:')), '').replace('Style:', '').strip()
    combined_genre_style = f"{genre_line}, {style_line}" if style_line else genre_line

# --- INSERT VERSION 3.6 UPDATE HERE ---
    raw_country_line = next((l for l in lines if l.startswith('Country:')), '').replace('Country:', '').strip()
    
    country_map = {
        'Australasia': 'Australia',
        'Europe': 'Germany',
        'UK': 'United Kingdom',
        'UK & Europe': 'United Kingdom',
        'US': 'United States',
        'USA': 'United States',
        'Worldwide': 'United States'
    }
    
    # Country/Region of Origin is ALWAYS United States (our selling origin),
    # regardless of the release's pressing country.
    final_origin = 'United States'
    tags_found = []
    for e in EDITION_LOG:
        if re.search(r'\b' + re.escape(e) + r'\b', raw_discogs_data, re.IGNORECASE):
            tags_found.append(e.title())
    if "compilation" in format_line.lower() and "Compilation" not in tags_found:
        tags_found.append("Compilation")
    if "reissue" in format_line.lower() and "Reissue" not in tags_found:
        tags_found.append("Reissue")
    if re.search(r'\bindie\s+exclusive\b', raw_discogs_data, re.IGNORECASE) and "Indie Exclusive" not in tags_found:
        tags_found.append("Indie Exclusive")
    tags_found = [t for t in tags_found if t not in ["Standard", "Standard Edition"]]
    final_edition_tags = ", ".join(tags_found) if tags_found else None
    num_discs = calculate_accurate_disc_count(raw_discogs_data)
    release_line = next((l for l in lines if 'Released:' in l), '').replace('Released:', '').strip()
    months_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05'
    }
    
    full_date_match = re.search(r'([a-zA-Z]{3})\s+(\d{1,2}),?\s+(\d{4})', release_line, re.I)
    
    if full_date_match:
        m_name = full_date_match.group(1).lower()[:3]
        day = full_date_match.group(2).zfill(2)
        year = full_date_match.group(3)
        month = months_map.get(m_name, '01')
        pub_date = f"{year}-{month}-{day}"
    else:
        year_match = re.search(r'(\d{4})', release_line)
        if not year_match and 'cd' in format_line.lower():
            year_val = '1995'
        elif not year_match and 'dvd' in format_line.lower():
            year_val = '2000'
        else:
            year_val = year_match.group(1) if year_match else '1970'
        if "IFPI" in raw_discogs_data and int(year_val) < 1994:
            year_val = '1994'
        pub_date = f"{year_val}-01-01"
    amazon_artist_clean = artist.replace(' / ', ', ').replace(' – ', ', ')
    detected_formats = []
    final_format_value = None 
    if re.search(r'\b(2\s*x?\s*LP|2\s*x?\s*Vinyl)\b', format_line, re.IGNORECASE):
        if "Double LP" not in detected_formats:
            detected_formats.append("Double LP")
    for format_option in AMAZON_FORMAT_LOG:
        if re.search(r'\b' + re.escape(format_option) + r'\b', format_line, re.IGNORECASE):
            detected_formats.append(format_option)
    if "Single" in detected_formats:
        final_format_value = "Single"
    elif "EP" in detected_formats:
        final_format_value = "EP"
    elif "Double CD" in detected_formats:
        final_format_value = "Double CD"
    elif detected_formats:
        final_format_value = detected_formats[0]
    priority_formats = ["Single", "EP", "Double CD", "Double LP", "Box set"]
    ordered_formats = [f for f in priority_formats if f in detected_formats]
    ordered_formats.extend([f for f in detected_formats if f not in priority_formats])
    amazon_formats_max = ordered_formats[:5]
    final_format_value = ", ".join(amazon_formats_max) if amazon_formats_max else None
    if "Record Store Day" in raw_discogs_data:
        final_format_value = "Limited Edition"
        if "Record Store Day" not in tags_found:
            tags_found.append("Record Store Day")
    if final_format_value in tags_found:
        tags_found.remove(final_format_value)
    is_import = final_origin not in ['United States']
    if is_import:
        if not final_format_value:
            final_format_value = "Import"
        elif "Import" not in amazon_formats_max and len(amazon_formats_max) < 5:
            amazon_formats_max.append("Import")
            final_format_value = ", ".join(amazon_formats_max)
        elif "Import" not in tags_found:
            tags_found.append("Import")
    overflow_terms = [f for f in detected_formats if f not in amazon_formats_max]
    for term in overflow_terms:
        if term not in tags_found:
            tags_found.append(term)
    seen_tags = set()
    unique_tags = []
    for t in tags_found:
        if t.lower() not in seen_tags and t not in ["Standard", "Standard Edition"]:
            seen_tags.add(t.lower())
            unique_tags.append(t)
    final_edition_tags = ", ".join(unique_tags) if unique_tags else None
    found_vinyl_options = []
    for detail in VINYL_DETAILS_LOG:
        if re.search(re.escape(detail), format_line, re.IGNORECASE):
            found_vinyl_options.append(detail)
    final_vinyl_details = ", ".join(found_vinyl_options) if found_vinyl_options else None
    v_detail_1 = found_vinyl_options[0] if len(found_vinyl_options) > 0 else None
    v_detail_2 = found_vinyl_options[1] if len(found_vinyl_options) > 1 else None
    v_detail_3 = found_vinyl_options[2] if len(found_vinyl_options) > 2 else None
    DISCOGS_DATA_STORAGE = {
        'Raw Data': raw_discogs_data, 
        'Item Name': final_item_name,
        'Artist(s)': amazon_artist_clean,
        'Composer': amazon_artist_clean,
        'Performer': amazon_artist_clean,
        'PRODUCT_TYPE': "Music", 
        'Publication Date': pub_date, 
        'Country/Region of Origin': final_origin,
        'Bullet Point': infer_bullet_point(format_line), 
        'Binding': next((v for k, v in BINDING_MAP.items() if k in format_line.lower()), 'Music'),
        'Format:': final_format_value,
        'Edition': final_edition_tags, 
        'Number Of Discs': num_discs, 
        'Vinyl Record Details 1': v_detail_1,
        'Vinyl Record Details 2': v_detail_2,
        'Vinyl Record Details 3': v_detail_3,
	'Series': series_line if series_line else None, # Add this to storage
        'Genre_Style': combined_genre_style,
        'Part Number': 'N/A' 
    }
    if DISCOGS_DATA_STORAGE.get('Part Number') in ['N/A', '', None]:
        cat_match = re.search(r'Label:.*?\s–\s*([^,\n]+)', raw_discogs_data, re.I)
        if cat_match:
            DISCOGS_DATA_STORAGE['Part Number'] = cat_match.group(1).strip()
        else:
            # Only check Matrix if Label Cat is missing
            matrix_match = re.search(r'Matrix\s*/\s*Runout:?\s*([^\n\r,]+)', raw_discogs_data, re.I)
            if matrix_match:
                DISCOGS_DATA_STORAGE['Part Number'] = matrix_match.group(1).strip()
    label_line = next((l for l in lines if l.startswith('Label:')), '').replace('Label:', '').strip()
    label_info_list = []
    brand_names_only = []
    cat_group_map = {} # Format: { 'CAT#': [Label1, Label2] }
    raw_pairs = label_line.split(',') 
    for pair in raw_pairs:
        if '–' in pair:
            parts = pair.split('–')
            lbl_name = parts[0].strip()
            lbl_name = re.sub(r'^Label:\s*', '', lbl_name).strip()
            cat_no = parts[1].split(',')[0].strip()
            if lbl_name not in brand_names_only:
                brand_names_only.append(clean_name(lbl_name))
            if cat_no not in cat_group_map:
                cat_group_map[cat_no] = []
            if lbl_name not in cat_group_map[cat_no]:
                cat_group_map[cat_no].append(lbl_name)  
            label_info_list.append({'name': lbl_name, 'cat': cat_no})
            if DISCOGS_DATA_STORAGE.get('Part Number') in ['N/A', '', None]:
                DISCOGS_DATA_STORAGE['Part Number'] = cat_no
        else:
            lbl_name = pair.strip()
            label_info_list.append({'name': lbl_name, 'cat': ''})
            if lbl_name and clean_name(lbl_name) not in brand_names_only:
                brand_names_only.append(clean_name(lbl_name))
    label_parts = []
    for cat, labels in cat_group_map.items():
        label_string = " / ".join(labels)
        label_parts.append(f"{label_string} – {cat}")
    consolidated_label_display = " - ".join(label_parts) if label_parts else None
    DISCOGS_DATA_STORAGE['Html_Label_Display'] = consolidated_label_display if consolidated_label_display else process_labels_3_0(label_info_list)
    DISCOGS_DATA_STORAGE['Label_List'] = list(dict.fromkeys(brand_names_only))
    # --- END ISOLATED LABEL LOGIC ---  
    barcode_line = next((l for l in lines if l.startswith('Barcode')), None)
    if barcode_line:
        barcode_match = re.search(r'(\d{12,13})', barcode_line)
        barcode_val = barcode_match.group(1) if barcode_match else '*(Not found)*'
        id_type = 'UPC' if len(barcode_val) == 12 else 'GTIN'
    else:
        barcode_val = '*(Not found)*'
        id_type = 'UPC/GTIN'   
    DISCOGS_DATA_STORAGE.update({
        'UPC/GTIN (Scanned)': barcode_val, 
        'ID_Type': id_type
    }) 
    DISCOGS_DATA_STORAGE = generate_html_block(raw_discogs_data, DISCOGS_DATA_STORAGE, artist)
    return "LOCKED: Waiting for Phase 2."
def process_seller_info_and_generate_asin(seller_info_data):
    """PHASE 2: INTERACTIVE HANDSHAKE."""
    global DISCOGS_DATA_STORAGE
    price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2}))', seller_info_data)
    comments_match = re.search(r'Comments\s*([\s\S]*?)Location:', seller_info_data)
    DISCOGS_DATA_STORAGE['Your Price'] = price_match.group(1).replace(',', '') if price_match else '0.00'
    DISCOGS_DATA_STORAGE['SKU'] = re.search(r'Location:\s*(\S+)', seller_info_data).group(1) if re.search(r'Location:\s*(\S+)', seller_info_data) else 'NEED-SKU'
    comments_match = re.search(r'Comments\s*([\s\S]*?)Location:', seller_info_data)
    DISCOGS_DATA_STORAGE['Offer Condition Note'] = comments_match.group(1).strip() if comments_match else ''
    # Item Condition is ALWAYS derived from the Offer Condition Note: the
    # worst (lowest) rating present, reported as "Collectable - <rating>".
    DISCOGS_DATA_STORAGE['Item Condition'] = derive_item_condition(
        DISCOGS_DATA_STORAGE.get('Offer Condition Note', ''))
    # (Interactive selection prompts removed — the API path supplies the
    #  condition choice and spelling flag directly to generate_final_amazon_table.)
    return "LOCKED: Waiting for Phase 3."
# Ratings we recognise in an Offer Condition Note, mapped to a quality rank
# (higher = better). We always report the *lowest* (worst) rating present so
# the buyer is never over-promised. The trailing +/- on a rating is dropped.
_RATING_RANK = {'Like New': 3, 'Very Good': 2, 'Good': 1}
def derive_item_condition(notes):
    """Return 'Collectable - <lowest rating found in the note>'.

    Scans the Offer Condition Note for Like New / Very Good / Good (most
    specific first so 'Good' never matches inside 'Very Good'), keeps the
    worst one present, and strips any +/- suffix. Falls back to
    'Collectable - Good' when no recognised rating appears.
    """
    text = notes or ''
    found = []
    for rating in ['Like New', 'Very Good', 'Good']:
        if rating == 'Good':
            # Avoid matching the "Good" inside "Very Good".
            pattern = r'(?<!very )Good\b'
        else:
            pattern = r'\b' + re.escape(rating) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            found.append(rating)
    if not found:
        return 'Collectable - Good'
    worst = min(found, key=lambda r: _RATING_RANK[r])
    return 'Collectable - ' + worst

def generate_final_amazon_table(condition_choice, apply_spelling):
    """PHASE 3: GENERATE FINAL OUTPUT."""
    global DISCOGS_DATA_STORAGE 
    final_output = {
        'Quantity': '1', 
        # 'Country/Region of Origin': 'US', <--- DELETE THIS LINE ENTIRELY
        'Number of Items': '1', 
        'PRODUCT_TAX_CODE': 'A_GEN_TAX',
        'Upload Photos': '(uploaded by user)', 
        'Merchant Shipping Group': '(select correct weight by user)'
    }
    final_output.update(DISCOGS_DATA_STORAGE)
    final_output['List Price'] = final_output.get('Your Price', '0.00')
    # Item Condition is ALWAYS "Collectable - <lowest rating in the Offer
    # Condition Note>" (new policy). Derive it here so it's consistent whether
    # or not Phase 2 populated the fields.
    final_output['Item Condition'] = derive_item_condition(
        final_output.get('Offer Condition Note', ''))
    if "Record Store Day" in str(final_output.get('Edition')) or "Record Store Day" in str(final_output.get('Raw Data')):
        final_output['Format:'] = "Limited Edition"
    if str(apply_spelling).lower() == 'yes':
        html = final_output['HTML Product Description']
        for misspelled, correct in SPELLING_CORRECTIONS.items():
            html = re.sub(r'\b' + re.escape(misspelled) + r'\b', correct, html, flags=re.IGNORECASE)
        final_output['HTML Product Description'] = html
    label_list = final_output.get('Label_List', [])
    primary_label = ' / '.join(label_list) if label_list else final_output.get('Artist(s)', 'Unknown')    
    # Check if this is a self-release or "Not On Label"
    is_self_released = "not on label" in primary_label.lower()
    if is_self_released:
        final_brand = final_output.get('Artist(s)', 'Unknown')
        final_manufacturer = final_output.get('Artist(s)', 'Unknown')
    else:
        final_brand = primary_label
        final_manufacturer = primary_label
    final_output['Brand Name'] = final_brand
    final_output['Manufacturer'] = final_manufacturer
    if final_output.get('UPC/GTIN (Scanned)') == '*(Not found)*':
        # Only flag "no brand name" when there is genuinely no label
        if is_self_released or not final_brand or final_brand == 'Unknown':
            final_output['Brand Name'] = '**Check box: "This product does not have a brand name"**'
        final_output['UPC/GTIN (Scanned)'] = '**Check box: "This product does not have a Product ID"**'
        final_output['ID_Type'] = 'N/A'
    raw_barcode = str(final_output.get('UPC/GTIN (Scanned)', ''))
    text_barcode = raw_barcode
    if raw_barcode == '*(Not found)*':
        text_barcode = '**Check box: "This product does not have a Product ID"**'
    elif len(raw_barcode) == 12: 
        text_barcode = f"{raw_barcode[0]} {raw_barcode[1:6]} {raw_barcode[6:11]} {raw_barcode[11]}"
    elif len(raw_barcode) == 13:
        text_barcode = f"{raw_barcode[0]} {raw_barcode[1:7]} {raw_barcode[7:13]}"
    final_output['UPC/GTIN (Text Display)'] = text_barcode
    current_pn = str(final_output.get('Part Number', '')).lower()
    if current_pn in ['n/a', '', 'none', '*(not found)*']:
        final_output['Part Number'] = text_barcode
    # ---- Subject Keyword -------------------------------------------------
    # Build a richer pool derived from the item, lower-cased and stripped of
    # anything Amazon dislikes, then cap the space-joined one-liner to 210 bytes.
    def _clean_kw(token):
        if token is None:
            return ''
        t = str(token).lower().strip()
        t = re.sub(r"[^a-z0-9\s\-]", ' ', t)   # drop punctuation / markup
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    BLOCKED = {
        'amazon', 'ebay', 'walmart', 'free', 'free shipping', 'sale', 'best', 'cheap',
        'wholesale', 'retail', 'authentic', 'genuine', 'original', 'replica',
        'counterfeit', 'new', 'used', 'refurbished', 'warranty', 'guarantee',
        'discount', 'promo', 'offer', 'limited time', 'only', 'exclusive',
        'official', 'licensed', 'real', 'fake', 'copy', 'reproduction', 'buy now',
        'click', 'import', 'shipping', 'tm', '100%', '®', '©',
    }

    def _bad(t):
        if not t:
            return True
        if 'check box' in t:
            return True
        if t in BLOCKED:
            return True
        if any(b in t for b in ('amazon', 'ebay', 'walmart', 'free shipping', '100%', 'check box')):
            return True
        return False

    candidates = []
    for src in ('Bullet Point', 'Artist(s)', 'Part Number', 'Series',
                'Brand Name', 'Manufacturer', 'Item Name'):
        c = _clean_kw(final_output.get(src))
        if c and not _bad(c):
            candidates.append(c)
    if raw_barcode and 'Check box' not in raw_barcode and raw_barcode != '*(Not found)*':
        candidates.append(raw_barcode)
    binding = final_output.get('Binding', '')
    if binding == 'Audio Cassette':
        candidates.append('cassette')
        candidates.append('cassette tape')
        released_line = next((l for l in str(final_output.get('Raw Data', '')).split('\n')
                              if l.startswith('Released:')), '')
        ym = re.search(r'(\d{4})', released_line)
        if ym and int(ym.group(1)) < 1990:
            candidates.append('vintage cassette')
    elif binding == 'Vinyl':
        candidates.append('vinyl')
        candidates.append('vinyl lp')
        if final_output.get('Bullet Point') == '12" - Vinyl':
            candidates.append('12 inch vinyl')
        if any('Colored Vinyl' in str(final_output.get(f'Vinyl Record Details {i}', ''))
               for i in range(1, 4)):
            candidates.append('colored vinyl')
    elif binding == 'CD':
        candidates.append('cd')
        candidates.append('compact disc')
    elif binding == 'DVD Audio':
        candidates.append('dvd')
        if 'CDV' in str(final_output.get('Raw Data', '')):
            candidates.append('cd video')
    for g in [x.strip() for x in str(final_output.get('Genre_Style', '')).split(',') if x.strip()]:
        cg = _clean_kw(g)
        if cg and not _bad(cg):
            candidates.append(cg)
    pd_year = re.search(r'(\d{4})', str(final_output.get('Publication Date', '')))
    if pd_year:
        candidates.append(f"{(int(pd_year.group(1)) // 10) * 10}s")
    candidates.append('music')
    candidates.append('out of print')
    if ('limited' in str(final_output.get('Edition', '')).lower()
            or 'limited' in str(final_output.get('Raw Data', '')).lower()):
        candidates.append('limited release')
    # dedupe (preserve order), drop empties / blocked / check-box placeholders
    seen = set()
    kw_unique = []
    for c in candidates:
        if c and not _bad(c) and c not in seen:
            seen.add(c)
            kw_unique.append(c)
    # cap to 210 bytes when space-joined (this is the Amazon one-liner)
    final_tokens = []
    used = 0
    for t in kw_unique:
        add = len(t.encode('utf-8')) + (1 if final_tokens else 0)
        if used + add <= 210:
            final_tokens.append(t)
            used += add
        else:
            break
    final_output['Subject Keyword'] = ', '.join(final_tokens)
    final_output['Product Type:'] = 'CDs & Vinyl'
    sections = {
        "Section 1: Product Identity": ["Item Name", "Product Type:", "Brand Name", "UPC/GTIN (Scanned)", "UPC/GTIN (Text Display)", "ID_Type"],
        "Section 2: Description": ["HTML Product Description", "Bullet Point"],
        "Section 3: Product Details": [
            "Manufacturer", 
            "Number of Items", 
            "Part Number", 
            "Subject Keyword", 
            "Series",            # <--- ADD THIS LINE so it shows in the table
            "Edition", 
            "Format:", 
            "Publication Date", 
            "Genre_Style", 
            "Binding",
            "Vinyl Record Details 1", 
            "Vinyl Record Details 2", 
            "Vinyl Record Details 3",
            "Number Of Discs",        
            "Artist(s)", 
            "Composer", 
            "Performer"
        ],
        "Section 4: Offer": ["SKU", "Quantity", "Your Price", "Item Condition", "Offer Condition Note", "List Price", "PRODUCT_TAX_CODE", "Upload Photos", "Merchant Shipping Group"],
        "Section 5: Compliance": ["Country/Region of Origin"]
    }
    output_md = ""
    for section_title, fields in sections.items():
        output_md += f"{section_title}\n"
        for f in fields:
            val = final_output.get(f)
            if val in [None, 'N/A', 'Standard', '']:
                continue
            if val == "Standard Edition" and f == "Edition":
                continue
            if f == "Subject Keyword":
                display_val = str(val)
            else:
                display_val = str(val).replace('\n', '<br>')
            output_md += f"{f} - {display_val}\n"
        output_md += "\n"

    output_md = output_md.replace('***', '').replace('**', '')
    return output_md


def scrape_to_text(raw_discogs_data, price=None, location=None, comments=None):
    """
    Convenience wrapper used by the WYSIWYG 'Adds > Amazon' tab.

    Runs Phase 1 (ingestion) on the raw Discogs text, then applies the
    optional seller info and renders the final 5-section markdown table.
    If seller info (price/location) is not supplied yet, it still produces a
    usable table from the Phase 1 data (SKU/Price left as placeholders).

    Returns the markdown string.
    """
    process_discogs_raw_data(raw_discogs_data)
    # Phase 2: seller info (optional). If missing, synthesize a minimal
    # handshake string so Phase 3 can still render the table.
    if price is not None or location is not None or comments is not None:
        seller_blob = ""
        if price is not None:
            seller_blob += f"${price}\n"
        if comments is not None:
            seller_blob += f"Comments {comments}\n"
        seller_blob += f"Location: {location or 'NEED-SKU'}\n"
        try:
            process_seller_info_and_generate_asin(seller_blob)
        except Exception:
            pass
    return generate_final_amazon_table(1, "no")
