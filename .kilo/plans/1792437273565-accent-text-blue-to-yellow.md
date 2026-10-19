# Blue accent text → Yellow accent text (Dark Mode readability)

## Goal

Remove `#0000FF` as a *text* color across the WYSIWYG app family and replace it with the
app yellow `#FFFF00`, so header labels, footer text and status updates are readable.
Blue used as a *background* is deliberately left alone.

## Decision (confirmed by user)

> **Yellow text only in Dark Mode.**

- **Light Mode:** blue text stays `#0000FF` (it is perfectly readable on the app's white
  surfaces — 8.6:1 on white).
- **Dark Mode:** blue text becomes `#FFFF00` (15.5:1 on the near-black panel).
- **Blue backgrounds/borders stay `#0000FF`** (they carry white or yellow text and are
  already readable).

This mirrors the pattern the **Adds pages already use**
(`Adds/*_add_page.html`: `--accent: #0000ff` in light, `--accent: #ffd400` in dark).
We are generalising that existing pattern to the main app and WysiScan.

### Why blue is "unreadable"

`#0000FF` on the Dark Mode panel `#1e1e1e` = **1.94:1** contrast (WCAG needs 4.5:1).
The main app's modal titles and WysiScan's panel label / status line are exactly that
combination, because their backgrounds flip to `--bg-content` / `--bg-container` in
Dark Mode while their text color stays hard-coded blue.

## Implementation

### 1. `styles.css` — add a theme-aware accent-text token

In `:root` (after line 10, `--wysiwyg-yellow: #FFFF00;`):

```css
    /* Theme-aware accent for TEXT: blue in Light Mode, yellow in Dark Mode
       (#0000FF on the dark panel is only 1.9:1 and cannot be read). */
    --wysiwyg-accent-text: #0000FF;
```

In the existing `[data-theme="dark"] { ... }` block (lines 107–130), add:

```css
    --wysiwyg-accent-text: #FFFF00;
```

No other `styles.css` change. The `h2` rule (line 49) stays
`background-color: var(--wysiwyg-blue); color: var(--wysiwyg-yellow);` — blue bar,
yellow text, readable in both themes.

### 2. `index.html` — 7 modal / picker titles

Replace `color: var(--wysiwyg-blue);` with `color: var(--wysiwyg-accent-text);` at
lines **41** (generic modal title), **54** (Hot Keys), **72** (Feature Request),
**92** (Cost Calculator), **137** (Edit Conditions), **196** (Select Conditions),
**222** (Select Options).

**Do NOT touch line 243** (the `☰ Menu` hamburger button): it is blue text on a
*yellow* button background — switching it to yellow would make it invisible in Dark Mode.

### 3. `editor.html` — 1 dynamic title

Line 415:

```js
title.style.cssText = 'border-bottom: 2px solid var(--wysiwyg-blue); padding-bottom: 8px; margin-bottom: 15px; color: var(--wysiwyg-blue); font-weight: bold; text-align: center; text-transform: uppercase; letter-spacing: 1px;';
```

→ use `var(--wysiwyg-accent-text)` for **both** `color` and `border-bottom` (the blue
underline is also 1.9:1 on the dark editor panel, i.e. effectively invisible).
If the border must stay blue, change only the `color` value.

Lines 10, 76, 85 (blue banner backgrounds, blue modal-footer border) are unchanged.

### 4. `app.js` — no change

The only matches are `var(--wysiwyg-blue-light, #e6f0ff)` (lines 2994, 3158, 3252, 3935,
4041, 4226, 4298, 4382, 4438) — a *light-blue selection background* with text forced to
`#000`. Not blue text; leave it.

### 5. `WysiScan/scanner_test.html` — header label + status message

- `:root` (lines 14–24): add `--primary-text: #0000FF;`
- `[data-theme="dark"]` (lines 26–33): add `--primary-text: #FFFF00;`
- **Line 620** — the `📦 Image Convert` panel header label:
  `color: var(--primary-color)` → `color: var(--primary-text)`
- **Line 3545** — `cliStatusMsg` in the OCR modal footer (the status update):
  `color: var(--primary-color)` → `color: var(--primary-text)`

Leave unchanged: lines 44–45 (`.menu-btn` — blue text/border on a yellow button),
143–149 (`h1` blue background + yellow text), 157–159 (blue button + yellow text).

### 6. `Adds/amazon_add_page.html` + `Adds/discogs_add_page.html` — align the yellow

Already theme-aware. In the `body.dark` block (lines 25 and 27 in each file), change
`--accent: #ffd400` → `--accent: #FFFF00` and `--btn: #ffd400` → `--btn: #FFFF00` so the
family uses one single yellow. Light-mode `#0000ff` stays.

### 7. `Uberpaste/UberPaste.py` — align the dark-mode "keep" marker

Lines **177** and **192** (dark-mode branch): `"#00FFFF"` → `"#FFFF00"`, so the
kept-item marker uses the same app yellow as everything else.

Line 198 (light mode, `"#0000FF" if is_kept`) stays — Light Mode keeps blue per the decision.
Lines 615–624 (`QListWidget::item:selected` cyan background with black text) stay —
that is a selection background, not blue text.

## Explicitly NOT changed

| Item | Reason |
|---|---|
| `styles.css` `h2` blue background + yellow text | Background, already readable |
| `.scraper-button` / `.search-button` / `.hk-key-btn.capturing` blue backgrounds | Backgrounds with white text |
| `.save-bar` blue top border, `.history-sidebar` blue right border | Borders, not text |
| `index.html:243` hamburger blue text on yellow button | Would become yellow-on-yellow |
| `app.js` `--wysiwyg-blue-light` selection highlight | Light-blue background with `#000` text |
| `WysiScan` `.menu-btn`, `h1`, generic `button` | Blue backgrounds / blue-on-yellow |
| `WalmartSheet`, `WysiChat`, `admin.html`, `search.html`, `results_viewer.html`, `model_tester.html` | Contain no `#0000FF` |
| `old.index.html`, `old.app.js`, `tmp_*` files | Backups / scratch, not served |

## Validation

- Per `AGENTS.md`, **the user verifies the UI manually** — do not launch the app or drive
  a browser. Only cheap syntax checks are run:
  - `python -m py_compile Uberpaste/UberPaste.py`
- `node --check app.js` is unnecessary (app.js is untouched).
- `styles.css` is served by `main.py` **without** cache headers (line 931), so the browser
  may heuristically cache it — the user should hard-refresh (Ctrl+F5) before judging.
  (`/app.js` already has `Cache-Control: no-cache`; `styles.css` does not.)
- Manual check list for the user: main app Dark Mode → open Hot Keys / Cost Calculator /
  Edit Conditions / Select Conditions modals and confirm the titles are yellow and legible;
  WysiScan Dark Mode → check the `📦 Image Convert` label and the CLI modal's status line;
  confirm Light Mode still shows blue titles.

## Housekeeping

1. `changelog.txt` — add a bullet under the current header `### v1.14.1.0 - 2026-10-13`:
   > `-- UI: accent text color is now theme-aware — blue (#0000FF) in Light Mode, yellow (#FFFF00) in Dark Mode — so modal titles, WysiScan's panel label and its CLI status line are readable on the dark panel (was 1.9:1 contrast).`
2. `.continuity/decisions.json` — log the decision (CLI not installed; append an object to
   the JSON array with `id`, `question`, `answer`, `timestamp`, `tags: ["ui","colors"]`,
   `files`, `status: "active"`, `metadata.status: "active"`):
   - Q: "Why does accent text switch from blue to yellow only in Dark Mode?"
   - A: "Blue (#0000FF) on the Dark Mode panel (#1e1e1e) is 1.9:1 and unreadable, while pure #FFFF00 text on the Light Mode white surfaces would be 1.07:1 and equally unreadable. So a theme-aware token was introduced: --wysiwyg-accent-text (main app) / --primary-text (WysiScan) = #0000FF in Light Mode, #FFFF00 in Dark Mode. Blue backgrounds were left unchanged since they carry white or yellow text. This generalises the pattern the Adds pages already used (--accent #0000ff light / #ffd400 dark). Scope covered main app, WysiScan, Adds pages and UberPaste; the UberPaste dark 'keep' marker changed from cyan #00FFFF to #FFFF00 for family consistency."
3. `docs/CONVENTIONS.md` — add a short UI convention: *"Accent text color is theme-aware: use `var(--wysiwyg-accent-text)` (main app) / `var(--primary-text)` (WysiScan) for any colored text; never hard-code `#0000FF` for text, and never use `#FFFF00` for text on a light surface."* (The existing "blue banner" line refers to a WysiScan element that no longer exists as a button bar, but the `h1` banner is still blue, so the line stays valid.)
4. Do **not** commit or push (project convention — the user commits after testing).

## Risks

- The Adds-page `#ffd400` → `#FFFF00` change is the only edit not strictly required by the
  request; it is a one-value family-consistency alignment and is trivially revertible.
- The UberPaste cyan → yellow change alters a distinct visual marker; if the cyan is
  meaningful to the user, drop step 7 and keep `#00FFFF`.
