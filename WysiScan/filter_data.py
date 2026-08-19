import re
def discogs_add_macro(uploaded_media_photos=None, extracted_data=None):
    if extracted_data is None: extracted_data = {}
    extracted_data["Submission Notes"] = "Added release to Discogs"
    if not extracted_data.get("Genre") or not extracted_data.get("Style"):
        log_transformation("Search Trigger", "Discogs/Web", "Executing research turn for Genre/Style")
    execution_audit = []
    def log_transformation(rule, source_file, result):
        execution_audit.append({"Rule": rule, "Source": source_file, "Applied": result})
    role_map = {
        "Lead": "Soloist",
        "Lead Vocals": "Soloist",
        "Writer": "Written-By",
        "Songwriter": "Written-By",
        "Produced By": "Producer",
        "Executive Producer": "Executive-Producer",
        "Recording": "Recorded By",
        "Engineer": "Engineer",
        "Mix": "Mixed By"
    }
    def process_credits_degrouped(raw_credits):
        """Processes credits into Individualized Rows with Comma-Separated Roles."""
        individual_map = {} # {Name: [Role1, Role2]}  
        for role, names in raw_credits.items():
            # Apply Dictionary Mapping
            mapped_role = role_map.get(role, role)
            if mapped_role != role:
                log_transformation("Role Mapping", "Credit Dictionary", f"{role} -> {mapped_role}")
            
            for name in names:
                if name not in individual_map:
                    individual_map[name] = []
                if mapped_role not in individual_map[name]:
                    individual_map[name].append(mapped_role)
        degrouped_rows = []
        for name, roles in individual_map.items():
            role_string = ", ".join(roles)
            degrouped_rows.append([role_string, name])
        return degrouped_rows
    rights_societies_global = [
        "BIEM", "STEMRA", "ASCAP", "BMI", "SDRM", "SACEM", "GEMA", 
        "SGAE", "SIAE", "JASRAC", "MCPS", "PRS", "PPL", "SABAM"
    ]
    def is_rights_society(text):
        if not text: return False
        upper_text = str(text).upper()
        return any(soc in upper_text for soc in rights_societies_global)
    def generate_variance_note(spine_artist, cover_artist, face_artist, credit_artist):
        variations = {
            "the spine": spine_artist,
            "the front cover": cover_artist,
            "the CD face": face_artist,
            "the credits": credit_artist
        }
        variations = {k: v for k, v in variations.items() if v and str(v).strip() not in ["", "None"]}
        unique_names = set(variations.values())
        if len(unique_names) > 1:
            note_parts = []
            for name in unique_names:
                locations = [loc for loc, n in variations.items() if n == name]
                if len(locations) > 1:
                    location_str = ", ".join(locations[:-1]) + " and " + locations[-1]
                else:
                    location_str = locations[0]
                note_parts.append(f"{name} on {location_str}")        
            return "Artist name appears as " + "; ".join(note_parts) + "."
        return None
    def reconcile_spine_elements(spine_raw):
        if not spine_raw or str(spine_raw).strip() in ["", "None"]:
            return {"artist": None, "title": None, "cat": None}
        data = {"artist": None, "title": None, "cat": None}
        cat_match = re.search(r'\b([A-Z]{1,4}\s?\d{3,10}|(?:\d{1,2}\s?){5,10})\b', str(spine_raw))
        if cat_match:
            data["cat"] = cat_match.group().strip()
            spine_raw = str(spine_raw).replace(data["cat"], "").strip()
        for delim in [" - ", " : ", " / "]:
            if delim in spine_raw:
                parts = spine_raw.split(delim, 1)
                data["artist"] = parts[0].strip()
                data["title"] = parts[1].strip()
                break
        if not data["artist"] and spine_raw:
            data["title"] = spine_raw.strip()
        return data
    engineer_from_hub = extracted_data.get("engineer_hub_literal") 
    gm_from_hub = extracted_data.get("gm_hub_literal")
    matrix_literal = str(extracted_data.get("matrix", "")).strip()
    raw_matrix = matrix_literal.upper()
    mastering_sid = extracted_data.get("mastering_sid")
    mould_sid = extracted_data.get("mould_sid")
    logos = ["NIMBUS", "SONOPRESS", "DISCTRONICS", "DENON", "WME", "SPECIALTY"]
    for logo in logos:
        if logo in raw_matrix and f"[{logo}]" not in raw_matrix:
            raw_matrix = raw_matrix.replace(logo, f"[{logo}]")
    if mastering_sid and str(mastering_sid).upper() in raw_matrix:
        raw_matrix = raw_matrix.replace(str(mastering_sid).upper(), "").strip()
    matrix_unified = raw_matrix.strip()
    matrix_unified = matrix_unified.replace("[", "<").replace("]", ">")
    matrix_upper = matrix_literal.upper()
    if "MASTERED BY NIMBUS" in matrix_upper or "IFPI L155" in str(mastering_sid).upper():
        gm_from_hub = "Nimbus"
    if not extracted_data.get("distributed_by_literal"):
        distributor = None
    spars_val = extracted_data.get("spars_code") or extracted_data.get("free_text")
    face_spars = extracted_data.get("face_spars_literal")
    if face_spars and any(x in str(face_spars).upper() for x in ["AAD", "ADD", "DDD"]):
        spars_val = face_spars.upper()
    if mastering_sid and "IFPI L" in str(mastering_sid).upper():
        raw_year = extracted_data.get("year_latest")
        if raw_year and str(raw_year).isdigit() and int(raw_year) < 1994:
            extracted_data["year_latest"] = "Unknown (Post-1994 SID Conflict)"
    raw_blob = str(extracted_data).upper()
    is_club = any(x in raw_blob for x in ["COLUMBIA HOUSE", "DIDY", "CRC", "CH"]) 
    def validate_label(label, artist):
        if not label or str(label).strip().lower() in ["", "none", "unknown"]:
            return f"Not On Label ({artist} Self-released)" if artist else "Not On Label"
        return label
    def strip_year(text):
        if is_rights_society(text): 
            return None
        clean_text = re.sub(r'\b(19|20)\d{2}\b', '', str(text)).strip()
        if clean_text != str(text):
            log_transformation("Year Stripping", "LCCN/Copyright Field", f"Removed year: {text} -> {clean_text}")
        return clean_text
    def strict_title_case(t):
        if not t: return t
        return ' '.join(word[0].upper() + word[1:] if len(word) > 1 else word.upper() for word in str(t).split())
    def reconcile_brand_vs_company(name_string):
        corporate_flags = ["Group", "Inc.", "Ltd.", "S.A.", "Corp.", "GmbH", "LLC"]
        if any(flag in name_string for flag in corporate_flags):
            return "Record Company"
        return "Label"
    def clean(rows):
        return [r for r in rows if r[0] == "-" or (r[1] and str(r[1]).strip() not in ["", "None", "Unknown", "(No data visible)"])]
    def sanitize_release_notes(notes_potential, t2_lccn, t3_baoi):
        """Purges structured LCCN names and BAOI text from Table 8 Notes to prevent redundancy."""
        blocked_strings = set()
        for row in t2_lccn:
            if len(row) == 2 and row[0] not in ["-", "Item", "Value", "Catalog Number"]:
                name = str(row[1]).strip()
                if len(name) > 3:
                    blocked_strings.add(name.lower())
        for row in t3_baoi:
            if len(row) == 2 and row[0] == "Barcode (Text)":
                val = str(row[1]).strip()
                if val:
                    blocked_strings.add(val.lower())
                    blocked_strings.add(val.replace(" ", "").lower())
        sanitized_notes = []
        roles_and_verbs = ["manufactured", "distributed", "by", "for", "produced", "co", "ltd", "inc", ":", "-", ".", ","] 
        for key, note_val in notes_potential:
            if not note_val or note_val == "-":
                sanitized_notes.append((key, note_val))
                continue  
            lower_note = str(note_val).lower()
            is_redundant = False
            for entity in blocked_strings:
                if entity in lower_note:
                    # Strip entity and common role descriptors to see if unique text remains
                    test_string = lower_note.replace(entity, "")
                    for word in roles_and_verbs:
                        test_string = test_string.replace(word, "")
                    if len(test_string.strip()) < 4:
                        is_redundant = True
                        break
            if not is_redundant:
                sanitized_notes.append((key, note_val))  
        return sanitized_notes
    def reconstruct_marks(win_marks_raw):
        if not win_marks_raw or win_marks_raw == "(No data visible)":
            return "(No marks visible)"
        visual = re.sub(r'\d+', '', win_marks_raw).strip()
        visual = " ".join(visual.split())
        return visual
    spine_literal = extracted_data.get("label_spine", "")
    spine_data = reconcile_spine_elements(spine_literal)
    raw_title = spine_data["title"] or extracted_data.get("title", "")
    secondary_title = extracted_data.get("subtitle", "")
    if secondary_title and not spine_literal:
        final_title = f"{raw_title} - {secondary_title}"
    else:
        final_title = raw_title
    final_title = strict_title_case(final_title)
    log_transformation("Strict Title Case", "Title Field", final_title)
    final_artist = spine_data["artist"] or extracted_data.get("artist")
    raw_artists = str(final_artist).replace(" & ", " / ").replace(" and ", " / ").split(" / ")
    artist_rows = []
    for i, individual in enumerate(raw_artists):
        actual_name = strict_title_case(individual.strip())
        artist_rows.append((f"Artist {i+1} (Actual Name)", actual_name))
        other_versions = [extracted_data.get("face_literal"), extracted_data.get("credit_artist_literal")]
        for version in other_versions:
            if version and strict_title_case(version) != actual_name:
                artist_rows.append((f"Artist {i+1} (ANV)", strict_title_case(version)))
                break
        if i < len(raw_artists) - 1:
            artist_rows.append(("Join", "&"))
    table_1 = [("Item", "Value")] + artist_rows + [("Title", final_title)]
    p_copyright = strip_year(extracted_data.get("p_copyright_latest"))
    c_copyright = strip_year(extracted_data.get("c_copyright_latest"))
    distributor = extracted_data.get("distributed_by")
    licensed_to = extracted_data.get("licensed_to")
    mfd_for = extracted_data.get("manufactured_for")
    def format_cat_no(raw_val):
        if not raw_val: return None
        if "Cassette" in str(extracted_data.get("core_format")): return raw_val.strip()
        cleaned = str(raw_val).strip()
        if cleaned == matrix_literal or cleaned in matrix_literal:
            return None
    spine_cat = spine_data["cat"] or format_cat_no(extracted_data.get("cat_no_spine"))
    shell_cat = format_cat_no(extracted_data.get("cat_no_shell"))
    inlay_cat = format_cat_no(extracted_data.get("cat_no_other"))
    cat_rows = []
    primary_cat = spine_cat
    if primary_cat:
        cat_rows.append(("Catalog Number", primary_cat))   
    if shell_cat and shell_cat != primary_cat:
        cat_rows.append(("Catalog Number", f"{shell_cat} (Shell)"))
    if inlay_cat:
        if inlay_cat != primary_cat and inlay_cat != shell_cat:
            cat_rows.append(("Catalog Number", f"{inlay_cat} (Inlay)"))
    if not cat_rows:
        cat_rows.append(("Catalog Number", "none"))
    raw_spine = extracted_data.get("label_spine")
    raw_back = extracted_data.get("company_back_artwork") 
    final_label = None
    record_company = extracted_data.get("record_company") 
    if raw_spine:
        if reconcile_brand_vs_company(raw_spine) == "Record Company":
            record_company = raw_spine
        else:
            final_label = raw_spine
    if raw_back:
        if reconcile_brand_vs_company(raw_back) == "Record Company":
            record_company = raw_back 
        else:
            final_label = final_label or raw_back
    final_label = validate_label(final_label, extracted_data.get("artist"))
    final_label = extracted_data.get("label_literal", final_label)
    redundant_check = [p_copyright, c_copyright]
    year_regex = r'\b(19|20)\d{2}\b|\bM{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b'
    def sanitize_lccn(val, label_ref):
        name_only = re.sub(year_regex, '', str(val)).strip("- ").strip()
        if not name_only or name_only.lower() == str(label_ref).lower():
            log_transformation("LCCN Suppression", "Redundancy Check", f"Suppressed {name_only} (Matches Label)")
            return None
        return name_only
    p_copyright = sanitize_lccn(extracted_data.get("p_copyright_latest"), final_label)
    c_copyright = sanitize_lccn(extracted_data.get("c_copyright_latest"), final_label)
    marketed_by = extracted_data.get("marketed_by")
    lccn_roles_to_check = [p_copyright, c_copyright, distributor, marketed_by]
    if record_company and any(str(record_company).strip().upper() == str(role).strip().upper() for role in lccn_roles_to_check if role):
        record_company_final = None
        log_transformation("Record Company Scrub", "LCCN Redundancy", f"Removed {record_company} (Already present in specific LCCN roles)")
    else:
        record_company_final = record_company
    primary_potential = [
        ("Label", final_label),
    ]
    if is_club:
        primary_potential.append(("-", "-"))
        primary_potential.append(("Manufactured By", "Columbia House"))
        didy_match = re.search(r'DIDY\s?\d+', raw_blob)
        if didy_match:
            primary_potential.append(("Catalog Number", didy_match.group()))
    primary_potential.extend(cat_rows)
    mastering_sid = extracted_data.get("mastering_sid")
    mfg_name = gm_from_hub if gm_from_hub else extracted_data.get("glass_mastered_at")
    
    # Initialize variables for the table
    glass_master_val = None
    pressed_by_val = extracted_data.get("pressed_by")

    # Preference Logic: If a manufacturing name exists but no "IFPI" SID is visible, credit as 'Pressed By'
    if mfg_name:
        if mastering_sid and "IFPI" in str(mastering_sid).upper():
            glass_master_val = mfg_name
        else:
            pressed_by_val = mfg_name
    # --- NEW MANUFACTURING LOGIC END ---

    primary_potential.extend([
        ("Series", extracted_data.get("series")),
        ("-", "-"), 
        ("Record Company", record_company_final),
        ("Licensed To", extracted_data.get("licensed_to")),
        ("Licensed From", extracted_data.get("licensed_from")),
        ("Licensed Through", extracted_data.get("licensed_through")),
        ("Marketed By", extracted_data.get("marketed_by")),
        ("Distributed By", extracted_data.get("distributed_by")),
        ("Manufactured By", extracted_data.get("manufactured_by")),
        ("Exported By", extracted_data.get("exported_by")),
        ("Produced For", extracted_data.get("produced_for")),
        ("Manufactured For", extracted_data.get("manufactured_for")),
        ("Recorded By", extracted_data.get("recorded_by")),
        ("Funded By", extracted_data.get("funded_by")),
        ("Corporate Owner", extracted_data.get("corporate_owner")),
        ("Trademark Owner", extracted_data.get("trademark_owner")),
        ("-", "-"),
        ("Phonographic Copyright (p)", strip_year(p_copyright)),
        ("Phonographic Copyright (p) [Licensed]", extracted_data.get("secondary_p_copyright")), # For MCA/Secondary Label
        ("Copyright (c)", strip_year(c_copyright)),
        ("-", "-"),
        ("Made By", extracted_data.get("made_by")),
        ("Pressed By", pressed_by_val), # FIXED: Linked to logic above
        ("Duplicated By", extracted_data.get("duplicated_by")),
        ("Printed By", extracted_data.get("printed_by")),
        ("-", "-"),
        ("Published By", extracted_data.get("published_by")),
        ("-", "-"),
        ("Recorded At", extracted_data.get("recorded_at")),
        ("Engineered At", extracted_data.get("engineered_at")),
        ("Overdubbed At", extracted_data.get("overdubbed_at")),
        ("Produced At", extracted_data.get("produced_at")),
        ("Mixed At", extracted_data.get("mixed_at")),
        ("Remixed At", extracted_data.get("remixed_at")),
        ("Mastered At", extracted_data.get("mastered_at")),
        ("Lacquer Cut At", extracted_data.get("lacquer_cut_at")),
        ("Glass Mastered At", glass_master_val), # FIXED: Linked to logic above
        ("Plated At", extracted_data.get("plated_at")),
        ("Authoring At", extracted_data.get("authoring_at")),
        ("-", "-"),
        ("Designed At", extracted_data.get("designed_at")),
        ("Filmed At", extracted_data.get("filmed_at")),
        ("Remastered At", extracted_data.get("remastered_at")),
        ("Edited At", extracted_data.get("edited_at")),
        ("Exclusive Retailer", extracted_data.get("exclusive_retailer"))
    ])
    raw_barcode = extracted_data.get("barcode_visual") or extracted_data.get("barcode_literal") or extracted_data.get("barcode") or ""
    literal_barcode = str(raw_barcode).strip()
    ambiguous_chars = ["0", "O", "G", "A", "Q", "1", "I"]
    if any(char in matrix_unified for char in ambiguous_chars):
        matrix_unified = matrix_unified
    price_codes = []
    other_val = extracted_data.get("other_id")
    if other_val:
        other_val_upper = str(other_val).upper()
        patterns = [r"PM\s?\d+", r"CDP\s?\d+", r"F:\s?PM\s?\d+"]
        for p in patterns:
            found = re.findall(p, other_val_upper)
            for f in found:
                price_codes.append(("Price Code", f))
                other_val_upper = other_val_upper.replace(f, "").strip()
        other_val = other_val_upper if other_val_upper and other_val_upper not in ["", "NONE"] else None
    if other_val in [spine_cat, shell_cat, additional_cat]:
        other_val = None
    if literal_barcode in [spine_cat, shell_cat, additional_cat]:
        literal_barcode = None
    if str(other_val).upper() in ["SR", "AR"]:
        other_val = None
    baoi_potential = [
        ("Barcode (Text)", literal_barcode),
        ("Label Code", extracted_data.get("label_code")),
        ("Rights Society", extracted_data.get("rights_society")),
        ("Matrix / Runout", matrix_unified),
        ("Mastering SID Code", mastering_sid if "IFPI" in str(mastering_sid).upper() else None),
        ("Mould SID Code", extracted_data.get("mould_sid") if "IFPI" in str(extracted_data.get("mould_sid")).upper() else None),
        ("Pressing Plant ID", extracted_data.get("pressing_plant_id")),
        ("Distribution Code", extracted_data.get("dist_code")),
        ("Price Code", extracted_data.get("price_code")),
        ("SPARS Code", spars_val),
        ("Depósito Legal", extracted_data.get("deposito_legal")),
        ("ASIN", extracted_data.get("asin")),
        ("ISRC", extracted_data.get("isrc")),
        ("Other [Sequential Numbering]", extracted_data.get("limited_no")),
        ("Other [Manufacturing Code]", extracted_data.get("mfg_code")),
        ("Other [Spine Identifier]", extracted_data.get("spine_code_internal")),
        ("Other [Tape Shell Code]", extracted_data.get("shell_code_internal")),
        ("Other", other_val)
    ]
    baoi_potential.extend(price_codes)
    baoi_combined = clean(baoi_potential)
    raw_pixels_upper = str(extracted_data).upper()
    dolby_base = ""
    if "SURROUND" in raw_pixels_upper:
        dolby_base = "Dolby Surround"
    elif extracted_data.get("dolby_literal_b"): 
        dolby_base = "Dolby B"
    elif extracted_data.get("dolby_logo_visible"): 
        dolby_base = "Dolby"
    if extracted_data.get("hx_pro") and dolby_base:
        dolby_string = f"{dolby_base} HX PRO B NR".strip()
    else:
        dolby_string = dolby_base or ("HX PRO" if extracted_data.get("hx_pro") else "")
    tape_type_raw = str(extracted_data.get("tape_type_literal", "")).upper()
    tape_type = None
    if any(x in tape_type_raw for x in ["CHROME", "120 μS", "120US", "CRO2"]):
        tape_type = "Chrome 120 μs EQ"
    elif any(x in tape_type_raw for x in ["TYPE IV", "METAL"]):
        tape_type = "Metal"
    elif any(x in tape_type_raw for x in ["TYPE I", "NORMAL"]):
        tape_type = "Normal"
    all_cd_tags = ["Album", "Compilation", "EP", "Single", "Maxi-Single", "Mini-Album", "Promo", "Reissue", "Remastered", "Mixed", "Enhanced", "Mispress", "Limited Edition"]
    format_table = []
    formats_found = extracted_data.get("formats_list")
    if not formats_found:
        formats_found = [{
            "type": extracted_data.get("core_format"),
            "qty": extracted_data.get("qty") if extracted_data.get("qty") else "1",
            "size": extracted_data.get("size"),
            "free_text": extracted_data.get("free_text", "")
        }]
    for i, fmt in enumerate(formats_found):
        if i > 0:
            format_table.append(("-", "-"))  
        format_table.append(("Format", fmt.get("type")))
        format_table.append(("Quantity", fmt.get("qty") or "1"))
        if fmt.get("size"): 
             format_table.append(("Size", fmt.get("size")))   
        cd_sub_types = [
            "Mini", "Minimax", "CD-ROM", "CDi", "CD+G", "HDCD", "VCD", "AVCD", "SVCD", "XRCD",
            "Advance", "Album", "Mini-Album", "EP", "Maxi-Single", "Record Store Day", "Single",
            "Compilation", "Club Edition", "Copy Protected", "Deluxe Edition", "Enhanced",
            "Limited Edition", "Mispress", "Misprint", "Mixed", "Mixtape", "Numbered",
            "Partially Mixed", "Partially Unofficial", "Promo", "Remastered", "Repress",
            "Sampler", "Special Edition", "Test Pressing", "Tour Recording", "Transcription",
            "Unofficial Release"
        ]
        channel_tags = ["Stereo", "Mono", "Quadraphonic", "Ambisonic"]
        for tag in channel_tags:
            if tag.upper() in raw_pixels_upper:
                format_table.append(("Checklist", f"[x] {tag}"))
        remaster_triggers = ["SBM", "SUPER BIT MAPPING", "20-BIT", "24-BIT", "DIGITALLY REMASTERED"]
        if any(trigger in raw_pixels_upper for trigger in remaster_triggers):
            extracted_data["remastered"] = True  
        is_compilation = False
        comp_triggers = ["COMPILATION", "ANNIVERSARY", "GREATEST HITS", "BEST OF", "COLLECTION"]
        if any(trigger in raw_pixels_upper for trigger in comp_triggers) or extracted_data.get("compilation"):
            is_compilation = True
        is_album = not is_compilation 
        for tag in all_cd_tags:
            if tag == "Album" and is_album:
                format_table.append(("Checklist", f"[x] {tag}"))
                continue
            if tag == "Compilation" and is_compilation:
                format_table.append(("Checklist", f"[x] {tag}"))
                continue
        raw_pixels = str(extracted_data).lower()
        for fmt_tag in cd_sub_types:
            if fmt_tag.lower() in raw_pixels:
                if ("Checklist", f"[x] {fmt_tag}") not in format_table:
                    format_table.append(("Checklist", f"[x] {fmt_tag}"))
            raw_ft = fmt.get("free_text", "")
            combined_ft = raw_ft.replace(",", "").replace(" tape", "").replace(" Tape", "").strip()
            for tag in ["Remastered", "Compilation", "Album", "Mono", "Stereo"]:
                if any(row[1] == f"[x] {tag}" for row in format_table):
                    combined_ft = re.sub(f"(?i){tag}", "", combined_ft).strip(", ")
            if spine_cat and str(spine_cat) not in ["", "None"]:
                combined_ft = combined_ft.replace(str(spine_cat), "").strip()
            if dolby_string: 
                combined_ft = f"{combined_ft}, {dolby_string}".strip(", ")
            if fmt.get("type") == "Cassette" and tape_type:
                combined_ft = f"{combined_ft}, {tape_type}".strip(", ")
            plant_code = str(extracted_data.get("other_id", "")).upper()
            if plant_code in ["SR", "AR"]: 
                combined_ft = f"{plant_code}, {combined_ft}".strip(", ")           
            raw_packaging = extracted_data.get("packaging", "").strip()
            forbidden_packaging = ["jewel case", "slipcase", "slim", "gatefold"]
            if "digipak" in raw_packaging.lower():
                combined_ft = f"{combined_ft}, Digipak".strip(", ")
            elif raw_packaging and not any(p in raw_packaging.lower() for p in forbidden_packaging):
                combined_ft = f"{combined_ft}, {raw_packaging}".strip(", ") 
            combined_ft = re.sub(r"^,\s*|\s*,\s*$", "", combined_ft) 
            if combined_ft and combined_ft.strip() not in ["", "None", "Unknown"]:
                format_table.append(("Free Text", combined_ft))
    raw_origin = str(extracted_data.get("country_raw", "")).upper()
    final_country = extracted_data.get("country_raw")
    is_uk = any(x in raw_origin for x in ["UK", "U.K.", "UNITED KINGDOM", "LONDON"])
    is_eu = any(x in raw_origin for x in ["EU", "E.U.", "EUROPE", "E.E.C.", "MADE IN THE EU"])
    if any(x in raw_origin for x in ["USA", "U.S.A.", "UNITED STATES"]):
        final_country = "US"
    elif any(x in raw_origin for x in ["CANADA", "CAN"]):
        final_country = "Canada"
    elif any(x in raw_origin for x in ["AUSTRALIA", "AUS"]):
        final_country = "Australia"
    elif is_uk and is_eu:
        final_country = "UK & Europe"
    elif is_eu:
        final_country = "Europe"
    elif is_uk:
        final_country = "UK"
    raw_year = extracted_data.get("year_latest")
    mastering_sid = extracted_data.get("mastering_sid")
    final_year = raw_year if raw_year else "Unknown"
    if mastering_sid and raw_year and str(raw_year).isdigit():
        if int(raw_year) < 1994:
            final_year = "Unknown (Post-1994 SID Conflict)"
    release_info = [
        ("Item", "Value"),
        ("Country", final_country), 
        ("Released", final_year)
    ]
    def process_tracks(tracks_raw):
        import string
        import re
        if not tracks_raw:
            return [{"Tracklist": "", "Title/Credits": "(Note: Tracklist data not visible. Omission Mandate applied.)"}]
        formatted = []
        current_side = "" 
        total_qty = str(extracted_data.get("qty", "1"))
        is_multi = total_qty != "1" or len(extracted_data.get("formats_list", [])) > 1
        is_analog_multi = any(fmt.get("type") in ["Cassette", "Vinyl", "LP"] for fmt in formats_found)
        if is_analog_multi and is_multi:
            side_map = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
            item_idx = int(t.get("disc_no", 1)) - 1
            side_offset = item_idx * 2
            if "SIDE TWO" in raw_val.upper() or "SIDE 2" in raw_val.upper() or "SIDE B" in raw_val.upper():
                current_side = side_map[side_offset + 1] if (side_offset + 1) < len(side_map) else ""
            else:
                current_side = side_map[side_offset] if side_offset < len(side_map) else ""
        side_suppression = [
            "SIDE ONE", "SIDE 1", "SIDE A", "PROGRAM ONE", "PROGRAM 1",
            "SIDE TWO", "SIDE 2", "SIDE B", "PROGRAM TWO", "PROGRAM 2"
        ]
        for t in tracks_raw:
            raw_val = str(t.get("title", "")).strip()
            if ":" in raw_val or " - " in raw_val:
                delim = ":" if ":" in raw_val else " - "
                parts = raw_val.split(delim, 1)
                work_title = strict_title_case(parts[0].strip())
                movement_title = strict_title_case(parts[1].strip())
                if not formatted or formatted[-1].get("Title/Credits") != f"**{work_title}**":
                    formatted.append({
                        "Track": "",
                        "Title": f"**{work_title}**",
                        "Time": ""
                    })
                track_title = movement_title
            else:
                track_title = strict_title_case(raw_val)
            anv_match = re.search(r'\(([^)]+)\)$', raw_val)
            track_title = raw_val
            literal_anv = None
            canonical_artist = t.get("artist_canonical") or "Unknown Artist" 
            if anv_match:
                content = anv_match.group(1)
                if content.strip().lower() in ["traditional", "instrumental", "remix", "edit"]:
                    track_title = strict_title_case(raw_val) 
                else:
                    literal_anv = content.strip()
                    track_title = strict_title_case(raw_val.replace(anv_match.group(0), "").strip())
            else:
                track_title = strict_title_case(raw_val)
            track_num_raw = str(t.get('num') or t.get("pos", "")).strip()
            track_num = track_num_raw.lstrip('0') if track_num_raw not in ["0", ""] else track_num_raw          
            if "medley" in raw_val.lower():
                formatted.append({
                    "Tracklist": "Index", 
                    "Title/Credits": f"**{strict_title_case(raw_val)}**"
                })
                inner_title = re.sub(r'(?i)medley\s*:\s*', '', raw_val)
                sub_titles = [s.strip() for s in inner_title.split('/')]
                for i, sub_t in enumerate(sub_titles):
                    suffix = string.ascii_lowercase[i] if i < 26 else i
                    formatted.append({
                        "Tracklist": f"{track_num}{suffix}",
                        "Title/Credits": strict_title_case(sub_t)
                    })
                continue
            if any(trigger in raw_val.upper() for trigger in side_suppression):
                continue
            if current_side and track_num.isdigit():
                pos_base = f"{current_side}{track_num}"
            else:
                disc_no = t.get("disc_no") 
                pos_base = f"{disc_no}-{track_num}" if (is_multi and disc_no) else f"{track_num}"
            has_anv = any(re.search(r'\(([^)]+)\)$', str(tr.get("title", ""))) for tr in tracks_raw)
            is_comp = len(set(str(tr.get("artist", "")).strip() for tr in tracks_raw if tr.get("artist"))) > 1
            trigger_artist_col = has_anv or is_comp
            
            row = {
                "Track": pos_base,
                "Title": strict_title_case(track_title),
                "Time": t.get("duration")
            }
            if trigger_artist_col:
                row["Artist"] = strict_title_case(t.get("artist") or "Unknown Artist")
            formatted.append(row)
            def add_credit_subrow(role_text, artist_text):
                if artist_text:
                    subrow = {
                        "Track": "",
                        "Artist": role_text, # Role isolated in Col 2
                        "Title": strict_title_case(artist_text), # Artist isolated in Col 3
                        "Time": ""
                    }
                    formatted.append(subrow)
            raw_credits_blob = str(t.get("credits_literal") or "").strip()
            if "Featuring" in raw_credits_blob:
                feat_part = re.search(r"Featuring\s*(.*)", raw_credits_blob, re.IGNORECASE)
                if feat_part: add_credit_subrow("Featuring", feat_part.group(1))           
            if "Lead Vocals" in raw_credits_blob:
                lv_part = re.search(r"Lead Vocals\s*:\s*(.*)", raw_credits_blob, re.IGNORECASE)
                if lv_part: add_credit_subrow("Lead Vocals", lv_part.group(1))
            if "aka" in raw_credits_blob:
                aka_part = re.search(r"aka\s*(.*)", raw_credits_blob, re.IGNORECASE)
                if aka_part: add_credit_subrow("aka", aka_part.group(1))
            if literal_anv and trigger_artist_col:
                formatted.append({
                    "Track": "",
                    "Artist": literal_anv,
                    "Title": "",
                    "Time": ""
                })
            continue
        return formatted
    final_tracks_list = process_tracks(extracted_data.get("tracklist_raw", []))
    credits_genres = [("Type", "Value")]
    raw_genre = extracted_data.get("genre")
    raw_style = extracted_data.get("style")
    if not raw_genre or str(raw_genre).strip().lower() in ["", "none", "unknown"]:
        genre_val = "TRIGGER_AI_GENRE_SEARCH"
    else:
        genre_val = raw_genre
    if not raw_style or str(raw_style).strip().lower() in ["", "none", "unknown"]:
        style_val = "TRIGGER_AI_STYLE_SEARCH"
    else:
        style_val = raw_style
    credits_genres.append(("Genre", genre_val))
    credits_genres.append(("Style", style_val))
    if engineer_from_hub:
        credits_genres.append(("Mastered By", strict_title_case(engineer_from_hub)))
    track_producers = {}
    for t in extracted_data.get("tracklist_raw", []):
        p_name = t.get("produced_by") or t.get("producer")
        if p_name:
            t_num = str(t.get("num") or t.get("pos", "")).lstrip('0')
            track_producers.setdefault(strict_title_case(p_name), []).append(t_num)
    for prod_name, tracks in track_producers.items():
        track_range = f"(Tracks: {', '.join(tracks)})"
        credits_genres.append(("Producer", f"{prod_name} {track_range}"))
    visible_credits = extracted_data.get("credits", [])
    for c in visible_credits:
        role = str(c.get('role', '')).strip()
        if not role: continue
        if "PRODUCER" in role.upper() and not any(x in role.upper() for x in ["EXECUTIVE", "CO-PRODUCER"]):
            continue
        names = [n.strip() for n in str(c['name']).split(',')]
        for name in names:
            clean_role = re.sub(r'\bProducers\b', 'Producer', role)
            credits_genres.append((clean_role, name))
    user_provided_notes = extracted_data.get("user_notes", "") 
    shell_desc = ""
    if any(fmt.get("type") == "Cassette" for fmt in formats_found):
        shell_desc = extracted_data.get("shell_desc", "")
        if extracted_data.get("win_marks"):
            window_val = extracted_data.get('win_marks')
            window_type = extracted_data.get('win_type', 'No numbers')
            shell_desc = f"{shell_desc}. Timing Window: {window_type} ({window_val})".strip(". ")
    ai_suggestions = []
    if "Post-1994 SID Conflict" in final_year: ai_suggestions.append("SID codes present; release date adjusted to post-1994 per Discogs RSG §5.2.")
    if ("LIMITED" in raw_blob or extracted_data.get("limited_no")) and not extracted_data.get("limited_edition"):
        ai_suggestions.append("Limited edition release; check for individual numbering.")
    if any(x in raw_blob for x in ["ENHANCED", "MULTIMEDIA"]) and not extracted_data.get("enhanced"):
        ai_suggestions.append("Release includes enhanced multimedia content (system requirements may apply).")
    if "HIDDEN" in raw_blob or "UNLISTED" in raw_blob:
        ai_suggestions.append("Contains unlisted or hidden tracks not printed on the sleeve.")
    distributor_raw = str(extracted_data.get("distributed_by", "")).upper()
    print_year = extracted_data.get("year_latest")
    if "MOTOWN" in raw_blob and "MCA" in distributor_raw:
        if print_year and str(print_year).isdigit() and int(print_year) < 1983:
            ai_suggestions.append("RED FLAG: Motown/MCA Distribution conflict. Motown was independent until 1983. Year should likely be 'Unknown'.")
    if "WEA" in distributor_raw and print_year and str(print_year).isdigit() and int(print_year) < 1971:
        ai_suggestions.append("RED FLAG: WEA Distribution found with pre-1971 date. WEA was formed in 1971.")
    if "POLYGRAM" in distributor_raw and print_year and str(print_year).isdigit() and int(print_year) < 1972:
        ai_suggestions.append("RED FLAG: PolyGram Distribution found with pre-1972 date. PolyGram was formed in 1972.")
    if any(x in raw_blob for x in ["STICKER", "PROMO", "PUNCH HOLE", "SAW CUT"]):
        ai_suggestions.append("Some copies may feature a marketing sticker, promotional stamp, or remainder mark.")
        if "Not On Label" in str(final_label):
            ai_suggestions.append("Self-released: Label name appears in copyright notice only; no branding present on artwork.")
    if "none" in [c[1] for c in cat_rows]:
        ai_suggestions.append("No catalog number found on artwork; matrix string used for secondary identification.")

    # --- TABLE 7 INITIALIZATION AND CREDIT COMPILATION ---
    table_7 = [("Role", "Artist")] 
    raw_genre = extracted_data.get("genre")
    raw_style = extracted_data.get("style")
    
    genre_val = "TRIGGER_AI_GENRE_SEARCH" if not raw_genre else raw_genre
    style_val = "TRIGGER_AI_STYLE_SEARCH" if not raw_style else raw_style
    
    table_7.append(["Genre", genre_val])
    table_7.append(["Style", style_val])
    
    if engineer_from_hub:
        table_7.append(("Mastered By", strict_title_case(engineer_from_hub)))
        
    track_producers = {}
    for t in extracted_data.get("tracklist_raw", []):
        p_name = t.get("produced_by") or t.get("producer")
        if p_name:
            t_num = str(t.get("num") or t.get("pos", "")).lstrip('0')
            track_producers.setdefault(strict_title_case(p_name), []).append(t_num)
            
    for prod_name, tracks in track_producers.items():
        track_range = f"(Tracks: {', '.join(tracks)})"
        table_7.append(("Producer", f"{prod_name} {track_range}"))
        
    visible_credits = extracted_data.get("credits", [])
    degrouped_credits = process_credits_degrouped(visible_credits)
    table_7.extend(degrouped_credits)
    # ----------------------------------------------------

    used_values = set()
    t1 = table_1
    t2 = primary_potential
    t3 = baoi_combined
    t4 = format_table
    t5 = release_info
    t7 = table_7
    for table_data in [t1, t2, t3, t4, t5, t7]:
        if table_data:
            for row in table_data:
                if len(row) == 2:
                    val = row[1]
                    if val and val != "-" and str(val).lower() not in ["none", "unknown"]:
                        used_values.add(str(val).strip().upper())
    def is_redundant(note_text):
        if not note_text: return True
        return str(note_text).strip().upper() in used_values
    mfg_note = extracted_data.get("printed_in")
    gen_notes = extracted_data.get("general_notes_full")
    variance_note = generate_variance_note(
        extracted_data.get("label_spine"), 
        extracted_data.get("artist"), 
        extracted_data.get("face_literal"), 
        extracted_data.get("credit_artist_literal")
    )
    notes_potential = [
        ("General Notes", user_provided_notes),
        ("Physical Credits", f"Printed in {extracted_data.get('printed_in_country')}" if extracted_data.get("printed_in_country") else None),
        ("Name Variation", variance_note),
        ("Shell Description", shell_desc.strip()),
        ("Packaging Details", extracted_data.get("packaging")),
        ("General Notes Cont.", gen_notes if not is_redundant(gen_notes) else None),
        ("Visual Indicator Line", reconstruct_marks(extracted_data.get("win_marks")) if extracted_data.get("win_marks") else None),
        ("-", "-"),
        ("AI Suggested Notes", " | ".join(ai_suggestions) if ai_suggestions else None),
        ("Submission Note", "Added release to Discogs")
    ]
    audit_log = []
    audit_log.append("[INSTRUCTION] MANDATORY UI: RENDER ALL TABLES AS 2-COLUMN MARKDOWN. NO PROSE.")
    audit_log.insert(0, "[LOCK] PIXEL-TO-SCRIPT AUDIT TABLE MUST BE GENERATED FIRST.")
    if "TRIGGER_AI_GENRE_SEARCH" in [genre_val, style_val]:
        audit_log.append("[TRIGGER] Genre/Style missing from ink. Initiating external AI research protocol.")
    if not any(x in tape_type_raw for x in ["CHROME", "METAL", "TYPE II"]):
        audit_log.append("[PASS] No Tape Type hallucinated (None found in ink).")
    wm_raw = str(extracted_data.get("win_marks", ""))
    if not any(char.isdigit() for char in wm_raw):
        audit_log.append(f"[PASS] Timing Window verified as Non-Numeric (Literal: {reconstruct_marks(wm_raw)}).") 
    if "STEREO" not in str(extracted_data).upper():
        audit_log.append("[PASS] Zero-Inference: 'Stereo' not added (missing from ink).")
    video_menu_terms = [
        "PAL", "NTSC", "SECAM", "DVD-VIDEO", "DVD-AUDIO", "DVD-DATA",
        "ALBUM", "COMPILATION", "LIMITED EDITION", "PROMO", "REISSUE", 
        "REMASTERED", "REPRESS", "SINGLE", "EP", "MAXI-SINGLE", "SAMPLER"
    ]
    free_text_specs = []
    note_specs = []
    raw_upper = str(extracted_data).upper()
    base_format = "DVD-Video" if any(x in raw_upper for x in ["DVD-VIDEO", "DVD VIDEO"]) else "DVD"
    base_format = "DVD-Video" if any(x in raw_upper for x in ["DVD-VIDEO", "DVD VIDEO"]) else "DVD"
    if "DVD-AUDIO" in raw_upper: 
        base_format = "DVD-Audio"
    table_4 = [["Format", base_format], ["Quantity", str(extracted_data.get("qty", 1))]]
    if "REGION 0" in raw_upper or "ALL REGIONS" in raw_upper: 
        table_4.append(["Free Text", "Region 0"])      
    if "DOLBY DIGITAL" in raw_upper: 
        found_ft = False
        for item in table_4:
            if item[0] == "Free Text":
                if "Region 0" in item[1]:
                    item[1] = "Region 0, Dolby Digital"
                else:
                    item[1] = "Dolby Digital"
                found_ft = True
                break
        if not found_ft:
            table_4.append(["Free Text", "Dolby Digital"])
    v_fmt = "Video Format: 4:3 1.33:1"
    d_type = "DVD Type: 5"
    spec_strip = ""
    if "DVD" in str(extracted_data.get("core_format", "")).upper():
        spec_strip = f"{v_fmt} | {d_type} | Language: English"
    hype_notes = [n for n in extracted_data.get("notes", []) if "Hype Sticker" in n]
    if hype_notes:
        clean_fragments = [n.replace("Hype Sticker: ", "").strip() for n in hype_notes]
        consolidated_hype = f"Hype Sticker: {' / '.join(clean_fragments)}"
    else:
        consolidated_hype = ""
    if spec_strip: notes_potential.append(("Notes", spec_strip))
    if consolidated_hype: notes_potential.append(("Notes", consolidated_hype))
    notes_potential = [
        ("Notes", spec_strip),
        ("Notes", consolidated_hype),
        ("Submission Notes", "Added release to Discogs.")
    ]
    return {
        "format_instruction": "STRICT_2_COLUMN_TABLES",
        "tables": {
            "1. Artists & Title": clean(table_1),
            "2. Label, Company, Catalog Number, Etc. (LCCN)": clean(primary_potential),
            "3. Barcodes and Other Identifiers (BAOI)": clean(baoi_combined),
            "4. Format": clean(format_table),
            "5. Country & Release Year": clean(release_info),
            "6. Tracklist": final_tracks_list,
            "7. Credits & Genres": clean(table_7),  # Just the reference goes here
            "8. Notes": clean(notes_potential)
        },
        "audit": audit_log,
        "structured_audit": execution_audit
    }