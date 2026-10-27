# WysiWYG-Browser — Project Conventions

This file is the durable home for project-wide conventions (UI, build, data rules).
It is referenced from `AGENTS.md` and should be consulted whenever a relevant
change is made. Add new conventions here rather than relying on chat memory alone.

Working facts about the user — identity, environment, projects, and how they want to
be worked with — are kept **outside this repo**, at
`C:\Users\Scott\.local\share\opencode\USER.md`, because they apply to every project
they work on. Update that file when you learn something durable about them rather than
trusting it to carry across a chat. Project-specific conventions stay here.

## UI Conventions

### Modal windows (mandatory)
**Every modal window must be:**
1. **Draggable** — movable by its header (drag handle), without triggering button clicks.
2. **Resizable** — has a resize handle (CSS `resize: both` or programmatic).
3. **Redraws on resize** — inner content reflows/fills the resized window (use flex
   layout: modal = `display:flex; flex-direction:column`, content = `flex:1`, and the
   growing region e.g. result box = `flex:1; overflow:auto`). Simply resizing the
   backdrop with a fixed-size inner block is NOT sufficient.

**Reference implementation:** the Amazon Add modal — `aapWrap` in
`Adds/amazon_add_page.html` (draggable, resizable, redraws). Match its behavior.

Enforced for: Amazon Add modal, WysiScan `ocr-modal`s (cliModal / Extract Text,
ocrResultModal, helpModal, renameModal, paddingModal), and any future modal.

### Protected areas — do not edit without explicit permission (mandatory)
- **Walmart Sheet** (`WalmartSheet/`, `walmart.html`, `walmartapp.js`, `walmart.py`, `generate_sheet.py`)
- **Amazon Adds** (`Adds/`, `amazon_add_page.html`, related Amazon add code)
Never modify these files unless the user explicitly asks in the current request. Main-app
changes that would normally be mirrored (e.g. description rules) must NOT be copied into them
automatically.

### Detailed change notes (mandatory)
Every change must be recorded in **`docs/WORK_LOG.md`** (files touched, why, what changed,
how to undo). Add entries as work happens, not at the end of the session.

### Notifications: toast, not alert (mandatory)
The user prefers **toast notifications** over `alert()` popups.
- Pure notifications / success confirmations → non-blocking toast, auto-dismiss after ~2s.
- Use `alert()` (or `confirm()`) ONLY when a decision is required (OK/Cancel, Proceed?).
- Reference implementation: `showToast(message, duration)` in `editor.html`.

### Pixel parity (mandatory)
Repeated controls (e.g. every "Copy" button, every "Copy Desc." button) must be
**identical fixed width** — never let content size them differently. User is OCD
about this; mismatches at any width are flagged.

### UI-edit discipline (mandatory)
Make ONLY the explicitly requested change. Do NOT also relocate/move other UI
elements the user didn't mention. For WysiScan, "move buttons to a Menu" meant the
blue banner's buttons (Hot Keys / Theme / Exit / AI Prompt) ONLY — not the
main-form scan-controls toolbar. Show exact before/after diffs for HTML/UI edits.

### Accent colors (mandatory)
Accent **text** color is theme-aware, never hard-coded:
- Main app — use `var(--wysiwyg-accent-text)` (`#0000FF` in Light Mode, `#FFFF00` in Dark Mode).
- WysiScan — use `var(--primary-text)` (same values).

Rules:
1. Never use `#0000FF` for text — in Dark Mode it is only 1.9:1 contrast on the panel.
2. Never use `#FFFF00` for text on a light surface — it would be 1.07:1 on white.
3. `var(--wysiwyg-blue)` / `var(--primary-color)` are **background/border** colors only; they
   carry white or yellow text and are readable in both themes.
4. Text on a yellow background (e.g. the hamburger `☰ Menu` button) stays blue.

## Data / Scraping Conventions

- **Discogs data always via API** (token in `.env`), never by scraping discogs.com HTML.
- **Amazon Adds** "Search Keywords" (Subject Keyword) field FORBIDS label / publisher /
  company names — never include `Brand Name`, `Manufacturer`, `Series`, or any
  label/publisher/company name as a keyword candidate.
- **Amazon Adds** Country/Region of Origin must ALWAYS = "United States" (our origin).
- Output cleanup: strip headers / `**` / table rows; replace `|` with ` - `.

## Build / Packaging Conventions

- WysiScan.exe: built via `build_scanner.py` using PyInstaller `--onefile` (bundles
  scanner_test.html, WysiScan.ico/.png, config.json). Main app uses `--onedir`
  (onefile trips Defender Bearfoos.A!ml). Do NOT unify these without asking.
- All big changes must be written to `changelog.txt` under the current version header.
- Do NOT commit/push unless the user explicitly asks; user tests himself first.
- Push only to `main` (never the local `Browser` branch).

## Secrets

- `.env` holds `GEMINI_API_KEY` and `DISCOGS_TOKEN` (never commit raw keys; they are
  redacted in summaries). Discogs token cannot be rotated — contain it, do not insist
  on rotation. `allpass.json` (editor/admin pw) is fine to push.
