src = open('Adds/discogs_add.py', 'rb').read().decode('utf-8')

# Add a cleanup helper after `text = str(raw_text)`
old_init = (
    "    text = str(raw_text)\r\n"
    "    out = {}\r\n"
)
new_init = (
    "    text = str(raw_text)\r\n"
    "    out = {}\r\n"
    "\r\n"
    "    _LABELS = r'(?i)\\b(R\\s*C\\s*A|BMG|SONY|COLUMBIA|WARNER|CAPITOL|MCA|UNIVERSAL|EMI|ATLANTIC|ARISTA|GEFFEN|MERCURY|POLYDOR|ISLAND|ELEKTRA|EPIC|VIRGIN)\\b'\r\n"
    "    def _clean_name(n):\r\n"
    "        # strip a leading label token and any catalog number from a name\r\n"
    "        n = re.sub(_LABELS, ' ', n)\r\n"
    "        n = re.sub(r'\\b\\d{4,}[\\d \\-]*\\b', ' ', n)\r\n"
    "        n = re.sub(r'\\s+', ' ', n).strip()\r\n"
    "        return n\r\n"
)
assert old_init in src, 'init not found'
src = src.replace(old_init, new_init, 1)

# Apply _clean_name to artist extraction
old_at = (
    "    if at_slash:\r\n"
    "        out[\"artist\"] = at_slash.group(1).strip().title()\r\n"
    "        out[\"title\"] = at_slash.group(2).strip().title()\r\n"
    "    elif at_block:\r\n"
    "        out[\"artist\"] = at_block.group(1).strip().title()\r\n"
    "        out[\"title\"] = at_block.group(2).strip().title()\r\n"
)
new_at = (
    "    if at_slash:\r\n"
    "        out[\"artist\"] = _clean_name(at_slash.group(1)).title()\r\n"
    "        out[\"title\"] = at_slash.group(2).strip().title()\r\n"
    "    elif at_block:\r\n"
    "        out[\"artist\"] = _clean_name(at_block.group(1)).title()\r\n"
    "        out[\"title\"] = at_block.group(2).strip().title()\r\n"
)
assert old_at in src, 'at_block not found'
src = src.replace(old_at, new_at, 1)

open('Adds/discogs_add.py', 'wb').write(src.encode('utf-8'))
print('artist cleanup applied')
