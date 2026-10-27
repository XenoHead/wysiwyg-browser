# Work Log — detailed change notes

Running log of AI-assisted changes. Newest work at the bottom.
Each entry lists the files touched, why, exactly what changed, and how to undo it.

---

## 2026-10-27

### 1. Editor — automatic backups before server overwrites
**Files:** `main.py`
- Added helper `backup_pre_overwrite(path, prefix)` → copies the existing file to
  `<prefix>_pre_YYYYMMDD_HHMMSS.json` in the same directory, timestamp prevents duplicates.
- `POST /api/admin/sync-conditions` (editor "Update to Server") backs up
  `\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json` → `conditions_pre_*.json`.
- `POST /upload-menus` backs up the server `data.json` → `data_pre_*.json` (in addition to the
  existing `.old` backup).
**Undo:** remove the two `backup_pre_overwrite(...)` calls and the helper.

### 2. Editor — toast notifications instead of alerts
**Files:** `editor.html`, `docs/CONVENTIONS.md`
- Added `showToast(message, duration = 2000)` (fixed-position green toast, 2 s, auto-dismiss).
- Replaced success `alert()`s in `saveConditions`, `syncConditions`, `saveData`
  (reload delayed 1.2 s so the toast is visible) and `uploadMenus`.
- Error paths still use `alert()`; confirmation prompts (`confirm()`) unchanged.
- New mandatory convention documented: toast for notifications, alert only for decisions.
**Undo:** restore the `alert()` calls and delete `showToast`.

### 3. Editor — conditions refresh/caching fixes
**Files:** `editor.html`, `app.js`, `main.py`
- Condition title/text inputs commit on `oninput` (previously `onchange`, lost edits).
- Save re-renders immediately from local state, then re-fetches from disk.
- All `/api/conditions` fetches use `cache: 'no-store'` + `?t=Date.now()`; server sends
  `Cache-Control: no-store` (FileResponse and JSON defaults).
- Main app reloads conditions on window focus / tab visible (`refreshCustomOptions`).
**Undo:** remove the no-store params/headers and the two listeners.

### 4. Editor — conditions search improvements
**Files:** `editor.html`
- Added ✕ button beside the search box: clears term, redraws, refocuses.
- Blank items (`title` and `text` empty) are always included when a search term is active,
  so "Add New Item" rows appear immediately.
**Undo:** remove button + `isBlankConditionItem` usage in the two filters.

### 5. Passwords — PBKDF2 hashing
**Files:** `main.py`, `app.js`, `WalmartSheet/walmartapp.js`, new `set_password.py`,
new `hash_password.py`, `!build.bat`, PowerShell profile (user machine)
- `allpass.json` may now store `pbkdf2_sha256$iterations$salt$hash` values; plaintext still works.
- New `POST /api/verify-password` compares constant-time and returns `role` (`editor`/`admin`).
- Frontends verify server-side first, with the old local plaintext compare as fallback.
- `set_password.py`: menu / `editor` / `admin` — prompts twice (hidden), preserves other keys,
  writes `allpass.json.bak` first.
- `hash_password.py`: one-shot hash printer.
- `!build.bat` deletes both helper scripts from `dist\WYSIWYG` if they ever appear
  (PyInstaller/installer never bundle them anyway).
**Undo:** revert frontends to plaintext compare; delete helpers.

### 6. Main app — service-status polling
**Files:** `main.py`, `app.js`
- `/api/service-status` result cached 20 s (`_SERVICE_STATUS_CACHE`).
- `updateServiceStatus()` returns immediately while `document.hidden`; refreshes on
  `visibilitychange`.
**Undo:** remove cache globals and the hidden guard.

### 7. Main app — lazy network + auto-exit on browser close
**Files:** `main.py`, `app.js`, `index.html`, `editor.html`, `admin.html`, `search.html`,
`walmart.html`, `style_guide.html`
- `resolve_server_paths()` is lazy and only caches successes: no UNC probe at import.
  Removed `SERVER_VERSION_PATH` / `INSTALLER_PATH` / `SERVER_EXE_PATH` constants; replaced by
  `get_server_version_path()` / `get_installer_path()` used only at request time.
- `/api/version` no longer checks the share. New `/api/server-version` is called by the UI
  after load (`checkServerUpdate()`); update banner logic moved there.
- `init_conditions()` no longer copies from the share at startup — local defaults only.
- `/heartbeat` accepts GET/POST `{tab_id, hidden, closed}`; `ACTIVE_TABS` tracks tabs.
- New `/heartbeat.js` (served by `main.py`) is loaded by every page; each tab gets a
  `sessionStorage` id, sends every 3 s, and a keepalive `closed:true` beacon on `pagehide`.
- Watchdog (browser mode only, `main.py`): removes tabs on close, expires stale tabs after
  120 s visible / 30 min hidden, and exits the app ~12 s after the last tab disappears
  (grace window so an F5 reload cannot kill the server).
**Undo:** remove the script tags, `/heartbeat.js`, the tab tracking + watchdog; restore the
module-level `resolve_server_paths()` call and the old `/api/version` behaviour.

### 8. WysiScan — responsiveness (event loop)
**Files:** `WysiScan/scanner_server.py`
- Converted 25 blocking endpoints from `async def` → `def` (threadpool), including scan,
  import, crop/rotate/deskew, OCR, batch-convert, undo/redo, gallery, CLI prompt.
- `ocr_and_lookup` also uses sync `httpx.get` instead of `AsyncClient`.
- Effect: long scans/OCR no longer block heartbeats or other API calls.
**Undo:** change those signatures back to `async def` (and restore `AsyncClient`).

### 9. WysiScan — heartbeat / self-shutdown
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- Heartbeat now posts `{hidden}` and fires on `visibilitychange`.
- Watchdog limits: 120 s while visible, 30 min while hidden (Chrome throttles background timers).
- Root cause of the "crashes after sitting a while": the old 60 s limit + throttled timers.
**Undo:** restore the old 60 s check and stateless heartbeat.

### 10. WysiScan — Extract Text in packaged builds
**Files:** `WysiScan/scanner_server.py`, `WysiScan/build_scanner.py`, `WysiScan/build_app.py`,
`WysiScan/WysiScan.spec`, `WysiScan/ScannerApp.spec`
- `gemini_pool.py` lives in the repo root and was not bundled by the scanner builds, causing
  `ModuleNotFoundError: gemini_pool` (HTTP 500) for Extract Text.
- Added `--hidden-import=gemini_pool --paths=..` to both build scripts and
  `pathex=['..']` + `gemini_pool` hidden import to both specs.
**Undo:** remove those build flags.

### 11. WysiScan — import dialog start folder
**Files:** `WysiScan/scanner_server.py`
- `/browse-file` opens **This PC** on first use, then the folder saved in
  `config.json → last_import_dir`; no network path is used as a start folder.
**Undo:** remove the initialdir logic and the `last_import_dir` save.

### 12. WysiScan — thumbnails + caching
**Files:** `WysiScan/scanner_server.py`, `WysiScan/scanner_test.html`
- New `/thumb?path=&w=` endpoint: PIL thumbnail (EXIF-corrected, max 600 px, JPEG q82),
  disk cache in `temp/thumbs` keyed by path+mtime+width, `max-age=86400`; stale thumbs
  (>24 h) removed by the existing 30-min janitor. Falls back to the original on error.
- Gallery tiles and import-queue tiles use `/thumb`; clicks still open the full image.
- `scanner_server.py` caches `scanner_test.html` in memory (still `no-store` to the browser).
**Undo:** point `img.src` back at `/view-image`; remove `/thumb` + `_INDEX_HTML_CACHE`.

### 13. WysiScan — security hardening
**Files:** `WysiScan/scanner_server.py`
- CORS is no longer `*`. Allowed origins: `127.0.0.1`/`localhost` on ports 8008 (main app
  static mount) and 8010 (scanner), methods GET/POST, header Content-Type.
- New HTTP middleware rejects requests whose `Origin` header is present and not in that list
  (403 `Cross-origin request blocked.`).
- New helpers `_is_image_file()` (extension allow-list) and `_is_under_allowed_root()`
  (temp, scans, configured `save_location`/`last_import_dir`).
- `/view-image`: image files under an allowed root only; now actually sends no-cache headers
  (the old no-cache branch was dead code after an early `return`).
- `/thumb`: image files only (import previews may come from any folder by design).
- `/open-file`: image files under an allowed root only.
**Undo:** restore the permissive CORS block, drop the middleware and the two guards.

### 14. WysiScan — launch race fix
**Files:** `main.py`
- `POST /run-wysiscan` was `async def` and slept a fixed 2 s, then the UI opened
  `http://127.0.0.1:8010/`. Scanner import (cv2/numpy/win32com) can take longer than 2 s,
  so the popup could land on "connection refused" (scanner "won't open").
- Endpoint is now a normal `def` (threadpool, so the event loop/heartbeats keep running) and
  polls `is_port_in_use(8010)` every 250 ms for up to ~15 s. It only reports success once the
  scanner is actually listening; if the child exits during startup it returns the exit code
  and points at `WysiScan\wysiscan_debug.log`.
- The scanner child is started with `CREATE_NEW_PROCESS_GROUP` (Windows) so it is not tied to
  the main app's console/control events.
**Undo:** restore the async endpoint with `time.sleep(2.0)` and remove `creationflags`.

### 15. Image refresh / stale-image fixes (audit item 10 + rotate bug)
**Files:** `WysiScan/scanner_server.py`, `WysiScan/scanner_test.html`
- `/view-image` dead code removed and no-cache headers now actually applied (done together with
  item 13); `/thumb` cache shortened to `private, max-age=60` so edited files can't show a
  day-old thumbnail.
- Server cache-busters changed from `int(time.time())` (1-second resolution) to
  `time.time_ns()` in rotate-image, rotate-image-fine, deskew-image, manual-crop replace,
  undo and redo. Two actions inside the same second previously produced the *same* URL, so the
  browser skipped the reload and rotations appeared to be dropped.
- New JS helpers `withCacheBuster()` and `refreshImageElements(path, fullUrl)`.
  `refreshImageElements` refreshes every `<img>` for a path; gallery tiles stay on `/thumb`
  (busted per call), main previews reload the full image with a fresh `v=` parameter.
- `rotateImage`, fine-rotate, deskew, auto-deskew, undo and redo now all use
  `refreshImageElements`, so the cropped/original previews always repaint after an edit.
**Undo:** restore the inline `querySelectorAll(...).forEach(img => img.src = ...)` blocks and
`int(time.time())` busters.

### 16. Main app — single source of truth for share paths (audit item 11)
**Files:** `main.py`
- New `DEFAULT_SERVER_ROOT` constant; `POSSIBLE_ROOTS` derives from it.
- New helpers `get_server_conditions_path(lowercase=False)` and `get_reports_path()`.
- Replaced every hardcoded `\\192.168.0.108\FYRShare\...` path:
  `get_conditions(master)`, `save_conditions(master)`, `sync_conditions`,
  `merge_conditions` (including the lowercase `conditions.json` fallback) and `/api/add-report`
  (`reports.txt`, which lives one level above `FYRTools`).
- Only `DEFAULT_SERVER_ROOT` still contains the UNC name, so a future share/IP change is one line.
**Undo:** restore the inline literal paths.

### 17. Standalone password manager executable
**Files:** `set_password.py`, `.gitignore`, build output `dist_tools/set_password.exe`
- `set_password.py` now resolves `allpass.json` in this order: beside the exe/script,
  current working directory, `C:\FYRTOOLS\WYSIWYG\allpass.json`, then the dev repo copy.
  It prints which file it is using.
- Built a one-file console exe with the 3.11 venv (PyInstaller cannot freeze 3.14):
  `.\.venv311\Scripts\python.exe -m PyInstaller --noconfirm --onefile --console --name set_password --distpath dist_tools --workpath build_tools --specpath build_tools set_password.py`
- Output: `dist_tools\set_password.exe` (~7 MB, stdlib only). Kept in a separate folder so the
  WYSIWYG `dist\` build is untouched; both tool folders are git-ignored.
**Undo:** delete `dist_tools/`, `build_tools/`, and the `.gitignore` lines.

### 18. Icon for the standalone password tool
**Files:** new `assets/set_password.ico`, rebuild of `dist_tools/set_password.exe`
- Generated a multi-size `.ico` (16–256 px) with PIL: blue rounded tile, white padlock
  shackle, amber lock body with keyhole, small white key accent.
- Rebuilt with `--icon C:\Git\WysiWyg-Browser\assets\set_password.ico`.
  The icon path must be **absolute** — a relative path is resolved against the spec folder
  (`build_tools/`) and PyInstaller fails with `FileNotFoundError`.
- Verified the embedded icon by extracting it from the built exe.
**Undo:** rebuild without `--icon`, delete `assets/set_password.ico`.

### 19. Standalone WysiScan single-file exe
**Files:** `WysiScan/scanner_server.py`, build output `WysiScan/dist/WysiScan.exe`
- Built with the existing `WysiScan/build_scanner.py` (`.venv311`, PyInstaller 6.22.2):
  one-file, `--noconsole`, icon `WysiScan.ico`, bundles `scanner_test.html`, `WysiScan.ico/png`
  (into `WysiScan/` inside the bundle, matching `ASSET_DIR`) and `config.json`;
  `--hidden-import=gemini_pool --paths=..` so Extract Text works.
  Result: `WysiScan\dist\WysiScan.exe` (~83 MB). `WysiScan.spec` is regenerated by the build.
- Fixed Browse dialogs in the frozen build: there is no `python.exe` to run the old
  `-c <script>` approach. `_run_py_dialog` now, when frozen, re-launches `WysiScan.exe` with
  `--run-script <tmp.py> --run-result <tmp.txt>`; a new `__main__` branch runs the script with
  `runpy` and redirects stdout to the result file (windowed apps have no console).
  Verified by executing a script that wrote a marker + printed text.
- Image Convert is not bundled in the standalone. `imageconvert_available()` checks for it and
  `batch_convert` / `open_convert_gui` now return a clear error instead of relaunching the
  scanner with `--imageconvert`.
- Verified the exe serves `/config` on 8010 and that it self-exits after the heartbeat grace
  period when no browser is attached. Test artifacts (`scans/`, `temp/`, log) removed from `dist`.
**Undo:** delete `WysiScan/dist/`, `WysiScan/build/`; revert the dialog dispatcher and
`imageconvert_available` guards.


### 20. Conditions — All Types picker unified (Media / Sleeve)
**Files:** `index.html`, `app.js`
- Added `#allTypesView` dropdown (`Media (All Types)` / `Sleeve (All Types)`) to the picker footer,
  to the left of the Media Type / Unfavorite All controls.
- `setAllTypesControlsVisible()` now also syncs that dropdown to the current view
  (`window.currentThreeColumnMode`).
- The footer controls (view dropdown, Media Type, ☆ Unfavorite All) now show in **both**
  all-types views; `openSleeveConditionThreeColumnModal()` previously hid them.
- `unfavoriteAllCurrentType()` is mode-aware: media mode clears favorites on
  `mediaCondition` for the selected media type; sleeve mode clears favorites on
  `customOptionsData[type]` (lp/cd/cassette).
- Sleeve all-types columns now get the same blue "active media type" header highlight as the
  media view (driven by `#allTypesMediaType`).
- New listener: switching `#allTypesView` reopens the other all-types view, preserving the
  current search text.
**Undo:** remove the dropdown + listener; restore `setAllTypesControlsVisible(false)` in the
sleeve all-types opener; revert `unfavoriteAllCurrentType` and the sleeve header styling.

### 21. Sleeve Description gets a "with " prefix
**Files:** `app.js` (main app only — Walmart Sheet reverted per protected-area rule)
- In `processFormatData()`, a non-empty Sleeve Description is normalized before it is
  assembled into the description:
  - leading `with`/`With`/`WITH` (any case) is stripped, then
  - the text is prefixed with lowercase `with `.
  - Examples: `Tearing` → `with Tearing`; `With Tearing` → `with Tearing`;
    `with tearing` → `with tearing`; `Without sleeve` is untouched (`\b` prevents a false match).
- The stored input field is not modified — only the generated description.
- No other description logic changed (sleeve-type label, insert detection, gatefold handling all
  still see the text; `includes()` checks are unaffected by the prefix).
**Undo:** delete the normalization block in `app.js`.
**Note:** the same block was briefly added to `WalmartSheet/walmartapp.js` and has been fully
reverted — Walmart Sheet is a protected area (see `docs/CONVENTIONS.md`).

### 22. "Artwork / Insert" collapses to "Artwork" when Insert is mentioned
**Files:** `app.js`
- In `processFormatData()`, before the sleeve-type label is chosen, `sleeveMentionsInsert` is
  computed from:
  - the Sleeve Description text, and
  - every selected sleeve condition (`customOptionsSelected` JSON entries — title **and** text),
  case-insensitive (`/insert/i`), including strings like `tab-marks to Insert`.
- For CD/DVD/Blu-ray with a sleeve grade and no sleeve packaging, the label becomes
  **Artwork** instead of **Artwork / Insert** when that flag is true.
- `Artwork` is never removed; only the `/ Insert` suffix is dropped.
- Walmart sheet has no sleeve-condition multiselects; its existing description-only check was
  left unchanged.
**Undo:** restore the `sleeveDesc.toLowerCase().includes("insert")` check.

### 23. Cassette "JCard" collapses to "Artwork" when Jcard is mentioned
**Files:** `app.js`
- Same helper text as the insert rule: `sleeveTextForRules` = Sleeve Description +
  all selected sleeve condition titles/texts.
- `sleeveMentionsJcard = /j[\s-]?card/i` matches `Jcard`, `JCard`, `J-card`, `J Card`, any case.
- For cassettes with a sleeve grade and no sleeve packaging, `sleeveTypeLabel` becomes
  **Artwork** instead of **JCard** when matched, so "Jcard" is not repeated alongside the
  description/conditions.
- Example: `Cassette Very Good+ JCard with hole-punch through Jcard …` →
  `Cassette Very Good+ Artwork with hole-punch through Jcard …`.
- Vinyl/CD logic and the insert rule are unchanged; Walmart Sheet untouched (protected).
**Undo:** change the cassette branch back to `sleeveTypeLabel = "JCard";`.

### 24. Flaw grouping — "Corner/Edge <flaw>"
**Files:** `app.js` (`groupFlaws`)
- `splitFlaw()` now recognises `Edge`/`Edges` the same way it already handled `Corner`
  (`/^edges?\s/i` → prefix `Edge`, separator `' '`, suffix = rest; `Corner` check widened to
  `Corners`).
- The suffix-grouping merge no longer assumes the shared prefix is always "Corner". For the
  space-separated (location) group it emits `<prefixes joined by /> <suffix>`:
  `Corner creasing` + `Edge creasing` → **`Corner/Edge creasing`**.
- Previously the special case produced `Corner Corner/Edge`, and `Edge …` items did not group
  at all (no prefix was recognised).
- Verified with node: `Corner creasing + Corner dent` → `Corner creasing/dent`;
  `Edge creasing + Edge dent` → `Edge creasing/dent`;
  `water damage to Booklet/Tray` unchanged; `Corner/Edge creasing + surface wear` → both kept.
**Undo:** restore the old `startsWith('corner ')` branch and the `'Corner ' + combinedParts`
assembly.

### 25. Flaw grouping — shared adjective modifiers
**Files:** `app.js` (`groupFlaws`)
- New first grouping pass, `groupAdjectives()`, run before prefix/suffix grouping.
- Recognised modifiers: light, moderate, heavy, minor, major, slight, severe, significant,
  faint, deep, small, large, tiny (case-insensitive).
- Entries sharing a modifier and a compatible trailing context are merged so the adjective
  appears once: `light play` + `light wear to Booklet` → **`light play/wear to Booklet`**.
- Trailing context (`to/through/on <x>`) must match when both entries have one; entries with no
  context merge with ones that do (`light play` + `light wear to Booklet`).
- Different adjectives never merge (`light …` + `moderate …` stay separate).
- Verified via node: `light wear to Booklet` + `light tearing to Booklet` →
  `light wear/tearing to Booklet`; `heavy ring wear` + `heavy scuffing to Cover` →
  `heavy ring wear/scuffing to Cover`; Corner/Edge and `to Booklet/Tray` grouping unchanged.
**Undo:** delete `groupAdjectives()` and set `let result = [...flaws];` again.

### 26. Flaw grouping — unlimited location prefixes (Corner/Edge/Spine …)
**Files:** `app.js` (`groupFlaws` → `splitFlaw`)
- Replaced the two hard-coded `Corner`/`Edge` checks with a `LOCATION_CANON` map:
  `corner(s)` → `Corner`, `edge(s)` → `Edge`, `spine(s)` → `Spine` (case-insensitive, any case
  normalized to the canonical capitalisation).
- Any number of locations sharing the same flaw word now merge in one pass because the suffix
  grouping joins the unique prefixes with `/`:
  `Corner creasing` + `Edge creasing` + `Spine creasing` → **`Corner/Edge/Spine creasing`**
  (4, 5, … items work the same way).
- Add new locations by adding one entry to `LOCATION_CANON`.
- Verified: same-prefix merging (`Corner creasing/dent`), adjective grouping
  (`light play/wear to Booklet`), context grouping (`water damage to Booklet/Tray`) and mixed
  lists all still correct.
**Undo:** restore the previous `/^corners?\s/` + `/^edges?\s/` branches.

### 27. Description text boxes use the same flaw grouping as multiselects
**Files:** `app.js`
- New helpers:
  - `stripLeadingWith(text)` — removes a leading `with ` so free text can group with
    multiselect entries (the sleeve text is already prefixed by the earlier rule).
  - `capitalizeFlawContext(text)` — capitalises the noun after `to`/`through`/`on`
    (`waviness/bending to back` → `… to Back`); articles (a/an/the) are skipped.
- Media Description text is added to `mediaEntries` via `stripLeadingWith` +
  `capitalizeFlawContext`, then grouped with the **media** multiselects only (unchanged pipe).
- Sleeve Description text is added to the sleeve entry list (stripped + capitalised) **before**
  `groupFlaws`, so it now groups with the **sleeve** multiselects:
  `waviness/bending to back` + `waviness/bending to Inlay/Insert` →
  **`with waviness/bending to Back/Inlay/Insert`**.
- Sleeve placement logic simplified to one merged list:
  description present → merged phrase goes in the sleeve-description slot (`with ` re-added);
  otherwise the existing condition / packaging / media-first / format-string rules apply
  exactly as before.
- Example now renders: `… CD with waviness/bending to Back/Inlay/Insert is Out-of-Print …`
- Verified: `light play` + `light wear to Booklet` → `light play/wear to Booklet`;
  media-side grouping and `Corner/Edge/Spine creasing` unchanged.
**Undo:** remove the two helpers, restore `mediaEntries` without transform, and restore the
separate Case A/Case B sleeve block.

### 28. Flaw list separators — ampersand goes before the last item
**Files:** `app.js`
- New `joinFlawItems(items)`:
  - 1 item → `A`
  - 2 items → `A & B` (unchanged)
  - 3+ items → `A / B & C` (and `A / B / C & D` …) — `&` only before the final item.
- Used for both combined phrases: sleeve (description + sleeve multiselects) and media
  (description + media multiselects). Grouping rules run before joining, unchanged.
- Description text keeps its current position (first in its phrase) — confirmed with the user.
**Undo:** restore the `grouped[0] + " & " + grouped.slice(1).join(" / ")` joins.

### 29. Description capitalisation skips "to <word> of …" phrases
**Files:** `app.js` (`capitalizeFlawContext`)
- The noun-capitalisation regex now captures an optional ` of` lookahead: when the word after
  `to/through/on` is followed by ` of`, the phrase is left untouched, because the head word is
  not the noun (`to top of box` stays lowercase, per user's correction).
- Plain cases still capitalise: `to back` → `to Back`; articles (`a/an/the`) still skipped.
- Re-checked the 3-item join with the reported example:
  `large tear to top of box / light play/wear to Booklet & substantial Cellophane tearing`.
**Undo:** remove the `(\s+of\b)?` lookahead group and its early return.

### 30. Production build (2026-10-27)
**Files:** build output `dist/WYSIWYG/`
- Ran `!build.bat` (PyInstaller 6.22.2 in `.venv311`) after today's changes.
- Output: `dist\WYSIWYG\WYSIWYG.exe` (12,133,386 bytes) + `Conditions.json`.
- Verified `set_password.py` / `hash_password.py` are **not** in the build (guard in the batch file).
- `dist\WysiScan\WysiScan.exe` (standalone scanner) was rebuilt earlier today — see entry 19.
**Undo:** n/a (regenerated by the build).

### 31. LP "Sleeve" label gets the same duplicate-word rule
**Files:** `app.js`
- Added `sleeveMentionsSleeve = /\bsleeves?\b/i` against the same `sleeveTextForRules`
  (sleeve description + selected sleeve conditions).
- Vinyl branch: `sleeveTypeLabel = sleeveMentionsSleeve ? "Artwork" : "Sleeve"`.
  So "Sleeve" is not repeated when the description/conditions already say sleeve
  (`worn sleeve` → `Artwork with worn sleeve`); `sleeveless` does not match (`\b`).
- CD (insert) and cassette (Jcard) rules unchanged.
**Undo:** change the Vinyl branch back to `sleeveTypeLabel = "Sleeve";`.

### 32. Favorite flags never ship
**Files:** `conditions.json`, `!build.bat`, `dist/WYSIWYG/Conditions.json`
- Removed all `favorite` keys from the repo `conditions.json` (8 entries; JSON valid, 225 items intact).
- `!build.bat` now sanitises the shipped copy right after copying it: a `.venv311` Python
  one-liner loads `dist\WYSIWYG\Conditions.json`, drops every `favorite` key from all list
  items, and rewrites the file (indent 4, UTF-8) before the build finishes. Build aborts if
  that step fails.
- Applied the same sanitisation to the existing `dist\WYSIWYG\Conditions.json` without a full
  rebuild — verified 0 `favorite` occurrences.
- Note: the app can still add `favorite` flags locally while in use; only the distributed file
  is stripped.
**Undo:** delete the Python line from `!build.bat`.

**Update (same day):** the source `conditions.json` is now sanitised **before every build** too —
the strip runs right after the `.venv311` / `Conditions.json` existence checks at the top of
`!build.bat`, then again on the copied `dist/WYSIWYG/Conditions.json`. Re-sanitised the new
source file (10 keys removed, 225 items valid, 0 favorites) and refreshed the shipped copy.

### 33. Rebuild with installer (2026-10-27 15:15)
**Files:** `dist/WYSIWYG/WYSIWYG.exe`, `dist/INSTALL_WYSIWYG.exe`, `dist/WYSIWYG/INSTALL_WYSIWYG.exe`
- `!build.bat` → `dist\WYSIWYG\WYSIWYG.exe` (12,133,386 bytes, 3:14:58 PM); source and shipped
  `Conditions.json` both verified with 0 `favorite` keys.
- Installer built from `INSTALL_WYSIWYG.spec` with `.venv311`
  → `dist\INSTALL_WYSIWYG.exe` (7,377,339 bytes), copied beside the app build.
- **Known packaging mismatch (pre-existing):** `install.py` copies a fixed file whitelist from
  its own folder (`index.html`, `app.js`, `WalmartSheet/`, `WysiScan/`, …) but the onedir build
  keeps those inside `_internal\`. Running the installer from `dist\WYSIWYG` therefore installs
  an incomplete app. Needs either `_internal` added to `SUB_DIRECTORIES_TO_INSTALL` or a
  copy-everything-except-installer approach — not changed without asking.
**Undo:** n/a (build artifacts).

### 34. Installer build corrected — Inno Setup (`wysiWyg-installer.iss`)
**Files:** `dist_install/INSTALL_WYSIWYG.exe`
- Entry 33's packaging concern only applies to the **legacy** `install.py`; the shipping installer
  is the Inno Setup script `wysiWyg-installer.iss` (version 1.14.3.14, output
  `dist_install\INSTALL_WYSIWYG.exe`).
- Removed the stray PyInstaller `INSTALL_WYSIWYG.exe` copies from `dist\` and `dist\WYSIWYG\`
  (the `.iss` includes `dist\WYSIWYG\*`, so leaving it there would ship a nested copy).
- Built with `ISCC.exe` ("C:\Program Files (x86)\Inno Setup 6\ISCC.exe"):
  **`dist_install\INSTALL_WYSIWYG.exe`** — 480,914,401 bytes, compiled 15:20.
  Sources `dist\WYSIWYG\*` (incl. `_internal`) + loose root files; `Conditions.json` is taken
  from `dist` (already favorite-free). Only warning: pre-existing
  `PrivilegesRequired=admin` vs per-user `userstartup` note.
- This is the file `run_me_Installer.bat` expects.
**Undo:** delete `dist_install/`.

### 35. Version bump to 1.15.3.18
**Files:** `version.json`, `wysiWyg-installer.iss`
- `version.json`: major 1 / minor 15 / patch 3 / build 18.
- `wysiWyg-installer.iss`: `#define MyAppVersion "1.15.3.18"` (used for `AppVersion` and the
  installer's version info).
- The existing `dist\WYSIWYG` / `dist_install` artifacts still carry 1.14.3.14 until the next
  `!build.bat` + ISCC run. `changelog.txt` has no v1.15.3.18 header yet.
**Undo:** restore the previous values (1.14.3.14).

### 36. Frozen scanner fixes — Image Convert availability + Browse dialogs
**Files:** `WysiScan/scanner_server.py`, `main.py`
- `imageconvert_available()` now also checks `<bundle>/WysiScan/imageconvert/app.py`; when the
  scanner runs inside the packaged WYSIWYG app the sub-app lives under `WysiScan\`, so Batch
  Convert / Open GUI no longer report "not bundled".
- `main.py` entry point now handles `--run-script <tmp.py> --run-result <tmp.txt>` before any
  other dispatch. The embedded scanner uses that mode for Browse dialogs; previously
  WYSIWYG.exe ignored the flag, fell through to normal startup and launched a second app
  ("browse buttons reopen the application").
- Standalone `WysiScan.exe` still ships without Image Convert (unchanged design; clear error).
- Rebuilt `dist\WYSIWYG\WYSIWYG.exe` (3:52 PM, 1.15.3.18) and
  `dist_install\INSTALL_WYSIWYG.exe` (3:55 PM, 480,911,468 bytes).
**Undo:** remove the `--run-script` branch and the extra path check.

### 37. Changelog + versioned rebuild (1.15.3.18)
**Files:** `changelog.txt`, `dist/WYSIWYG`, `dist_install/INSTALL_WYSIWYG.exe`
- Added the v1.15.3.18 entry (15 bullets covering today's conditions, description, editor,
  security, heartbeat and WysiScan changes).
- Rebuilt app and Inno installer after the version bump; verified bundled `version.json` =
  1.15.3.18 and shipped `Conditions.json` has 0 favorites.
**Undo:** remove the changelog block; rebuild from the prior version.

### 38. Standalone scanner bundles Image Convert; app keeps using Python modules
**Files:** `WysiScan/scanner_server.py`, `WysiScan/build_scanner.py`,
`WysiScan/dist/WysiScan.exe`
- `scanner_server.py` `__main__` now also handles:
  - `-c <code>` (dialog runner used by the bundled Image Convert app), and
  - `--imageconvert` (runs Image Convert GUI or `--source/--output` batch mode from inside the
    standalone exe).
- `build_scanner.py` bundles Image Convert's runtime files (`app.py`, `config.json`,
  `index.html`, `script.js`, `styles.css`, `assets/css`, `assets/webfonts`) into
  `imageconvert\` inside the exe — deliberately excluding `imageconvert\.venvic` and
  `__pycache__` (the first attempt shipped the dev venv; exe grew to 105 MB).
  Added `--hidden-import=webview/clr/clr_loader` and `--collect-all=webview`.
- Verified on a clean run: `/batch-convert` returns success from the standalone exe (the earlier
  "not bundled" response came from a stale scanner instance still listening on 8010), and
  `-c` dispatch writes its marker file. Rebuilt `dist\WysiScan.exe` = 87,210,107 bytes (4:02 PM).
- **No change needed for WYSIWYG:** it never launches `WysiScan.exe`. Dev mode runs
  `WysiScan\scanner_server.py` with the venv Python; frozen mode re-launches `WYSIWYG.exe
  --wysiscan`, which imports the bundled `WysiScan\scanner_server.py`; Image Convert is launched
  as `WYSIWYG.exe --imageconvert` (bundled Python), and Browse dialogs use the `--run-script`
  handler. The installer does not ship the standalone exe.
**Undo:** remove the two dispatch branches, the Image Convert bundle entries and the webview
flags; rebuild.

### 39. Packaged scanner "doesn't open" — popup-blocker timing fix
**Files:** `app.js`, rebuilt `dist/WYSIWYG` + `dist_install/INSTALL_WYSIWYG.exe`
- Root cause: `runWysiScan()` awaited `/run-wysiscan` before calling `window.open()`. Since that
  endpoint now waits for the packaged scanner to boot (PyInstaller extraction can exceed 5 s),
  Chrome had already expired the user-gesture window and silently blocked the popup. Raw code
  boots in ~1 s, so it worked there — matching "works in raw, nothing opens in the exe".
- `runWysiScan()` now opens the tab/window **synchronously** on click (showing a "Starting
  WysiScan…" placeholder), then navigates it to `http://127.0.0.1:8010/` once `/run-wysiscan`
  succeeds; it closes the placeholder and shows an error if launch fails or the popup is blocked.
- Verified via the installed app: `/run-wysiscan` starts the server and the page loads
  (`GET /`, `/config`, `/get-groups`, `/list-scanners`).
- Rebuilt `dist\WYSIWYG\WYSIWYG.exe` (4:10 PM) and `dist_install\INSTALL_WYSIWYG.exe` (4:13 PM,
  487,159,980 bytes, 1.15.3.18).
**Undo:** restore the previous await-then-open version.

### 40. Flaw grouping — shared leading object ("sticker mark/residue")
**Files:** `app.js` (`groupFlaws`)
- New `groupLeadingObjects()` pass after adjective grouping: simple two-word flaws sharing the
  same first word merge the second word.
  `sticker mark` + `sticker residue` → **`sticker mark/residue`**; hyphens work too
  (`sticker-mark`).
- Only plain `<head> <tail>` pairs participate (no `to/through/on`, no already-merged values),
  so context grouping, location grouping (`Corner/Edge/Spine creasing`) and adjective grouping
  (`light play/wear to Booklet`) are unaffected.
- Verified: example list → `["Corner/Edge/Spine creasing", "sticker mark/residue"]`;
  `paper scuffing to Disc` unchanged.
**Undo:** delete `groupLeadingObjects()` + `splitHeadTail()` and the `result = groupLeadingObjects(result);` line.

### 41. Edit Conditions modal — search with clear + autofocus
**Files:** `index.html`, `app.js`
- Added a search row (`#customOptionsSearch` + ✕ `#clearCustomOptionsSearchBtn`) between the Media
  Type filter and the option list in the Edit Conditions modal.
- `customOptionsSearchTerm` filters the current category/media type by title or text
  (case-insensitive); empty result shows "No matches for this search." while a truly empty
  category keeps the "No options found…" message.
- New `resetCustomOptionsSearchAndFocus()` clears the term, re-renders and focuses the input; it
  runs whenever the modal opens (Edit button and the picker's right-click → Edit List, for both
  Media and Sleeve).
- ✕ clears the filter and refocuses; typing re-renders live.
**Undo:** remove the search row, the term variable, the two listeners and the helper calls.

**Follow-up (same day):** fixed the wrong-row bug the search exposed. The modal list passed
display indexes (already filtered by search and media type) into edit/delete/favourite, which
then re-indexed a differently filtered array — so clicking a row acted on the item below it.
All three actions now pass the **option object** and resolve it by identity
(`indexOf(opt)` / direct mutation), so they always hit the row you clicked. Delete cancels the
in-progress edit only when the deleted object is the one being edited. Verified with
`node --check`.

### 42. Full rebuild (2026-10-27 17:26) — 1.15.3.18
**Files:** `!build.bat`, build outputs
- `!build.bat` now also copies `.env` and `keys.txt` into `dist\WYSIWYG` after building, so the
  portable (un-installed) app can reach Gemini/Discogs without an install.
- Rebuilt everything:
  - `dist\WYSIWYG\WYSIWYG.exe` — 17:22, version 1.15.3.18, shipped Conditions.json 0 favorites,
    `.env` + `keys.txt` present.
  - `WysiScan\dist\WysiScan.exe` — 17:23, 87,209,358 bytes (Image Convert bundled).
  - `dist_install\INSTALL_WYSIWYG.exe` — 17:26, 487,189,876 bytes (Inno Setup, AppVersion
    1.15.3.18).
  - `dist_tools\set_password.exe` — unchanged 11:49 (source unchanged, PyInstaller reported
    up-to-date).
- Changelog head is `### v1.15.3.18 - 2026-10-27`; source `conditions.json` has 0 favorites.
**Undo:** n/a (build artifacts).

### 43. set_password crash on empty/corrupt allpass.json + installer preservation
**Files:** `set_password.py`, `wysiWyg-installer.iss`, rebuilt `dist_tools/set_password.exe`,
`dist_install/INSTALL_WYSIWYG.exe`
- Crash cause: on the other machine `C:\FYRTOOLS\WYSIWYG\allpass.json` exists but is empty/corrupt,
  so `json.load` raised `JSONDecodeError` with a raw traceback.
- `load_allpass()` now:
  - reads with `utf-8-sig` (tolerates a BOM),
  - treats an **empty/whitespace** file as a warning and starts from `{}` (the old file is kept as
    `allpass.json.bak` when saving),
  - on genuinely invalid JSON prints a clear "file looks corrupt, restore it (.bak)" message and
    exits without a traceback.
- Installer no longer ships `set_password.exe` (removed after feedback — it's a private tool).
  Nothing in the `.iss` deletes unknown files, so a copy manually placed in `C:\FYRTOOLS\WYSIWYG`
  survives installs, upgrades and uninstalls (no `InstallDelete`/`UninstallDelete` entries and
  it is not part of the installed file list).
- Rebuilt `set_password.exe` (5:28 PM) and `INSTALL_WYSIWYG.exe` (5:43 PM, 487,189,876 bytes —
  back to the normal size).
**Undo:** remove the `Source: "dist_tools\set_password.exe"` line; restore the old loader.

---

## Notes / gotchas
- Scanner changes need a scanner restart; HTML/JS changes only need Ctrl+F5, but the new
  in-memory HTML cache means `scanner_test.html` edits require restarting the scanner server.
- Main app changes need an app restart (uvicorn runs without reload).
- `WysiScan/UI-COMPACTION-NOTES.md` documents the scanner top-area layout compaction.
