# Code review — confirmed issues & fixes

## What was reviewed (coverage, honest)

Targeted pass over the live code, focused on the user's daily workflow (scrape →
condition/description assembly → listing output) and the riskiest components:

- `app.js` init sequence + a full `getElementById` cross-check against `index.html`
- `app.js` `processFormatData` / `groupFlaws` / `assembleDescription` / `generateSku`
- `main.py` — `/scrape`, `/format-html`, `/save-css`, counters, endpoint/route cross-check
  (all 68 front-end `fetch()` calls vs all server routes)
- `style_guide.html` (CSS parse-and-write-back tool)
- `WysiScan` `buildCliPlainText` export
- `Adds/amazon_add_page.html` keyword rendering

Not deep-reviewed this pass (flagged as follow-up): the tail of the `/scrape`→format
pipeline in `main.py`, `Adds` server-side keyword/country extraction, `Uberpaste/UberPaste.py`
widget lifecycle, `ChromeExt`, `WalmartSheet` Python writer.

## Findings (confirmed by reading the code)

### 1. HIGH — `app.js:67` null-deref crash on every load (stale localStorage)

```js
if (dockPref === 'true') {
    document.getElementById('dockScanner').checked = true;   // element removed from header
}
```

The `dockScanner` checkbox was removed from `index.html` (app.js:531 comment says so), so
`getElementById('dockScanner')` is `null`. Any user who ticked that box before it was removed
still has `wysiwyg_dock_scanner === 'true'` in localStorage (nothing clears it), so on **every
page load** `DOMContentLoaded` throws `TypeError: Cannot set properties of null`. The throw
aborts the rest of the handler, so the **Auto Generate toggle state is never restored**
(app.js:78-79) for those users.

Trigger: had "dock scanner" checked in an older version → upgrade → open app → Auto Generate
never remembers its setting; console shows an uncaught TypeError each load.

Fix: guard it, matching the surrounding style:
`if (dockPref === 'true' && document.getElementById('dockScanner')) { ... }`

### 2. MEDIUM — `main.py:943` `/save-css` overwrites `styles.css` with no backup

```python
@app.post("/save-css")
async def save_css_endpoint(data: dict = Body(...)):
    css_content = data.get("css", "")
    ...
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(css_content)
```

The style guide posts the whole textarea; one accidental Save (or a hand-mangled edit in the
textarea) permanently destroys the app's stylesheet. No `.bak`, no size/emptiness validation.

Fix: before writing, copy the current file to `backups/styles.css.bak` (or `styles.css.<ts>.bak`),
and reject `css_content` that is empty or suspiciously short (e.g. `< 200` chars) with a 400.

### 3. MEDIUM — `app.js:2014` / `app.js:2024` unescaped regex from user-editable dropdown values

```js
const regex = new RegExp(ed + "[,\\s]*", "gi");          // ed = edition dropdown value
const regex = new RegExp(`(?<!Colored \\()\\b${c}\\b`, 'gi');  // c = color value
```

Shipped defaults are clean, but the user edits these lists in the Settings Editor. An edition
like `Reissue (Remastered)` or `180g [Test]` makes `new RegExp` throw `SyntaxError`, and the
Generate click fails (uncaught, silent to the user). Same risk for color values containing
regex metacharacters.

Fix: escape the interpolated value:
`const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');` then `new RegExp(esc(ed) + "[,\\s]*", "gi")`.

### 4. LOW — `app.js:22-23` footer year never set (`footerYear` vs `id="Year"`)

```js
const footerYear = document.getElementById('footerYear');   // null — index.html uses id="Year"
if (footerYear) footerYear.textContent = new Date().getFullYear();
```

Guarded so no crash, but the year is never populated from JS.

Fix: change the id lookup to `'Year'` (one word) in app.js, or add `id="footerYear"` to the
footer element in index.html — whichever matches the intended markup.

### 5. LOW — `app.js:3096` `syncMediaOptionsToTextBox` is dead code

It looks up `mediaOptions`, which was removed from `index.html` (Media Description multiselect
removed in v1.14.0.0), so it always early-returns. Harmless, but dead.

Fix (optional): delete the function and any caller; or leave it.

### 6. LOW / cosmetic — `style_guide.html` CSS parser limitations

`ruleRegex = /([^{}]+)\{([^}]+)\}/g` (line 172) cannot represent nested blocks (`@media`,
`@keyframes`), so usage counts and hardcoded-color detection are approximate. `updateVariable`
(line 351) relies on "first `[data-theme="dark"]` is the block definition", which is true today
but brittle. No data loss; the guide display is just sometimes wrong.

Fix (optional): none required; if desired, only run the usage/hardcoded scan on top-level rules.

## Reviewed and found clean

- `/scrape` (main.py:1161) — defensive `.get()` access throughout; clear 401/404/429 messages.
- `groupFlaws` / `processFormatData` — flaw grouping (prefix/suffix/Corner, `/` separators)
  matches the design decisions in the changelog.
- `buildCliPlainText` (WysiScan) — blank-line-separated groups, `Media Description:` header
  above its block, as documented.
- Endpoint cross-check — every front-end `fetch()` maps to a server route; `/exit` belongs to
  WysiScan's own server on :8010.
- Counter endpoints (`/api/get-counters`, `/api/increment-counter`) — fine for single-user local use.

## Fix order (for the implementation agent)

1. `app.js:67` — add the `&& document.getElementById('dockScanner')` guard. (One line, fixes a
   recurring console error + broken Auto Generate restore.)
2. `main.py:943` — backup-before-write + empty-CSS rejection in `/save-css`.
3. `app.js:2014` + `app.js:2024` — escape interpolated edition/color strings before `new RegExp`.
4. `app.js:22` — `footerYear` → `Year`.
5. (Optional) remove dead `syncMediaOptionsToTextBox`; (optional) style-guide parser hardening.

## Validation

- `node --check app.js` after edits; `python -m py_compile main.py` after the `/save-css` change.
- Per project convention the **user tests the UI manually**:
  - Fix 1: with `wysiwyg_dock_scanner` set (or after adding the guard, no console error on load;
    Auto Generate remembers its state).
  - Fix 2: save CSS from the style guide → confirm `styles.css` updates AND a `.bak` appears;
    try posting empty CSS → expect 400.
  - Fix 3: add a fake edition `Reissue (Test)` in the Settings Editor, select it on a multi-format
    (" + ") release, Generate → no console error.
  - Fix 4: footer shows the current year.
- Update `changelog.txt` under the current version header and log the decision in
  `.continuity/decisions.json` (same pattern as the accent-text change).

## Follow-up (not done this pass)

If you want a second sweep: `/scrape` pipeline tail in `main.py`, server-side Adds
keyword/country extraction, `UberPaste.py`, `ChromeExt`, `WalmartSheet` Python writer.
