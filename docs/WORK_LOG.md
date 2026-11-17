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

### 44. Chrome extension — context menu aware of Discogs listing pages
**Files:** `ChromeExt/background.js`, `ChromeExt/manifest.json`, `ChromeExt/version.json`,
`Adds/amazon_add_page.html`
- On a Discogs marketplace listing page (`/shop/item/<id>`) the page-level right-click item is
  retitled **"Send to Amazon Add"**; every other Discogs page keeps
  "Send Page to WYSIWYG Scraper". Retitling uses `chrome.contextMenus.update()` driven by
  `tabs.onActivated` / `tabs.onUpdated`, plus a sync on service-worker start and install, so the
  menu follows the active tab instead of guessing.
- Clicking it on a listing page hands the URL to Adds > Amazon, which opens
  `http://127.0.0.1:8008/adds/amazon?url=<encoded>` in its own popup window
  (`chrome.windows.create({type:"popup", width:820, height:860})` — the same shape app.js uses).
  Only an Adds page already inside a popup window is reused; an Adds page sitting in an ordinary
  tab is ignored (reusing it put the page back in a tab). The link is still copied to the clipboard
  as a fallback.
- `amazon_add_page.html` reads `?url=` on `DOMContentLoaded`, fills `#urlInput`, strips the param
  with `history.replaceState` (so a reload does not re-scrape) and auto-scrapes. Clipboard
  auto-paste still runs when there is no param.
- Menu creation is idempotent (`ensureMenus()`), and the Discogs URL patterns are hoisted into
  `DISCOGS_PAGE_PATTERNS`.
**Undo:** restore the two `contextMenus.create` calls under `onInstalled` and the old
`chrome.tabs.create`/`tabs.query` handler; delete the `?url=` block in the page.

### 45. Extension self-update — compare the loaded manifest, not the app
**Files:** `ChromeExt/background.js`
- Old hook compared `version.json` fetched from the extension folder against
  `/api/extension-version`. With the extension loaded off the server share both are the *same file*,
  so it could never fire; and a client running a stale local `WYSIWYG.exe` would reload forever.
- Now: `chrome.runtime.getManifest().version` (what Chrome actually registered) vs `version.json`
  from the extension folder with `cache: "no-store"`. Replacing the files on the share with a higher
  version makes every client reload itself within the 5-minute alarm — no manual reload.
**Undo:** restore `APP_VERSION_URL` / `getInstalledVersion()` and the `Promise.all` comparison.

### 46. Amazon Adds — real always-on-top pin, with remembered state
**Files:** `Adds/amazon_add_page.html`, `main.py`
- The old pin wrapped the page in a fixed `#aapWrap` with `z-index: 2147483647`; it never touched
  the OS window and its wrapper covered the top bar, pin button included, so it could not be undone.
- New `GET/POST /api/window-pin`: finds the window by caption (exact match first, then prefix so
  Chrome's " - Google Chrome" suffix still matches) and calls
  `SetWindowPos(HWND_TOPMOST / HWND_NOTOPMOST)`. `user32` argtypes are declared so 64-bit HWNDs
  survive the call.
- The button stays in place: 📍 = normal, 📌 = pinned (accent background, `aria-pressed`, tooltip).
  `localStorage['wysiwyg_adds_amazon_pin']` records the choice and is re-applied silently on load,
  because the topmost flag dies with the window.
**Undo:** delete the two endpoints and `_win_*` helpers; restore the old `toggleAapPin` and the
`#aapWrap.pinned` CSS.

### 47. Amazon Adds — Jump to section no longer hides the heading
**Files:** `Adds/amazon_add_page.html`
- `.section-title` got `scroll-margin-top: 52px`. `scrollIntoView({block:'start'})` parked the title
  at viewport y=0, i.e. behind the sticky `#aapTopbar` (~44px), so the heading looked skipped.
**Undo:** remove the one property.

### 48. Amazon Adds — catalogue number (Part Number) truncation
**Files:** `Adds/Amazon_add_scraper.py`
- Release 2671258 (`ART CD 002`) returned Part Number `002`. The label parser split the catalogue
  number on whitespace and kept only tokens containing a digit, so `ART` and `CD` were dropped. The
  same split mangled `Html_Label_Display` into
  `Odium Records – ART CD – ART - Odium Records – ART CD – CD - …`, and `Label_List` became
  `['Odium Records – ART CD']`.
- Added `split_cat_numbers()`: a token only starts a new catalogue number when it is
  self-contained (letter prefix like `C108068`/`WARPCD123`, or digit-hyphen-digit like `542-4`) and
  the current number already holds digits. `ART CD 002` and DG-style `2530 123` stay whole;
  `314-526 542-4` still splits.
- The label name now comes from the dash split (`lbl_name`) instead of re-deriving it by stripping
  digit tokens from the pair.
- Verified: 2671258 → Part Number `ART CD 002`, `Html_Label_Display` `Odium Records – ART CD 002`,
  `Label_List` `['Odium Records']`; synthetic checks cover `314-526 542-4`, `2530 123`, `C108068`,
  `WARPCD123`, `BN-LA123-G` and a no-catno label.
**Undo:** restore the two `cat_str.split()` loops and the `lbl_tokens_clean` derivation.

### 49. Walmart Sheet retired (files kept on disk)
**Files:** `index.html`, `app.js`, `main.py`, `wysiWyg-installer.iss`, `!build.bat`
- Walmart changed their upload items page, so the exporter no longer fits anything.
- GUI: removed the drawer button, `runWalmartSheet()`, `clearWalmartCache()`,
  `assembleWalmartDescription()`, `walmartWindow` / `walmartFilteredDesc`, the dock-preference
  restore, the command-palette + hotkey entry (`walmart`, `Ctrl+Shift+B`), the
  `/api/walmart/cache-context` auto-sync pushes and the `wysiwyg_walmart_context` writes.
- `main.py`: dropped the `walmart_router` import, the `/WalmartSheet` static mount and
  `include_router`. This was mandatory — the import is at module level, so the exe would have
  failed to start once `WalmartSheet` stopped being bundled. Also removed the dead
  `WALMART_CONTEXT_CACHE_FILE` constant, two stale "moved to WalmartSheet/walmart.py" comments,
  and the Qt **Tools ▸ Walmart** action + its state-poll JS key.
- Build/installer: dropped `--add-data "walmart.html"` / `--add-data "WalmartSheet"` and the
  `Source: "walmart.html"` line; fixed the `[Subfolders]` comment that claimed the bundle contains
  WalmartSheet.
- `walmart.html`, `walmart.js` and `WalmartSheet/` are **left in place** — the user may want them
  later. Still referencing them: `install.py` (unused), `backup.bat` / `backup_code.py` zip lists,
  `docs/CONVENTIONS.md` (protected-areas list).
**Undo:** `git checkout` the five files, or re-add the entries listed above.

### 50. Amazon Adds — "Hide Empty" filter + Copy All feedback
**Files:** `Adds/amazon_add_page.html`
- New **Hide Empty** check box (`#aapHideEmpty`, `.aap-check` styling) in the top bar. Toggling it runs
  `applyHideEmpty()`, which shows/hides the existing `.field-row` and `.kw-group` nodes with
  `display:none` — deliberately no re-render, so edits typed into the boxes are never lost.
- What counts as empty (`rowIsEmpty`): blank value, `n/a` / `na` / `none` / `null` /
  `*(not found)*` / `need-sku` / `-` / `—`, and any value containing `check box:` (Amazon's
  "This product does not have a Product ID" placeholder). Mirrors the placeholders that
  `Amazon_add_scraper.py` emits.
- **Upload Photos** and **Merchant Shipping Group** are hidden by label (`EMPTY_LABELS`) whatever
  their text says — they only ever carry form instructions ("(uploaded by user)",
  "(select correct weight by user)").
- Section headings whose rows are all hidden are hidden as well, so no orphan headers remain.
- Starts **unchecked** on every load — set explicitly in the `DOMContentLoaded` handler because
  Chrome restores form state on some reloads. Not re-applied while typing, so a row cannot vanish
  mid-edit.
- **Copy All** now skips rows hidden by the filter and, on success, calls `flashCopied(copyAllBtn)`
  (label flips to "Copied" for 1.2 s, same as the per-field Copy buttons). Failures still go to the
  status line ("Copy failed." / "Nothing to copy yet.").
**Undo:** delete the check box + `.aap-check` CSS, `rowIsEmpty` / `applyHideEmpty` and its calls,
the load-time reset block, the two `style.display === 'none'` guards in the Copy All handler, and
the `flashCopied(copyAllBtn)` call.

### 51. Amazon Adds — "Top" jump target + Pull URL from WYSIWYG
**Files:** `Adds/amazon_add_page.html`, `app.js`
- The **Jump to section** list now carries a **Top** entry (in the static markup and re-added by
  `populateSectionNav()` after every render, since that rebuilds `nav.innerHTML`). `onAapSectionNav`
  handles `'top'` before the `parseInt` branch and does `window.scrollTo({top:0, behavior:'smooth'})`.
- New **Pull from WYSIWYG** button on the Adds page grabs whatever URL is sitting in the main app's
  Discogs URL box.
  - `app.js`: `rememberDiscogsUrl()` writes the field into
    `localStorage['wysiwyg_last_discogs_url']` on `input`, and after the click-to-autopaste fills the
    box. A blank value never overwrites a stored URL (so a reload with an empty box keeps the last one).
  - Adds page: reads the key, fills `#urlInput` and scrapes; empty key → "No Discogs URL in WYSIWYG yet."
- Both pages are served from `http://127.0.0.1:8008`, so they share localStorage regardless of which
  host form (127.0.0.1 / localhost) the user came from.
**Undo:** remove the `Top` option + its branch in `onAapSectionNav`, `rememberDiscogsUrl` and its two
call sites in `app.js`, and the `#pullUrlBtn` button + handler.

### 52. WysiScan — "Extract Text From Image(s)" in its own window (+ working pin)
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`, `docs/CONVENTIONS.md`
- Extract Text no longer shows `#cliModal` as an overlay in the scanner page. `openCliModal()`
  validates the 1–8 selected images and **immediately** (no `await` before it, so the click's user
  gesture survives) calls `window.open('/?extract=1&files=[...]', 'WysiScanExtract', ...)`.
- The same page re-loads in **extract mode**: a tiny inline script right after `<body>` adds
  `body.extract-mode` before first paint; CSS hides every body child except `#cliModal` /
  `#toast-container` and stretches the panel to `100vw`/`100vh` (no backdrop, no drag handle, Max
  button hidden).
- Selected file paths travel in the URL (`?files=` JSON) and are kept in `cliFiles`, which
  `submitCliPrompt()` now prefers over the (absent) gallery checkboxes.
- Panel population moved into `loadCliModalContent(files)` so the presets + AI cache load in the new
  window; `initExtractWindow()` also starts its own `/api/heartbeat` (the normal boot is skipped) so
  the server's 120 s no-heartbeat auto-shutdown cannot kill the extract window.
- `closeCliModal()` closes the window in extract mode — Cancel and the × both route through it.
- **Pin**: `toggleCliPin()` no longer toggles an in-page z-index class (`stay-on-top`); it POSTs
  `{title: document.title, topmost}` to the scanner's new `/api/window-pin`, which finds the window
  by caption ("Extract Text From Image(s)", exact then prefix so Chrome's " - Google Chrome" suffix
  matches) and calls `SetWindowPos(HWND_TOPMOST / HWND_NOTOPMOST)`. `initCliPinState()` reads the
  real state on load; failures raise a toast instead of silently doing nothing.
- `scanner_server.py` gained its own `GET/POST /api/window-pin` + ctypes helpers (same contract as
  the app's, duplicated because the scanner also builds and runs standalone).
- `docs/CONVENTIONS.md`: the modal rule no longer points at the deleted `aapWrap`;
  Extract Text and Adds > Amazon are documented as windows, not modals.
- Note: `scanner_test.html` is cached in memory by the server (`_INDEX_HTML_CACHE`) — restart the
  scanner to pick these changes up.
**Undo:** restore the old `openCliModal` (modal display) and `toggleCliPin`
(`stay-on-top` class), drop the extract-mode CSS/inline script/`initExtractWindow`/`cliFiles`, and
delete the two `/api/window-pin` routes + `_win_*` helpers from `scanner_server.py`.

### 53. WysiScan Extract Text — theme switch, prompt order, Save visibility, working Re-Run
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- **Dark/Light button**: new `#cliThemeBtn` in the panel header (hidden unless `body.extract-mode`; the
  scanner page keeps Theme in its own drawer). It calls the existing `toggleTheme()` and then
  `updateCliThemeBtn()` to flip 🌙 Dark / ☀️ Light. The saved theme
  (`localStorage['wysiscan_theme']`) is now applied in the early inline script as well, so the extract
  window does not flash light first — its normal theme init lives in the page boot that it skips.
- **Prompt order**: new `sortPromptNames()` / `renderPromptOptions()` keep every preset in
  prompts.json order with **Custom last**. Used by the initial load *and* the post-save refresh
  (which used to rebuild the list without the "(read only)" suffix).
- **Save only for Custom**: the button got `id="cliSaveBtn"`, and `onCliPromptSelect()` now hides it
  (`display:none`) unless the selection is `Custom` (previously it was merely disabled).
- **Re-Run**: `/run-cli-prompt` returned the cached extraction whenever the file list matched, so
  pressing Re-Run just re-displayed the same output. The client now sends `force: true` when the
  button is in Re-Run state **or** the prompt text changed (the cache key is files-only), and the
  server skips its cache lookup when `force` is set. State lives in `cliResultFromCache` /
  `cliLastPromptSent`.
**Undo:** drop `#cliThemeBtn` + `updateCliThemeBtn()` + the theme restore in the early script;
restore the inline option building instead of `sortPromptNames`/`renderPromptOptions`; remove the
`saveBtn.style.display` line; remove `force` from both the fetch body and the endpoint.

### 54. WysiScan Extract Text — "Band/Artist" label + Discogs marketplace search
**Files:** `WysiScan/prompts.json`, `WysiScan/default_prompt.json`, `WysiScan/scanner_test.html`
- Prompts now show `Band/Artist: AAAA` instead of `Band Name: AAAA` (both the Basic and Custom
  presets in `prompts.json`, plus `default_prompt.json`), so new extractions emit the new label.
  `big_default_prompt.json` was left alone: it is UTF-16 and already invalid JSON, and nothing reads it.
- `renderCliResults()` normalises a rendered label of `Band Name` to `Band/Artist`, so **cached**
  extractions and any AI drift still display the new label.
- New 🔎 **Discogs** button in the panel footer → `searchDiscogsMarketplace()`:
  - **Disabled** (`#cliDiscogsBtn`, greyed + `disabled` + "Run an extraction first" tooltip) until
    `updateCliDiscogsBtn()` sees extracted fields. It is re-evaluated whenever the result box is
    rendered, cleared, or a new run starts.
  - `cliFieldValue()` reads the rendered rows by label, taking the textarea value (so manual edits
    count): Band/Artist, Album Title, Catalog Number (also "Catalogue Number", "Cat#", "Catalog #").
  - First attempt used `/sell/list?artist=&release_title=&catno=`, which opened an **unfiltered**
    Discogs page: Discogs moved the marketplace page to `/shop/list` and its search box takes a single
    free-text `q` (the per-field filters are internal IDs, so name-based params are ignored).
    It now folds every extracted identifier into one query —
    `?q=<Band/Artist Album Title Catalog# UPC/Barcode>` — omitting whatever is missing.
  - Results page is **`/sell/list`** (the marketplace the user prefers for picking a release to list
    against), not the redesigned `/shop/list`.
  - `cliDiscogsFields()` is the single source for that query, and `updateCliDiscogsBtn()` uses it, so
    a UPC-only extraction also enables the button. UPC labels accepted: `UPC`, `UPC/GTIN`,
    `Barcode`, `Barcode (Scanned)`, `Barcode (Text)`, `EAN`, `GTIN`.
  - Opens in the named tab `DiscogsMarketplaceSearch`, so repeated searches reuse one tab.
**Undo:** restore `Band Name: AAAA` in the two prompt files (and the "separate the band name"
sentence); remove the label-normalisation line, `cliFieldValue`, `searchDiscogsMarketplace`,
`updateCliDiscogsBtn` and the button.

### 55. Extension — hand focus to the app tab after "Send to WYSIWYG Scraper"
**Files:** `ChromeExt/background.js`, `ChromeExt/manifest.json`, `ChromeExt/version.json`
- When the app runs in a **browser tab** (`http://127.0.0.1:8008`), sending a URL to the scraper used to
  leave the user on the Discogs page while the scrape happened in the background.
- The successful `/api/extension-scrape` path now calls `focusAppTab()`, which activates the app tab and
  focuses its window. Desktop-mode installs need nothing: `main.py`'s scrape bridge already does
  `showNormal()/activateWindow()/raise_()` on the app window.
- New `findAppTab()` prefers the **main page** (`/`, `/index.html`, `/#…`, `/?…`) over other 8008 tabs,
  because Adds pages live on the same host — previously the fallback injection path could have picked
  the Adds window. Both `focusAppTab()` and the injection fallback use it now.
- Extension version 1.6 (self-reload via `version.json`).
**Undo:** drop the `focusAppTab()` call in the `.then()` and replace `findAppTab()` with the old inline
`chrome.tabs.query` + `tabs[0]` in both places.

### 56. App — Reset All runs before every scrape
**Files:** `app.js`
- Every scrape (manual Scrape click, Enter in the URL box, the SSE bridge, and the Chrome
  extension clicking `#scrapeBtn`) fires a `submit` on `form[hx-post="/scrape"]`.
- New interceptor on **document, capture phase**, so it runs before htmx's own handler:
  `preventDefault()` + `stopPropagation()`, `await fullReset()`, put the URL back, then
  `form.requestSubmit()` with a guard flag so the re-submit passes through untouched.
- Why the URL dance: `fullReset()` clears `input[type="url"]`, which includes `#discogsUrlInput` —
  without restoring it the re-submit would scrape an empty box.
- Why capture phase: htmx attaches its own listener to the element, and element-phase listeners run
  in registration order; a capture listener on an ancestor is guaranteed to fire first, so the
  request cannot go out before the reset finishes.
- Net effect: menus, condition pickers, SKU and description boxes are blank (and profile/conditions
  reloaded) before the response is applied, so a previous item can never bleed into the new scrape.
**Undo:** delete the `scrapeForm` block (the `document.addEventListener('submit', …)` interceptor) in
`setupEventListeners()`.

### 57. Build & installer — WysiChat ships with WYSIWYG, XDevHubX refs removed
**Files:** `!build.bat`, `wysiWyg-installer.iss`
- `!build.bat` now runs three steps: clean, build WYSIWYG, **build WysiChat**. The chat step runs
  PyInstaller (`--onefile --windowed --name "Wysichat"`, icon + `fyrlogo.png` / `fyrlogo_alert.png`)
  from inside `WysiChat\`, using the chat's own `.venv` when present (FreeSimpleGUI / cryptography
  live there), else `.venv311`, else `python` from PATH.
- The chat's `dist` folder also holds live `chat_history_*.db` / `user_prefs_*.json`, so the build
  deletes **only** `WysiChat\dist\Wysichat.exe` (plus `WysiChat\build`) — never the folder. Deleting
  the old exe first also stops the "did the build produce an exe?" check from passing on a stale
  binary. A running `Wysichat.exe` fails the build with a clear message.
- `wysiWyg-installer.iss` ships **only** `WysiChat\dist\Wysichat.exe` to `C:\FYRTOOLS\WysiChat` —
  the same folder the standalone WysiChat installer uses (it spells it `C:\FYRtOOLS`; Windows paths
  are case-insensitive, so it is the same directory). Adds a `{autoprograms}\WysiChat` shortcut, a
  Defender exclusion for that folder, and `taskkill /IM Wysichat.exe` before install and uninstall so
  an open chat cannot lock the exe.
- Both images (`fyrlogo.png`, `fyrlogo_alert.png`) are baked into the exe via `--add-data`, so no
  loose copies are installed. `main.py` used to read `fyrlogo_alert.png` from the exe folder
  (`alert_icon_path = os.path.join(script_dir, ...)`) — it now uses `resource_path()` like the window
  icon, and `create_alert_icon()` no longer crashes if it has to write into a read-only `_MEIPASS`.
- Net effect: install/upgrade replaces the exe and nothing else; uninstall removes only the exe.
  Chat history, preferences and logs next to it are never touched.
- Removed the leftover `XDevHubX.exe` kills everywhere: the installer's pre-install batch and
  uninstall step, `main.py`'s self-update batch, and `kill_wysiwyg.bat` / `run_me_Installer.bat`
  (those helpers now kill WYSIWYG, WysiScan and WysiChat).
- WysiChat tray menu: the "Wysiscanner" entry is now **"WysiScan"** (label + event handler match), and
  it launches the standalone `C:\FYRTOOLS\WysiScan\WysiScan.exe` (dev-script fallback unchanged).
- The main app still uses its **bundled** scanner (`sys.executable --wysiscan`); it never launches
  `WysiScan.exe`. That exe exists purely for external tools like WysiChat.
- Icon fix found by the first real build: `WysiChat\!build.bat`, `WysiChat\Wysichat.spec` and
  `WysiChat\wysichat_installer.iss` all pointed at `fyr-logo.ico`, which does not exist (git only has
  `fyrlogo.ico`, `fyr-logo_2.ico`, `wysichat-logo.ico`). PyInstaller died at "Copying icon to EXE"
  and left a 283 KB stub exe behind. All three references (plus the root `!build.bat`) now use
  `wysichat-logo.ico`, which is byte-identical to `fyr-logo_2.ico`.
- Standalone scanner rebuilt by hand (the root `!build.bat` does not cover it): old
  `WysiScan\dist\WysiScan.exe` + `WysiScan\build` deleted, then
  `.venv311\python.exe -m PyInstaller --noconfirm --clean WysiScan.spec` (83.2 MB). `WysiScan\dist`
  also holds runtime `scans/` and `temp/` folders, so only the exe and the build dir were removed.
- **Known gap in that rebuild:** `pytesseract` is not installed in `.venv311` (or `.venv`), so the new
  exe omits it — `warn-WysiScan.txt` says "missing module named pytesseract". The 28 Oct exe had it
  bundled. OCR paths (`/ocr-and-lookup`, CD matrix orientation) still fail gracefully, and Tesseract
  itself is not installed on this machine, so nothing observable changes here; `pip install
  pytesseract` into `.venv311` + rebuild restores parity if it is ever needed.
- `WysiChat\!build.bat` and `WysiChat\wysichat_installer.iss` are untouched and still work on their
  own (including the `Z:` sync in the chat's own build script).
**Undo:** delete the `[3/3]` block in `!build.bat` (restore the `[1/2]` / `[2/2]` labels), remove the
WysiChat `Source:` / `[Icons]` / Defender-exclusion / taskkill lines from the `.iss`.

### 58. HTML tab / Amazon HTML — no "Track Count", tracks always listed
**Files:** `html_format.py`, `Adds/Amazon_add_scraper.py`
- The scraper's raw text carries a `Track Count: N` line (it feeds `#trackTimeInfo`, which the
  description text turns into "with N Tracks"). `format_discogs_to_html()` treated every `Key: value`
  line as metadata, so the HTML tab's output contained `<b>Track Count:</b>&nbsp;4`. That line is now
  skipped — it is bookkeeping, not listing data. The raw text is untouched, so the description text
  still says "with N Tracks".
- Also fixed while verifying: `main.py` emits the header as `Tracklist:` (with colon) but
  `html_format` only stripped an exact `tracklist`, so a stray `Tracklist:` line appeared at the top of
  the tracklist body. The check is now `startswith("tracklist")`.
- **Amazon Adds** `generate_html_block()`:
  - Skips any `Track Count:` line (it never appeared in the output, but now it cannot).
  - Tracklist start detection now understands CD positions: previously only `A1`-style or `1.`-style
    lines started the list, so a Discogs API tracklist (`1 Title`, no dot) left the
    `HTML Product Description` tracklist **empty**. It now also matches `^\d+\s`, and the `Tracklist:`
    header is recognised (tracks start on the next line, so the header never renders as a track).
- Verified live (release 2671258): app HTML → `1 - Lilitu Aria - 1:20 …` with no Track Count and no
  stray header; Amazon HTML → `1 - Lilitu Aria<br>2 - The Serpents Throne …`. Synthetic A1 / `1.` /
  `1 ` positions all list correctly, and a raw text containing `Track Count: 2` leaks into neither.
**Undo:** remove the `track count` skip and the `startswith("tracklist")` change in `html_format.py`;
restore `elif re.match(r'([A-Z]\d+|\d+\.)', line):` in `generate_html_block()` and drop its
`track count` / `tracklist` branches.

### 59. Details/HTML tab — scratchpad removed, code box matches preview height
**Files:** `index.html`, `app.js`, `main.py`
- Removed the whole **MANUAL INPUT / SCRATCHPAD** block: its label, the Copy All / Select All / Paste
  buttons and the `#manualInputBox` textarea.
- `app.js`: dropped the three listeners (`copyScratchpadBtn`, `selectAllScratchpadBtn`,
  `pasteToScratchpadBtn`) plus the now-unused `copyScratchpad()` and `pasteToManualInput()`, and the
  `manualInputBox` line in `resetScraperTab()`.
- `index.html`: `htmlGenBtn`'s `hx-vals` no longer falls back to `manualInputBox` — it sends
  `#scraperResultText` directly.
- `main.py`: the scrape response no longer mirrors the raw text into `manualInputBox` (that element is
  gone). `parsePastedData(rawText)` still runs, so the builder tab and `#trackTimeInfo` still fill.
- **Height**: no CSS change needed. `.details-grid` is a fixed 600px grid and `.details-box` /
  `.details-box-textarea` are `flex: 1`, so with the second box gone the HTML CODE textarea fills the
  column exactly like the LIVE PREVIEW box does (`.preview-column` header + `flex: 1` `.preview-box`).
- Verified that the description still ends with "with N Tracks": `assembleDescription()` extracted
  from `app.js` and run with the example inputs returns
  `Used Like New Limited Edition Numbered 2004 Canadian Import CD is Out-of-Print with 4 Tracks - Autistiartili Records Autist015`
  (and drops the phrase when `trackTime` is empty). Only the HTML *output* lost the Track Count line;
  the raw text still carries it for `#trackTimeInfo`.
**Undo:** restore the scratchpad `.details-box` markup, the three listeners + two functions, the
`manualInputBox` lines in `main.py` / `resetScraperTab()`, and the `hx-vals` fallback.

### 60. Description — "Gatefold" gains its noun ("Gatefold Sleeve") in both slots
**Files:** `app.js` (`assembleDescription`, `processFormatData`)
- Two separate paths were dropping the word "Sleeve":
  1. **Sleeve condition** selected (multiselect Gatefold) with the sleeve description box empty — the
     value sits in the condition slot, so the sentence read `... USA LP Vinyl Gatefold with light
     Cellophane tearing ...`. Fixed in `assembleDescription()`:
     ```js
     let sleeveCondText = inputs.sleeveCond;
     if (fmtData.conditionPhrase && /gatefold/i.test(sleeveCondText || '')) {
         sleeveCondText = String(sleeveCondText).replace(/gatefold(?!\s*sleeve)/ig, 'Gatefold Sleeve');
     }
     ```
     `fmtData.conditionPhrase` is only set when the sleeve description is **blank**, so the
     description-present path stays byte-for-byte identical.
  2. **Sleeve packaging** = Gatefold with sleeve multiselect flaws and no description — the flaws get
     appended to the packaging (`sleevePkg += " with " + combined`) and the old rule
     `if (sleevePkg … includes('gatefold') && sleeveDesc)` required a sleeve description, so the same
     word went missing. Now the noun is added only when something else sleeve-related follows:
     ```js
     const sleeveHasContent = hasSleeveCondition || hasSleeveDesc || sleeveEntriesAll.length > 0;
     if (sleevePkg && sleeveHasContent && /gatefold/i.test(sleevePkg)) {
         sleevePkg = sleevePkg.replace(/gatefold(?!\s*sleeve)/ig, 'Gatefold Sleeve');
     }
     ```
     So a bare Gatefold stays `... LP Vinyl Gatefold is Out-of-Print ...`, while a condition, a sleeve
     description or a sleeve flaw makes it `Very Good Gatefold Sleeve with Corner creasing`.
- Both replacements use a `(?!\s*sleeve)` lookahead, so an existing "Gatefold Sleeve" is never doubled.
- Verified by running the real `processFormatData()` + `assembleDescription()` (extracted from
  `app.js`):
  - packaging Gatefold only → `... USA LP Vinyl Gatefold is Out-of-Print ...` (no noun, per the
    "nothing else sleeve-related" rule);
  - packaging Gatefold + condition "Very Good" + "Corner creasing" →
    `... USA LP Vinyl Very Good Gatefold Sleeve with Corner creasing ...`;
  - packaging Gatefold + sleeve flaw (no condition) → `Gatefold Sleeve with light Corner wear`;
  - packaging Gatefold + sleeve description → `Gatefold Sleeve with light Cellophane tearing`;
  - already "Gatefold Sleeve" → not doubled, Digipak untouched, no-packaging case unchanged.
**Undo:** delete the `sleeveCondText` block (use `inputs.sleeveCond`) and restore
`if (sleevePkg && sleevePkg.toLowerCase().includes('gatefold') && sleeveDesc)`.

### 61. WysiScan — Image Adjust panel (brightness, contrast, saturation, hue, tint)
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- New `#adjust-ui` panel stacked **below Tilt Correction** (both now live in a new `#left-controls`
  column, so the left rail keeps its width) and styled like the tilt panel.
- Five sliders with live value read-outs, previewing **client-side** on `#originalImg` ("Last Scan
  (Original)"): `filter: brightness() contrast() saturate() hue-rotate()` plus an inline SVG
  `feComponentTransfer` filter (`#adjTintFilter` — R and B intercept +v, G −v) for tint, because plain
  CSS filters have no tint primitive.
- **Apply** → `POST /adjust-image` `{path, brightness, contrast, saturation, hue, tint}`, for **both
  copies**: the original you preview on and the "Last Scan (Cropped)" output (skipped when they are the
  same path). The server writes a one-time `<sanitized>.pristine` copy into `TEMP_DIR`, pushes a normal
  undo backup, applies the maths with numpy/OpenCV (contrast around mid-grey, brightness ±1.28 per
  step, HSV saturation + hue, tint lifts R/B and drops G), overwrites the file and returns a
  cache-busted URL. Sliders then reset to 0.
- **Reset** zeroes the sliders only (clears the preview, no server call).
- **Reset All** → `POST /adjust-image-reset` for both paths, restoring each pristine copy (creating an
  undo backup first), so it always returns to the untouched scans.
- `adjustTargetPaths()` is the single source of the two paths; thumbnails are refreshed through the
  existing `refreshImageElements(path, url)`.
- Sliders are cleared when a new scan arrives (`handleScanSuccess`) and when a different item is
  restored, so a preview can never leak onto the next image.
- Verified the maths standalone: brightness ±50 on mid-grey → 192 / 64, contrast pivot unchanged,
  saturation −100 → greyscale, tint ±60 → magenta / green, hue +120 red → green, extremes clamp
  (no wraparound).
- `*.pristine` snapshots live in the scanner TEMP dir and are deliberately not swept by the `.bak`
  cleanup (they must survive for Reset All); one per adjusted image.
**Undo:** remove the `#adjust-ui` panel + `#left-controls` wrapper, the SVG filter, the five JS
functions (`adjustCssFilter`, `resetImageAdjustSliders`, `applyImageAdjust`, `resetImageAdjustAll`,
`adjValue`) and the server helpers/endpoints (`get_pristine_path`, `_adjusted_image`,
`/adjust-image`, `/adjust-image-reset`).

### 62. WysiScan — left-rail button colours matched to the rest of the app
**Files:** `WysiScan/scanner_test.html`
- **Apply** (Tilt Correction and Image Adjust) now use the Save button's green — `background-color:
  #28a745` with no colour override, exactly like the Save buttons in the cropped preview row, so the
  text inherits `--btn-text` just as it does there.
- **Reset** (both panels) and **Reset All** use the Full / Open blue: `background: var(--btn-bg); color:
  var(--btn-text)`.
- **Auto-Align** uses the Extract Text purple: `background-color: #6f42c1; color: #fff`.
- All six keep their existing padding/size/flex; the border moved from the hard-coded `#333`/`#444` to
  `1px solid var(--accent-color)`, which is what the reference buttons use from the generic `button`
  rule.
- **Compaction (same day):** the visible panel headings ("📐 Tilt Correction" / "🎛️ Image Adjust") are
  removed, buttons use 2-3px vertical padding, the tilt number box 2px, panel padding 15px → 10px, panel
  gaps 10/8px → 4/3px and `#left-controls` gap 20px → 12px. Sliders are restyled to a 10px control (3px
  track, 10px thumb via `::-webkit-slider-*`) and each slider's name/value now share **one line**
  (`.adj-head` + `.adj-val`) instead of stacking two. The left rail no longer needs scrolling.
**Undo:** restore the previous inline styles (`#000`/`#333`/`#222` backgrounds with `#333`/`#444`
borders) on those six buttons, re-add the two heading divs, restore the stacked label/value markup and
revert the padding/gap/slider CSS.

### 63. Install helpers — source-scanner kill, local browser windows closed
**Files:** `kill_wysiwyg.bat`, `run_me_Installer.bat`, `close_local_chrome.ps1` (new)
- Both batch helpers now kill **WYSIWYG / WysiScan / WysiChat** *and* a WysiScan started from source
  (`python.exe …\scanner_server.py`). `/IM` cannot target that one without also killing the main app's
  Python process, so a PowerShell `Get-CimInstance Win32_Process` filter on the command line stops only
  the scanner PIDs (launcher + child). Verified: the same filter matches `UberPaste.py` processes, and
  never the main app.
- New `close_local_chrome.ps1`: enumerates top-level windows, matches captions starting with
  `WYSIWYG`, `WysiScan` or `Extract Text From Image(s)`, requires the owner process to be a browser
  (chrome / msedge / brave / chromium / vivaldi) and posts `WM_CLOSE` — so the local app windows are
  gone before the installer runs. `-ListOnly` prints what it would close (verified against a live
  "WYSIWYG · Adds · Amazon - Google Chrome" window).
- Chrome exposes no external per-tab close, so this closes the whole window showing that page — the
  caveat is documented in the script header.
- `run_me_Installer.bat` skips the browser step if the `.ps1` is not next to it (prints a note).
- `timeout /t` replaced with `ping -n … 127.0.0.1` — `timeout` fails with "Input redirection is not
  supported" when there is no interactive console (task scheduler / wrappers).
**Undo:** delete `close_local_chrome.ps1`, remove the `if exist … close_local_chrome.ps1` block and the
python-scanner PowerShell line from both batches, and restore `timeout /t`.

**Dev helper (same day):** `kill-wysiwyg.ps1` + the `!powershell .kill-wysiwyg.ps1.bat` wrapper close
everything needed *between edits*: `WYSIWYG.exe` / `WysiScan.exe` / `Wysichat.exe`, a **source-run**
scanner (`*scanner_server.py*`) **and a source-run app** (`*main.py*`, matched on the command line so
`UberPaste.py` survives), plus **whatever owns ports 8008/8010** as a safety net (an elevated process
can hide its `CommandLine`, so a name/command-line filter silently misses it — the port owner cannot
hide). Stop failures are printed instead of swallowed. Switches: `-WhatIf` (list only), `-Quiet`.
**Browser windows are not touched** by the dev helper or `kill_wysiwyg.bat` (closing a Chrome window
takes the user's other tabs with it) — that step lives only in `run_me_Installer.bat` via
`close_local_chrome.ps1`.
- `kill_wysiwyg.bat` got the same port-owner sweep and now prints a **WARNING** when a port is still
  held (instead of claiming success), suggesting running it as administrator.
- **A leftover console window after running the killers is not an app window.** The main app prints
  PySide/Qt warnings and the scanner child (launched with `CREATE_NEW_PROCESS_GROUP`, i.e. *sharing* the
  parent console) prints its `Auto-cropping` lines into the same window; its title is the default
  `C:\WINDOWS\system32\cmd.exe`. That is the shell the app was started from, so killing the app cannot
  close it. Launch via `pythonw main.py` or a shortcut if no console is wanted.

### 64. WysiScan — Crop Mode radio labels renamed
**Files:** `WysiScan/scanner_test.html`
- The three placeholder radio labels are now meaningful: **Custom1 → "CD Matrix"**, **Custom2 →
  "CD/45 Front"**, **Custom3 → "Custom One"**. Their `value`s stay `cd` / `tape` / `lp`, because all the
  logic (`handleCropModeChange`, `paddingByMode`, the scan/import `media_type` payloads) keys off the
  value, never the label — so nothing else changed. No references to the old label text existed anywhere
  in `WysiScan`.
**Undo:** change the three labels back to Custom1 / Custom2 / Custom3.

### 65. WysiScan — "CD/45 Front" straightens its text (AI orientation + local levelling)
**Files:** `WysiScan/scanner_server.py`
- When Crop Mode is **CD/45 Front** (`media_type == 'tape'`), a scan or import now straightens the
  artwork before cropping, in two stages:
  1. **Orientation (0/90/180/270)** — one small Gemini call (`_ai_upright_degrees`), because no local
     heuristic can tell upright from upside-down. The image is downscaled to ≤900px, written to
     `TEMP_DIR`, sent with a one-line prompt ("reply with ONLY 0/90/180/270, the clockwise rotation to
     apply"), then deleted. Fails soft: no key / no answer ⇒ no rotation, everything else still runs.
  2. **Levelling (skew)** — local, no network: `_detect_text_skew` rotates candidate angles
     (±10° in 1° steps, then ±1° in 0.25° steps) and keeps the angle whose horizontal ink projection
     has the sharpest text rows (`_text_line_score` = normalised variance of row sums, rejected when
     ink coverage is <1% or >55%). Sub-0.5° corrections are ignored so a clean scan is never
     re-encoded for nothing. *(Superseded for wide angles — see "Third live attempt" below; this sweep
     is now the narrow fallback.)*
- Applied rotations use `_rotate_with_background` (same math as `/deskew-image`, corners filled with the
  image's background colour) and `create_backup()` first, so **Undo still works**.
- Other modes are untouched: Auto/LP keep the existing `perform_auto_deskew`, `cd` still gets none.
- The scan response carries a `message` ("Straightened 90deg + levelled 1.2deg") when it did something,
  and "Already upright." is treated as nothing to report.
- Verified: synthetic artwork rotated ±3/6.5/9° is levelled to within 0.25°; upright vs 90° scores
  4.39 vs 1.71; a 4° scan is corrected and its score improves (4.77); an already-straight image is left
  untouched. Live AI check on synthetic covers returned **0 / 90 / 180** correctly (3 small calls).
- **Guard for disc faces:** levelling only applies when the winning angle beats the "leave as is" score
  by ≥10%. A CD label face has radially arranged text with no horizontal rows, and this stops a
  marginal noise win from rotating an already-good scan — verified: a synthetic label face rotated
  0/4/−7/15° is left alone, while ordinary text still corrects within 0.25°.
- **First live scan exposed two bugs (fixed same day):**
  1. `gemini_pool` could not be imported inside the scanner process (`No module named 'gemini_pool'` in
     `wysiscan_debug.log`) — the scanner is spawned separately and does not inherit the app's sys.path,
     so the AI stage silently never ran. `_ai_upright_degrees()` now bootstraps
     `sys.path.insert(0, dirname(dirname(__file__)))` like the other AI endpoints do.
  2. With no orientation, the levelling latched onto a wrong optimum at the **edge of the search range**
     (logged "levelled 11.0deg", i.e. ±10 plus the fine pass) on a booklet-type scan and rotated a good
     image. Edge-of-range winners are now rejected outright, and a busy non-text image never rotates.
- Verified after the fix: normal text still levels to within 0.25°; busy non-text images rotated
  0/5/12° stay at 0.00; the failing real case (booklet-like, AI unavailable) now reports
  "Already upright." instead of spinning; `_ai_upright_degrees()` imports and answers again.
- **Second live attempt ("Failed to fetch" / scanner appeared to die):** reproduced on the saved scan
  (`C:\New Scans\8163\ScanGroup_6.jpg`, 1240×1753) — the code does **not** crash and correctly answers
  **90°** for that image. The real problem was **latency**: `gemini_pool` fails over across models/keys
  and its `timeout` is *per attempt*, so the call took **44 s** (combo#0 and #1 each timed out, then a
  key was dropped as forbidden, then a good combo answered). A scan request hanging that long looks like
  a crash and leaves the page's `fetch` with `TypeError: Failed to fetch`.
  - AI attempts are now capped at **6 s each** and the whole orientation step at **25 s wall clock**
    (worker thread + `future.result(timeout=…)`, the worker is abandoned harmlessly on timeout).
  - Answers are cached per file (path + mtime + size), so a re-scan of the same file is instant.
  - `straighten_front_image()` never raises now (AI and levelling are each wrapped), and both call sites
    wrap it too — a straighten failure can never take a scan or import down.
  - Added progress logging: "straightening <file> (WxH)", "asking AI for orientation (preview)", "AI
    replied in Ns", plus the existing result lines — so a slow/failed run is visible in
    `wysiscan_debug.log` instead of looking like a dead scanner.
  - Measured after tuning: **16.6 s** end-to-end on that scan, rotating 90° correctly.
- **Third live attempt: the label text sits at 33°, and the ±10° sweep refused it.** On
  `C:\New Scans\8163\ScanGroup_1.jpg` the AI answered 90° correctly, but the printed label was another
  **33° off** and the log said `skew hit the search edge (10.8 deg) - ignoring it`, so the crop came out
  with the text still on a slant. Ground truth for that scan is **+34.0°**, measured independently by
  isolating the glyph pixels (they are far darker than the label's dotted screen) and finding the
  rotation that collapses them into rows.
- **Why simply widening the sweep to ±45° was rejected.** It was implemented and tested, and it fails
  its own regression harness: the row-projection score changes with how much white fill the rotation
  adds, so on the same clean text page 12° was reported as 10.75°, 20° as 4°, and 33° as 0° — while
  abstract artwork and a radial-label face produced bogus 30–43° answers. Shipping that would have
  rotated good discs for no reason, which is worse than the original bug.
- **What levelling does now** (`_word_like_blobs` → `_text_axis_consensus` → `_mask_row_sharpness`):
  1. Binarise (Otsu), then keep **word-shaped blobs**: elongated (aspect ≥ 2.2, ≥ 20 px long) and not
     solid (`contourArea / rect area` between 0.12 and 0.70 — a word is mostly gaps between glyphs at
     ~0.5, a printed block or photo highlight is ~0.8+ and is what fooled an earlier version on abstract
     artwork). Each blob's long axis is its text angle, so the method is **rotation-invariant**: no
     sweep, and 33° is measured as easily as 3°.
  2. Take the **consensus**: ≥ 4 blobs, ≥ 60% within 3° of a common angle. Radial/curved label text
     points every which way and photo texture scatters, so both fail the majority and are left alone.
  3. **Refine on the agreeing blobs only** (±2° in 0.25°) so artwork and label screens cannot drag the
     angle.
  4. **Ambiguity guards:** the measurement runs at 1400 px and again at 800 px (a full bed has no word
     blobs at 800); if both answer and differ by more than 3°, the geometry is ambiguous and the scan is
     left alone. More than 45° with an AI answer is refused (the perpendicular reading is equally
     likely), and without an AI answer anything over 15° is refused — that is where a line cannot be
     told from the same line upside down.
  5. The old ±10° projection sweep is kept as `_detect_skew_from_projection` for when the blobs give no
     consensus, so small leans behave exactly as before.
- **Verified against real data and synthetic cases:** the failing scan now gives **+34.1°** end-to-end
  (truth +34.0) and the final crop measures a residual of **+0.00**; synthetic text rotated ±1.5…44° is
  measured to within 0.5° at 15 of 17 angles, the other two (exactly 12° and −44°) are refused because
  the two scales disagree — "leave it alone" rather than guess; abstract artwork and a radial-label face
  at 0/5/12/25/33° are left alone in 32 of 35 cases (the 3 exceptions are the legacy fallback, unchanged
  behaviour); real booklet scans give no consensus; an already-level crop is left **byte-identical**
  (0 pixels changed). Cost: 0.1–0.3 s, no network, no new AI calls.
- **End-to-end on the failing scan:** AI 90° + levelled 34.1° (total −55.93), auto-crop back to
  736×734, residual 0.00 — the disc is centred, upright and level.
**Undo:** delete `_front_small`, `_text_line_score`, `_rotate_with_background`, `_ai_upright_degrees`,
`_detect_text_skew`, `straighten_front_image`, the two `media_type == 'tape'` branches and the
`straighten_note` lines. (The 33° work adds `_word_like_blobs`, `_text_axis_consensus`,
`_mask_row_sharpness`, `_detect_skew_from_words` and `_detect_skew_from_projection`.)

---

### 66. WysiScan — Image Adjust presets (Default applies itself), Save button removed
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- **Default preset applies to every scan.** A scanner that reads everything too dark needed the same
  brightness sliders on every scan. `apply_default_adjustments()` runs right after auto-crop in
  `/trigger-scan` and `/import-file` (and after `/recrop`, so "Adjust Pad" cannot quietly undo it), and
  bakes the stored `default` values in. It does nothing when the preset is all zeros, records what it
  applied so **Remove All** can take it off again, and never raises — a failure logs and the scan
  continues. *(Originally this kept a pristine copy for a full restore; entry 69 replaced that.)*
- **Three presets, all editable, all auto-saving:** `default`, `custom1`, `custom2` in
  `config.json` → `adjust_presets` (`{brightness, contrast, saturation, hue, tint}` each). The page
  posts to `/adjust-preset` 400 ms after a slider stops moving; there is no Save button, by design.
  Only `default` is applied automatically — the two customs are loaded into the sliders on demand and
  baked only when Apply is pressed.
- **Sliders load showing the user's Default**, so what every scan gets is visible on open. They zero
  after a scan or an Apply (the values are already in the image), and zeroing does not overwrite the
  stored preset with zeros.
- **Double-apply guard:** pressing Apply while the sliders still hold untouched Default values now says
  "Default values are already applied to scans." instead of brightening a second time.
- **Save button removed** under the cropped image (it copied the crop into the Save Location, which the
  scan already does). Full and Open now share that row. `saveCurrentCropped()` had no other caller and
  went with it.
- Verified: with no preset the scan is untouched (mean unchanged); a Default of brightness +40 lifts a
  synthetic dark scan 60 → 111; customs stay independent of Default; clearing Default stops it applying;
  an unknown preset name falls back to Default and drops foreign keys. `config.json` was restored
  byte-for-byte after the test. Page JS extracted and checked with `node --check` (clean).
- **Not baked into the raw original:** defaults go on the cropped output only, matching the existing
  rule that the raw scan stays raw (the same reason deskew/straighten skip `temp_path`).

- **Button labels are the user's — do not "fix" them.** They renamed the Image Adjust buttons themselves:
  `Reset` is now **Boost** (still zeroes the sliders, image untouched) and `↺ Reset All` is now
  **↺ Remove All**. The `onclick` handlers were left alone. The point of Boost is their workflow: clear
  the sliders after a pass so a *further* amount can be applied on top of an already-adjusted scan
  (sliding again and pressing Apply stacks, it does not replace). They were offered a one-click "apply
  the same values again on top" and declined, so the behaviour stays as described. Any later tidy-up must
  keep these words; the tooltips still describe the old behaviour on purpose.
  *(Remove All stopped restoring the whole scan in entry 69 — it now removes only colour.)*

**Undo:** remove the `.adj-presets` block and CSS, the preset JS block, the `ADJ_PRESETS`/`ADJUST_KEYS`
constants, `_adjust_presets`, `save_adjust_preset`, `apply_default_adjustments`, the
`/adjust-preset` route and its three call sites; restore the Save button and `saveCurrentCropped()`.

---

### 67. WysiScan — tilt is absolute, 1°/10° steps, applies on click
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- The tilt was **relative and needed Apply**: `adjustTilt()` nudged a pending number, `applyTilt()` posted
  it to `/deskew-image`, which rotated whatever was on disk. Click `<` three times and you got 3° on top
  of 3° on top of 3° — three JPEG re-encodes and a drifting canvas.
- Now the angle is **absolute, measured from the untouched scan**, and each click applies immediately:
  `<` / `>` ±1°, `<<` / `>>` ±10°, the number box shows the current angle and typing in it applies too,
  Reset returns the file to the base. The Apply button is gone.
- **New `/tilt-image`** keeps a "tilt base" copy of the pixels per file (`TEMP_DIR/<path>.tiltbase`) and
  always restores that before rotating, so 1, 2, 3, 4° all rotate the same pixels exactly once — no
  compounding loss, no drifting bounds. `_rotate_file_by` holds the rotate/re-crop maths, shared with
  `/deskew-image` (which is unchanged and still used by auto-deskew paths).
- **One backup per tilt session**, taken when the base is created, so a single Undo returns the pre-tilt
  scan instead of one undo per click.
- **Other edits are not thrown away.** The base is only trusted while the file's mtime matches what the
  tilt wrote; if anything else changed the file (crop, brightness, 90° rotate, undo), the next tilt
  rebuilds the base from what is on disk. The page also resets the displayed angle to 0 whenever an image
  refreshes for a non-tilt reason (`refreshImageElements(..., keepTilt)`), so the number never claims an
  angle the scan does not have.
- Requests are chained, so fast clicking cannot interleave restore/rotate pairs; setting the same angle
  twice is byte-identical (absolute, idempotent).
- **Hold to repeat.** All four buttons repeat while held: the first step is immediate, then `<`/`>` add
  1° every 110 ms and `<<`/`>>` add 10° every 180 ms. This is press-and-hold, not click-and-wait, and
  releasing outside the button (or switching window) stops it via `pointerup`/`pointercancel`/`blur`
  listeners. Keyboard activation still steps once — the click handler ignores pointer-generated clicks
  (`event.detail > 0`) that `pointerdown` has already handled.
- **Requests coalesce instead of queueing.** One tilt request is in flight at a time; while it runs only
  the newest angle is remembered, and the worker re-sends if the number moved. Holding a button therefore
  cannot pile up dozens of restores/rotations — it converges on wherever the display got to.
- Hotkeys: Left/Right arrows now move the absolute angle by 1° and apply (were 0.1° nudges that only took
  effect on key release); the Apply-Tilt key applies whatever is in the box.
- Verified against the endpoint directly: 1° then 2° gives 2° from the base (not 3); re-setting 2° is
  byte-identical; one backup for five clicks; Reset restores the original bytes exactly and removes the
  base; an external edit made between tilts survives the next tilt (marker pixels intact); the cropped
  path (`skip_crop=false`) returns success and a URL; Reset on a never-tilted file is a true no-op; a
  missing path returns a clean "File not found". Page JS passes `node --check`.

**Undo:** delete `/tilt-image`, `_TILT_STATE`, `_tilt_base_path`, `_tilt_base_is_current`,
`_rotate_file_by`; restore the old `applyTilt()` (post to `/deskew-image`), the relative `adjustTilt()`,
the Apply button and the 5° buttons.

---

### 68. WysiScan — image quality: stop OpenCV throwing away colour on every save
**Files:** `WysiScan/scanner_server.py`
- The user reported scans looking softer than before. It was real, and mostly pre-existing: every step
  writes the JPEG back with `cv2.imwrite(path, img)`, and OpenCV's default is quality 95 **with 4:2:0
  chroma subsampling**. Measured on a real 6 MB scan: **28.04 dB PSNR** for one save, with a
  saturation-plane error of 11.7; the same quality in **4:4:4 gives 41.64 dB** and a saturation error of
  2.1. Repeated saves compound it: 26.11 dB after two, 25.33 after three, 25.02 after four.
- New scans hit more of these writes than they used to (auto-crop → straighten → Default adjustments →
  tilt), which is why it became noticeable now.
- **Fix:** a single `_imwrite_image(path, img)` helper writing **quality 97 in 4:4:4**, used by every
  scan write — `auto_crop_image`, rotate, deskew, straighten, `adjust-image`, the Default adjustments,
  `recrop`, manual crop and the tilt staging file. Only the tiny AI orientation preview still uses a
  plain `imwrite`. Non-JPEG paths (PNG) are untouched and stay lossless.
- **Measured after the change:** 44.34 dB from one generation and 44.24 dB after four (generations
  barely compound any more). Full crop → adjust → tilt on the same real scan: **21.67 dB → 39.96 dB**
  against an ideal in-memory version. File size 249 KB → 637 KB for the crop, i.e. ~2.5x, which buys
  back the colour detail.
- **Rule for later:** never `cv2.imwrite` a scan directly; call `_imwrite_image`. The imgwrite default is
  a silent 13 dB of colour loss.
- Not done (bigger change, only if it ever matters): keeping a lossless PNG master per scan and writing
  JPEG only on export.

**Undo:** delete `JPEG_SAVE_PARAMS` and `_imwrite_image`, and put the plain `cv2.imwrite` calls back.

---

### 69. WysiScan — "Remove All" removes colour only, not rotation/tilt
**Files:** `WysiScan/scanner_server.py`, `WysiScan/scanner_test.html`
- Reported: pressing **Remove All** after tilting un-rotated the scan. It restored a `pristine` snapshot
  taken before the colour was applied, and any tilt/rotation made after that snapshot went with it.
- **Now it takes the colour back off in place.** Every adjustment is recorded per file
  (`_ADJUST_HISTORY`, oldest first) by `/adjust-image` and by the Default preset at scan time;
  Remove All replays `_unadjust_image()` over the current pixels in reverse order — tint, then
  saturation/hue, then brightness, then contrast — so tilt, 90° rotations, crop and pad are untouched.
- **Accuracy:** removal is essentially exact where nothing was clipped — 45–48 dB on realistic
  brightness/contrast/saturation/hue/tint combinations, and 40.7 dB inside the artwork when a tilt sits
  between the adjustment and the removal (mean 89.2 vs 90.1, 95th-percentile error 5 levels). Pixels that
  were blown out to pure white by a bright adjustment cannot come back; that information was destroyed
  when it was applied. The white margins a rotation fills in can shift by ~13 levels for the same reason —
  they are outside the scan and the cropped output trims them.
- **History is dropped when the pixels are replaced** (new scan, import, recrop, revert-crop, undo, redo,
  file delete) so a stale record can never darken a scan twice. Pressing Remove All again reports
  "No colour adjustments to remove" instead of doing anything.
- `get_pristine_path` and the `.pristine` snapshots are gone: nothing restores a whole scan any more, and
  leaving the function behind would have implied otherwise.
- The button label ("↺ Remove All") and its behaviour on the page (keep-tilt refresh) are unchanged;
  only the toast/title text now says what it does.

**Undo:** delete `_unadjust_image`, `_ADJUST_HISTORY`, `_remember_adjustment`, `_forget_adjustments` and
the `_forget_adjustments` call sites; put the pristine snapshot + restore back in `/adjust-image`,
`/adjust-image-reset` and `apply_default_adjustments`.

---

### 70. WysiScan — tilt direction, no rim clipping, slider/preview rules, Reset Default
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- **Tilt buttons now move the picture the intuitive way:** `>` / `>>` turn it to the **right**
  (clockwise), `<` / `<<` to the left. The page keeps its own sign (positive = right, so the box reads
  `+1.0`) and negates only when posting, because OpenCV's positive angle is counter-clockwise —
  verified with a marker blob: OpenCV +10° moved it left/up, −10° right/up.
- **Rotating no longer shaves the rim off, and the frame holds still.** Two attempts are worth recording:
  1. First fix was a content box (`_content_bbox`, "everything that differs from the border colour"
     + 1.5% margin). Verified fine on a *loose* crop, but **wrong on a real one**: a CD crop is tight
     enough that the disc runs off all four edges (corner pixels are disc pixels), so there is no
     background to measure against. The box then jumped on every rotation - reported as "the image is
     wobbling all around the white square", "auto crop is not cropping properly", "the last scan shrinks
     with each rotation". `_content_bbox` was deleted.
  2. **What ships:** `_rotate_file_by(..., keep_frame=…)` rotates on the expanded canvas and then crops
     straight back to the **original canvas size, centred**. A disc is unchanged by rotation, so the
     framing is byte-for-byte stable at every angle: 756×737 tight crop at +5/+14/+30° stays 756×737
     with **zero** dark pixels on the rim, and clicking 1,2,3,4,5° in turn never drifts or shrinks.
     The page passes `media_type`; **tape/cd keep the frame**, lp/auto keep the wider canvas (a
     rectangular sleeve would lose its corners otherwise - its picture gets smaller as the angle grows,
     which is the honest trade for not clipping).
- **Apply keeps the slider values** (they are what is now in the picture) and **Remove All zeroes them**.
  Because the sliders no longer reset after Apply, pressing Apply again stacks another helping — which is
  the behaviour wanted for "make it brighter than that".
- **The preview now shows only what is not already in the pixels.** `adjustApplied` records what has been
  baked in (Default preset at scan time, then each Apply; cleared by Remove All), and the CSS filter shows
  the *difference*. All sliders at zero means "change nothing", so the filter is cleared rather than
  showing a negative of the applied values.
- **New "Reset Default" link** under the preset radios: puts the Default preset back to 0 (so new scans
  are left exactly as the scanner made them) and, when Default is the selected preset, zeroes the sliders
  with it. Saved through the same `/adjust-preset` call — no extra endpoint.
- Verified: absolute/idempotent/reset-exact tilt behaviour intact on the real crop, no rim clipping at
  −34/−12/+7/+24°, 24 concurrent tilt requests with zero errors, no temp-file strays; page JS passes
  `node --check`.

**Undo:** swap the `angle: -angle` back to `angle: angle`; restore the `auto_crop_image` re-crop in
`_rotate_file_by` and delete `_content_bbox`; put `resetImageAdjustSliders()` back after Apply, remove
`adjustApplied`/`setAdjustApplied` and the zero-slider early return in `adjustCssFilter`, and delete the
Reset Default button, its CSS and `resetDefaultPreset()`.

---

### 71. WysiScan — tilt touches only the cropped scan, and re-crops it from itself
**Files:** `WysiScan/scanner_test.html`, `WysiScan/scanner_server.py`
- **"Last Scan (Original)" is no longer rotated.** The page used to tilt both copies; now only
  `lastCroppedPath` is sent to `/tilt-image`, so the raw scan stays exactly as the scanner produced it.
- **The cropped image is re-cropped from itself after every rotation** (this replaces entry 70's fixed
  frame). The user's report was that padding drifted after any rotation and only "Adjust Pad" put it
  right — but that rebuilds from the original bed scan, which throws away the tilt.
  - `_rotate_file_by` now rotates onto a canvas expanded by the rotation **plus a 4% background
    margin** (so the object never touches the edge and is findable), then crops that picture.
  - **Discs (tape/cd)** are cropped by a **circle fit** (`_disc_crop`: background-difference mask →
    `minEnclosingCircle` → square of `2r + 2×padding`, centred on the disc). Same crop at every angle by
    construction: **746–747 px square from 1° to 30° and at −12°, always square, zero dark pixels on the
    rim**. A 1 px spread, versus 735–759 with the contour crop.
  - **LP / Auto** go through the normal `auto_crop_image` on the rotated picture (which is safe now that
    the margin exists), so rectangular artwork is not clipped either.
  - Guard rails: an implausible circle fit (radius or side out of range) falls back to the contour crop,
    and `auto_crop_image` is given a separate temp path because it raises `SameFileError` when told to
    write over its own input and finds no contours.
- Verified: `+1…+30°`, `−12°` — square, no rim ink, padding identical; Reset restores the pre-tilt file
  **byte for byte**; LP mode at 14° re-crops from the rotated image with no clipping; the page JS passes
  `node --check`.

**Undo:** send both paths again in `applyTilt`, restore `keep_frame` cropping in `_rotate_file_by` and
delete `_disc_crop`.

---

### 72. WysiScan — "Remove All" restores the real colour-free pixels
**Files:** `WysiScan/scanner_server.py`, `WysiScan/scanner_test.html`
- Reported: Remove All did not put the image back to its proper state. It undid the maths
  (`_unadjust_image`), which **cannot** bring back highlights that a bright adjustment clipped to
  white — after brightness +40 the bright areas come back grey, so the picture looked wrong.
- **Now it restores the actual pixels.** `_plain_snapshot()` copies the file to
  `TEMP_DIR/<path>.plain` immediately before the **first** adjustment lands (both the Default preset at
  scan time and every Apply), recording the generation counter and the tilt angle at that moment.
  Remove All swaps that copy back:
  - **Colour only, no geometry change → byte-identical to the pre-colour file** (verified by SHA).
  - **Colour then tilt → the tilt is replayed** and, when the colour predates the tilt, using the
    **crop window stored by the tilt itself** (`_TILT_STATE[key]["crop_rect"]`), so the framing matches
    exactly: 727×727 before and after, byte-identical to rotating the colour-free pixels by the same
    angle with the same window.
- **Geometry is tracked so the snapshot is only trusted when it still lines up.** `_geometry_changed()`
  is called by `rotate-image`, `rotate-image-fine`, `deskew-image`, `auto-deskew`, `manual-crop` and
  `manual-crop-replace`; `_plain_forget()` by `recrop`, `revert-crop`, `undo`, `redo`, scan, import and
  file delete (those replace the pixels outright). If the counter no longer matches, Remove All falls
  back to the old undo-the-maths path so the colour still comes off.
- `_disc_crop` now returns `(crop, (x, y, side))` and `_rotate_file_by` accepts/returns a `crop_rect`,
  which is what makes the replay framing exact.
- Verified: byte-identical after one Apply and after two stacked Applies; colour-then-tilt keeps the
  tilt with identical framing and the colour gone; a geometry edit in between still strips the colour
  via the fallback; a new Apply after Remove All takes a fresh snapshot.

**Undo:** delete `_plain_path`, `_plain_snapshot`, `_plain_forget`, `_geometry_changed`,
`_PLAIN_STATE`, `_PLAIN_GENERATION` and their call sites; restore the snapshot/restore in
`adjust_image_reset` to the maths-only version.

---

### 73. Box sets — a fourth "Box Sleeve Condition" column (structure only)
**Files:** `Conditions.json`, `app.js`, `index.html`, `editor.html`
- Box sets need their own sleeve-condition list, separate from LP/CD/Cassette. Nothing is filled in yet —
  this is the wiring so the list can be populated later and the selections behave like the other sleeve
  conditions.
- **Data:** `Conditions.json` gained a **`boxSleeve`** array (empty). It round-trips through the same
  `/api/conditions` → `/api/save-conditions` path as the rest, and `merge-conditions` already merges by
  key so it survives a server merge. `Conditions.json` was rewritten with the app's own formatting
  (`json.dump(..., indent=4)`, the same call `main.py` uses) — the diff is only the user's pending edits
  plus the new key.
- **Sleeve (All Types) picker:** a fourth column, header **BOX SLEEVE CONDITION**, reading
  `customOptionsData.boxSleeve`. Selections are held in a new hidden `<select id="boxSleeveOptions">`
  (like `lpOptions`/`cdOptions`/`customOptions`) and are distributed by
  `syncConditionMultiselectsToLegacy`, so toggling, Clear, Done and favouriting all work the same way.
  The box options are added to `sleeveConditionOptions` with `data-media-type="boxSleeve"` and are
  **always hidden** in the normal per-type multiselect (LP/CD/Cassette views are unchanged).
- **Description:** `customOptionsSelected` now also collects `boxSleeveOptions`, so once the category is
  filled, selected box conditions flow into the description like any other sleeve condition. With the
  list empty this changes nothing today.
- **editor.html:** the conditions editor gained a **Box Sleeve Conditions** section (add/edit/delete,
  search, save) exactly like the other three, and the four sections now wrap instead of squeezing
  (`flex-wrap: wrap`), since the row used to be three wide.
- **Not touched:** the in-app "Edit Conditions" modal (`customOptionsModal`) still offers Media/Sleeve for
  LP/CD/Cassette only — editing the box list is done in editor.html, as asked. The All-Types picker rows
  still only expose the favourite menu, which is unchanged.
- Verified: `node --check` on `app.js`, and on the extracted scripts of `index.html` and `editor.html`;
  `Conditions.json` parses and still has every original key (`lp` 60, `cd` 79, `cassette` 47, `media` 1,
  `mediaCondition` 63, plus `boxSleeve` 0).

**Undo:** remove the `boxSleeve` key from `Conditions.json`; in `app.js` drop it from
`customOptionsData`, `renderCustomOptionsSelect`, `renderConditionMultiselects`,
`syncConditionMultiselectsToLegacy`, the All-Types `mediaTypes` list, `unfavoriteAllCurrentType` and
`customOptionsSelected`; remove `#boxSleeveOptions` from `index.html`; remove the Box Sleeve section from
`editor.html`.

---

### 74. Box sets — the sleeve list switches to Box Set conditions
**Files:** `app.js`
- A scrape that puts **Box Set** into Sleeve Packaging now switches the **Sleeve Condition** list: it
  shows `customOptionsData.boxSleeve` and hides LP/CD/Cassette. The LP/CD/Cassette lists come back the
  moment Box Set is deselected.
- `isBoxSetSelected()` reads the Sleeve Packaging multiselect and matches `/box\s*set/i` on any selected
  value (so "Box Set" and "Boxset" both count); `effectiveSleeveType()` returns `boxSleeve` or the
  current media type, and `renderConditionMultiselects()` now filters visibility on that instead of the
  media type alone.
- Triggers: the scrape fill (`renderConditionMultiselects()` after the packaging values are selected),
  the Sleeve Packaging select's own `change`, the packaging list picker's **Done / Close / Clear**
  handlers, and `fullReset()` (so Reset All goes back to the media-type list). The
  **Open Sleeve (Current Type)** button and its context-menu entry both open the Box Set list while Box
  Set is selected; the picker header reads "BOXSET SLEEVE CONDITION".
- Favouriting a selection in the multiselect now resolves each row's own `data-media-type` instead of
  assuming the current media type, so it works for whichever sleeve list is showing.
- Nothing is destroyed by the switch: hidden LP/CD/Cassette selections stay selected (they are cleared by
  Reset All before the next scrape anyway).
- Verified: `node --check app.js`. Not verified in the browser — the user tests.

**Undo:** remove `isBoxSetSelected`/`effectiveSleeveType`, restore
`option.hidden = type !== currentConditionMediaType`, drop the `renderConditionMultiselects()` calls from
the scrape fill, the packaging `change` listener, the list-picker handlers and `fullReset`, and pass
`currentConditionMediaType` back to `openConditionPickerForSleeve` at the two call sites.

---

### 75. Box sets — "Both" view and the Edit Conditions list
**Files:** `app.js`, `index.html`
- **Both view (dual column picker):** the *media* column now takes its type from the on-screen
  **Media Type** dropdown (`#conditionMediaType`) rather than whatever type the caller passed — it no
  longer drifts back to a default. The *sleeve* column uses `effectiveSleeveType()`, so with Box Set
  selected it lists the Box Sleeve conditions and its header reads **BOXSET SLEEVE CONDITION** instead
  of "CD/LP/CASSETTE SLEEVE CONDITION". Toggling a row and the row's favourite menu both use that same
  type.
- **Edit Conditions modal (right-click > Edit List):** **Box Set** was added to both its Media Type
  pull-downs (`#modalMediaTypeSelect` filter and `#newOptionMediaType` for new entries), so
  `customOptionsData.boxSleeve` can be listed, added to, edited, favourited and deleted exactly like the
  other sleeve lists.
  - While Box Set is selected the modal forces the category to **Sleeve Condition** and hides the
    "Media Condition" category (there are no box media conditions).
  - Rows tag themselves `[BOX SET]` instead of `[BOXSLEEVE]`.
  - Opening the modal auto-selects the effective sleeve type, and the right-click **Edit List** entry
    from the sleeve multiselect opens straight onto Box Set when one is selected. The plain **Edit**
    button clears that sticky choice so it follows the form again.
- Verified: `node --check app.js` and the extracted script from `index.html`. Browser behaviour is the
  user's to test.

**Undo:** in `openDualColumnConditionPicker` use `mediaType` for the sleeve column again; remove the two
`boxSleeve` `<option>`s from `index.html`; remove the category-forcing block, the `[BOX SET]` label map,
the `effectiveSleeveType()` calls in the modal and the `userChanged` reset on the Edit button.

- **First live hold killed the scanner — heap corruption, not a Python error.** `wysiscan_debug.log`
  shows ~10 tilt requests a second (`Tilt: ScanGroup_9.jpg set to +77…+87 deg`, alternating with
  `temp_ScanGroup_9.jpg`), and the Windows event log records `pythonw.exe` faulting in `ntdll.dll`,
  exception `0xc0000374` (`STATUS_HEAP_CORRUPTION`), at the moment the log stops. Cause: the page sent a
  request for every repeat tick (two files each), and every request rewrote the same file the browser
  was simultaneously re-fetching — simultaneous native decodes/writes on one file.
  - **Client throttles:** a tap still applies immediately, but a held button refreshes the image at most
    every **400 ms**, plus once more after the number stops moving. One request in flight at a time; the
    pump re-sends only if the angle moved while it was busy.
  - **Server serialises:** `_TILT_LOCK` means two tilt writes can never run at once.
  - **Writes are atomic:** the result is built in a temp file and swapped in with `os.replace`, so the
    browser never reads a half-written JPEG (it re-fetches the image after every tilt).
  - **Half the I/O:** the old code copied the 6 MB base over the file and then read it back; it now reads
    the base and writes the destination directly. Measured **3 ms/request** on a small test image where
    the old path copied every time.
- **Re-verified after the crash fix:** absolute (1 then 2 = 2°), idempotent, one backup per session, Reset
  restores the original bytes exactly, no stray `.tmp`/`.rot` files left behind, and **24 concurrent
  requests from 8 threads** complete with zero errors, the file still decodes, and a reset afterwards is
  byte-exact.

### 76. WysiChat — selectable tray bubble size
**Files:** `WysiChat/main.py`
- The bubble rendered the artwork at whatever size PIL produced, which after the icon work landed at 22 px and
  read as a dot. Size is now a setting: **Small 48 / Medium 72 (default) / Large 96 / Extra Large 128 px**,
  chosen from the bubble's own right-click menu (**Bubble Size**) or the main window's **File → Bubble Size**,
  and remembered as `-TRAY-ICON-SIZE-` in the app's user settings.
- `apply_bubble_size()` re-renders both the normal and the alert artwork, saves the choice, then closes and
  rebuilds the tiny always-on-top window in place (screen position kept) and re-shows it.
- A saved value from an older build snaps to the nearest new size, so upgrading never leaves the old 22/32 px
  bubble behind.
- Verified: `ast.parse`, plus `load_tray_icon_bytes()` renders 48×36 / 72×55 / 96×73 / 128×97 (aspect kept).

### 77. Main app — plain click toggles condition multiselects
**Files:** `app.js`
- A `<select multiple>` normally needs Ctrl+click; the condition lists are tick lists now.
- `enableClickToggle(select)` intercepts `mousedown`, cancels the browser's selection reset, flips
  `option.selected` and fires `change` (so the legacy sync still runs); the following `click` is neutralised so
  it cannot undo the toggle.
- Delegated on the `<select>` itself, so it survives `renderConditionMultiselects()` rebuilding the options
  (media-type change, load, Box Set switch). Right-click is untouched, so favourites still work.

### 78. Main app — ✕ clear buttons, matching size, media-condition favouriting
**Files:** `index.html`, `app.js`, `styles.css`
- **✕ beside each 📂:** `.condition-clear-btn` clears only its own list — Media empties
  `#mediaConditionOptions`; Sleeve empties `#sleeveConditionOptions` and pushes the empty result back through
  `syncConditionMultiselectsToLegacy()`, so no stale sleeve flaw survives in the description.
- **Same box as the folder:** both buttons share the tiny-icon rule
  (`.list-picker-open-btn, .condition-open-btn, .condition-clear-btn` — 22×16 px, `inline-flex` centred). The
  folder already had that rule further down the sheet, which is why the pair rendered mismatched at first. Only
  the glyph size differs (✕ 13 px) because a text ✕ reads smaller than the 📂 emoji.
- **Favouriting a media condition did nothing:** the handler resolved the array from the row's
  `data-media-type` (`cd`/`lp`/`cassette`), i.e. it searched the *sleeve* lists. It now branches — media
  conditions match `customOptionsData.mediaCondition` on title + text + `media_type`; sleeve conditions keep
  using the row's own type, so Box Set still works.
- Verified: `node --check` on `app.js` and on the scripts extracted from `index.html`; CSS brace balance checked.

### 79. WysiScan — Autoscan tick persists
**Files:** `WysiScan/scanner_test.html`
- Same pattern as Auto Delete Original: `config.auto_scan` restores `#autoScanCheckbox` on load, and each change
  posts `{ auto_scan }` to `/update-config`, which saves it in the scanner's `config.json`. Per-install, so it
  travels with that copy of the scanner.
- Needs a scanner restart (the page HTML is held in `_INDEX_HTML_CACHE`).

### 80. WysiScan — "Remove All" keeps the selected preset's values
**Files:** `WysiScan/scanner_test.html`
- ✕ (Remove All) still restores the untouched pixels (rotation / tilt / crop kept), but it no longer zeroes the
  sliders: it re-loads the selected radio's preset via `selectAdjustPreset(adjustPresetName)`, then marks those
  same values as already baked in with `setAdjustApplied(presetValues)`.
- Net effect: the sliders always show what the selected preset holds (the Default values stay visible instead of
  reading as zeros), and because the sliders equal "already applied" every delta is zero, so the preview stays
  the plain scan — nothing is re-applied on top of it.
- Fresh scans already behaved this way (`selectAdjustPreset('default')` + `setAdjustApplied(default)` when a scan
  lands). The gallery/restore path still zeroes the sliders on purpose, because a restored item's colour state is
  unknown.
- Verified: extract-and-`node --check` of the page's script blocks.

### 81. WysiScan — editable value boxes + Reset Default / Zero Out buttons
**Files:** `WysiScan/scanner_test.html`
- Each adjustment value (`adjBrightnessVal` … `adjTintVal`) is now an `<input type="number">` instead of a
  `<span>`: it can be typed into, and it has the native up/down spinner arrows (Chromium shows them on hover /
  focus). Ranges match the sliders — ±100 except Hue at ±180.
- `wireAdjustValueBoxes()` keeps the pair in step: typing or spinning the box moves its slider (which clamps to
  the slider's min/max) and re-previews; blur / Enter snaps the text to what the slider accepted. A cleared or
  half-typed box (`""`, `"-"`) is left alone rather than being forced to 0 mid-edit.
- `adjustCssFilter()` writes the slider value back as `out.value` and skips the box while it has focus, so the
  keyboard cursor is never yanked out from under the user.
- **The old underlined "Reset Default" text link is a proper button now**, sitting in a two-up row with the new
  **Zero Out**: `resetDefaultPreset()` still always targets the Default slot, while `zeroOutAdjustPreset()` zeroes
  *whichever radio is selected* and stores that in its slot. Both clear the pending auto-save timer first, so the
  zeroing is what gets written, and both toast a confirmation.
- Verified: extract-and-`node --check` of the page scripts; CSS brace balance.
- To test: restart the scanner (`_INDEX_HTML_CACHE` holds the page).

### 82. WysiScan — tighter preset buttons, narrower value boxes, docked Menu button
**Files:** `WysiScan/scanner_test.html`
- **Reset Default / Zero Out:** 10 px bold → **8 px normal**, height **13 px** (`line-height: 11px`, 3 px side padding,
  `white-space: nowrap` + ellipsis). They now sit on one line instead of wrapping to two.
- **Value boxes:** text aligned **left** instead of right, font 11 → 10 px and width 52 → **40 px** — enough for
  `-100` plus the spinner arrows, and no wider.
- **Menu button is docked, not scrolled:** `.menu-btn` is now `position: fixed; top: 8px; left: 8px; z-index: 900`,
  which parks it in the empty gutter to the left of the centred 1200 px `.container` and keeps it in exactly the
  same spot whatever the page scroll is. `.app-topbar` keeps `min-height: 26px` so taking the button out of flow
  does not pull the layout up. z-index 900 keeps it under the modals (1000/1001/2000) and under the drawer
  (9990/9991), which are all higher.
- The gutter only exists when the window is wider than the 1200 px content column (the container is centred);
  below that the button overlaps the container's empty top row, which is harmless.
- Verified: extract-and-`node --check` of the page scripts; CSS brace balance.

### 83. WysiScan — right-click rename for the Crop Mode radios
**Files:** `WysiScan/scanner_test.html`
- The visible name of each Crop Mode radio is now a `<span class="crop-mode-name" data-mode="…">`, so the wording can
  change without touching the `value` that drives processing and `padding_by_mode`.
- **Right-click a radio that is selected** (not Auto) → a small Rename Crop Mode modal. It opens with the current name
  preselected; Enter or **Rename** applies it, Escape/Cancel/✕ cancels, and an empty name is refused (it would leave an
  unlabelled option).
- The three names are saved as `crop_mode_names` (`{cd, tape, lp}`) through `/update-config` and re-applied on load, next
  to `auto_scan` and `auto_delete_original`. Defaults live in `CROP_MODE_DEFAULT_NAMES`, so a missing or partial config
  falls back to Auto / CD Matrix / CD/45 Front / Custom One.
- Auto has no `contextmenu` listener at all, and right-clicking an unselected radio does nothing (that is what "when
  they are selected" means here).
- **Hot Keys also closes the menu:** `openHelpModal()` calls `closeWysiScanDrawer()` first, so the drawer and its overlay
  are gone before the Hot Keys window appears instead of sitting behind it.
- Verified: extract-and-`node --check` of the page scripts.

### 84. WysiScan — the AI pass is gone from CD/45 Front
**Files:** `WysiScan/scanner_server.py`
- Removed outright: `_orientation_cache_key`, `_AI_ORIENT_CACHE`, `_ai_upright_degrees` and
  `_ai_upright_degrees_call` (103 lines). No Gemini call, no worker thread, no 25 s budget, no temp preview file.
- `straighten_front_image()` is levelling only: `_detect_text_skew(img)` → rotate by the found skew, backup first, and
  "Already level." when the skew is under 0.5°. The call-site sentinel that checks for that message was updated to match.
- `_detect_text_skew()` lost `base_cv_angle` / `orientation_known` (nothing else called it) and is back to the
  conservative **15°** limit, i.e. exactly the old no-AI path: word-blob consensus, two scales must agree within 3°,
  projection sweep as the fallback, otherwise the scan is left alone.
- Consequence, by design: a scan that comes off the bed quarter-turned is **no longer turned upright** — it is only
  levelled. A wrong 90° turn was worse than a sideways scan, and the AI almost never got it right.
- **Extract Text is untouched** — the two `gemini_pool.gemini_generate(...)` endpoints and `_scanner_cfg_keys()` are
  unchanged; `git diff` hunks are confined to the CD/45 Front section plus the one sentinel line.
- Verified: `ast.parse` of `scanner_server.py`.

### 85. WysiScan — Adjust Pad aligns first
**Files:** `WysiScan/scanner_test.html`
- `recropLast()` (the **Adjust Pad** button) now runs `/auto-deskew` on the original before it re-crops, because the crop
  is taken from that file - padding a tilted scan just bakes the tilt into the new crop.
- The align fetch was hoisted into `deskewFile(path, padding)`, shared with `autoDeskew()` (Auto-Align), which now returns
  the server's message (`"Already aligned."`, `"Aligned."`, …) instead of a bare true/false.
- Tilt is only reset when the image was really replaced: `"Already aligned."` leaves the pixels alone, so the tilt baked
  into them keeps its on-screen value. Auto-Align still always resets it, as before.
- The "Crop" button (`recropLast(true)`, back to the original) is untouched — it is not a padding change.
- An align failure only toasts; the padding step still runs.
- Adjust Pad's tooltip now reads "Auto-align the scan, then apply the new padding".
- Verified: extract-and-`node --check` of the page scripts.

### 86. WysiScan Extract Text — Discogs search scope, barcode box, clean UPC
**Files:** `WysiScan/scanner_test.html`
- **Right-click the Discogs button** for a small menu: *Cat# + Artist/Title*, *UPC + Artist/Title*, *Both (Cat# + UPC)*
  (the current choice is ticked). Kept in `discogsSearchParts`, saved as `discogs_search_parts` through
  `/update-config`, and applied from `/config` by `initDiscogsUi()`. A blank click elsewhere closes the menu; it flips
  above the button when there is no room below.
- **Every identifier is always trimmed off the query when the mode excludes it** — `discogsQueryText()` builds
  `[artist, title] + chosen parts`, so "Cat#" searches without the barcode and vice versa. Artist/Title are always
  included; the mode only decides which numbers narrow the result.
- **UPC is normalised before it is searched:** `cliNormBarcode()` drops everything that is not a letter or digit
  (`"0 08817 00414 3"` → `008817004143`, hyphens and stray whitespace too) and upper-cases it. This was the reported
  bug — the spaced form was being sent to `?q=` verbatim. Verified with a throwaway Node harness against
  space/hyphen/padded/empty inputs and all three modes.
- **New "Barcode (no spaces)" text box** under the Extracted Text panel, read-only, showing exactly what a search will
  use. It refreshes from `updateCliDiscogsBtn()` (every render) and on `input` in `#cliResultBox`, so hand-editing an
  extracted field updates it immediately.
- `body.extract-mode`'s "hide everything except the panel" rule had to learn about `#discogsSearchMenu`, otherwise the
  menu would have been `display: none !important` in the extract window.
- Verified: extract-and-`node --check`, CSS brace balance, plus the barcode/query test harness above.

### 87. Main app — HTML tab now mirrors the Discogs release page
**Files:** `main.py` (`scrape_url` route)
- The Format line is built from Discogs' own `formats` payload, in Discogs' order: name, then `descriptions`, then
  `text` (split on `,` / `/`), first occurrence wins, **"Album" dropped**. For release 5610215 that is
  `Vinyl, LP, Compilation, Limited Edition, Pink Marbled` — exactly what the page shows. Verified against the live API
  payload *and* with an offline harness over 2xLP / CD / CD+DVD / repeated-block / multi-colour cases.
- The two duplicates came from the old formatter, not the payload: `found_space_tags` was appended twice (once as the
  full list, once as "everything except Out-of-Print"), which is where `Compilation Compilation` came from, and the
  Vinyl block re-added the colour word (`Pink`) that was already inside `text` (`Pink Marbled`). The whole
  "Advanced Format Logic" section (~420 lines: edition grouping, CD/tape/video blocks, data.json tag ordering) is gone;
  nothing after it referenced any of its variables (checked before deleting), and `_discogs_format_parts()` replaces it.
- **Genre and Style lines added**, straight from `genres` / `styles`, in Discogs' order, after Released (skipped when
  empty). `app.js`'s paste parser only looks at known prefixes, so the extra lines are ignored there.
- Multi-disc quantity is kept as `2xVinyl` (not `2 x Vinyl`) because `generateListingData()` matches `/(\d+x)/` for its
  quantity prefix and `/(\d+xLP)/` for the size.
- Not changed, still as before: the Label line (`Kanine Records KR107`, space rather than the page's " – ") and the
  ISO date (`2014-04-19` rather than `Apr 19, 2014`).
- Verified: `ast.parse` plus the harness above.

### 88. run_me_Installer.bat — reports what it stops, kills UberPaste, narrates the backup
**Files:** `run_me_Installer.bat`, `dist_install/run_me_Installer.bat`, `!build.bat`
- Rewritten in the style of `kill_wysiwyg.bat`: every step prints a `stopped` / `skipped` / `FAILED` line instead of
  swallowing the result in `>nul`.
  - Calls `kill-wysiwyg.ps1` when it sits next to the script (that is the repo copy), so the process list stays in one
    place; otherwise a built-in fallback does the same jobs with the same wording (that is the `dist_install` copy).
  - `:stopexe` checks with `tasklist` first, kills with `taskkill /F /T`, then re-checks: a process that survives is
    reported as `FAILED … try running this as administrator` rather than a silent success.
  - `:stopsource` stops `python.exe ...\scanner_server.py` / `...\main.py` / `...\UberPaste.py`, verifying each pid
    afterwards, so a venv launcher that takes its child with it is reported once instead of "stopped" + "FAILED".
- **UberPaste is now shut down** — both `UberPaste.exe` and a copy started from source. `kill-wysiwyg.ps1` leaves it
  alone on purpose (it reports other Python as "left alone, e.g. UberPaste"), but the installer replaces its files.
- **Backup step narrates itself:** "Deleting the previous backup: C:\FYRTOOLS\wysiwyg.old", then "Copying … to …", then
  either "Backup complete." or a WARNING when `xcopy` fails (the old script printed "Backup complete." unconditionally),
  and "nothing to back up" when there is no current install.
- Also: refuses to run when `INSTALL_WYSIWYG.exe` is missing, reports the installer's exit code, and `pause`s so the
  summary stays on screen after a double-click.
- `!build.bat` now copies the repo's batch into `dist_install\` at the end of every build, so the copy that ships next to
  `INSTALL_WYSIWYG.exe` can never drift again (it was a stale copy that still killed "XDevHubX" and nothing else).
- **Gotcha:** labels used inside `if ( … )` blocks must not contain parentheses. `"WysiScan (scanner)"` closed the block
  early and produced `- was unexpected at this time`; the labels are now plain words.
- Verified: the helper subroutines were run against a live dummy exe and a live dummy Python process (both stopped and
  reported), a dry run against names that do not exist (both `skipped`), and a syntax run in an empty folder (banner +
  "INSTALL_WYSIWYG.exe is not in this folder" + exit 1). The full install path was not executed - that is the user's.
- Not changed: the installer's own [Code] kill list (compiled into `INSTALL_WYSIWYG.exe`) still does not stop UberPaste,
  so running the exe directly, without the batch, can still hit a locked UberPaste file.

### 89. Main app — "Name - CAT#" label line and "Apr 19, 2014" release date
**Files:** `main.py` (`scrape_url` route, `_format_discogs_date`)
- **Label:** the catalogue number is now joined to the label name(s) with `" - "` instead of a space, in every branch:
  one label → `Label: Kanine Records - KR107`; several labels → `Label One - CAT1 / Label Two - CAT2`; labels sharing
  one cat# → `Shared A / Shared B - X1`; a label with no cat# keeps just its name (no dangling dash).
  Verified by running the extracted labelling block against those four shapes.
- **Released:** Discogs sends ISO (`2014-04-19`) and the page shows `Apr 19, 2014`, so `_format_discogs_date()` renders it
  the same way — day not zero-padded (`Apr 9, 2014`), month names from a fixed tuple so the machine's locale cannot change
  them, partial dates kept (`2014-04` → `Apr 2014`, `2014` → `2014`), a `-00` day treated as unknown (`Apr 2014`), and
  anything that is not an ISO date passed through untouched. `app.js` still reads the year with `/\d{4}/`, so the Year
  field keeps filling itself.
- Verified: `ast.parse` plus a harness over eight date shapes and the four label shapes.

### 90. Version 1.19.12.66 + changelog section
**Files:** `version.json`, `wysiWyg-installer.iss`, `changelog.txt`
- `version.json` is now `{major: 1, minor: 19, patch: 12, build: 66}` and `#define MyAppVersion` in the installer matches
  `1.19.12.66`. `get_current_version_str()` prints the raw parts, so the window title and User-Agent read `1.19.12.66`.
- New `### v1.19.12.66 - 2026-11-16` section at the top of `changelog.txt` (17 entries, newest-first as the file expects -
  `/api/changelog` sorts by header date then version tuple). The old `v1.19.8.3` header is untouched history.
- The file is UTF-8 like the rest of the changelog (it already carried em dashes and arrows), so the `✕` in the Conditions
  entry decodes fine even though a cp1252 console shows it as garbage.
- Nothing else hardcodes the old number: the only remaining `1.19.8.3` strings are the previous changelog header and the
  Continuity decision log.

### 91. Main app — a page refresh is a Reset All
**Files:** `app.js` (`DOMContentLoaded` init, `fullReset`)
- F5, the Refresh button (`refreshBtn`), and the drawer's Refresh all reload the page, so hooking the load covers all
  three: the init now schedules `fullReset()` once the page has finished loading.
  - **It must run after `load`, not at DOMContentLoaded** - Chromium re-applies the previous form state *after*
    DOMContentLoaded, so clearing earlier is silently undone. A `resetOnLoadDone` guard means the `load` handler and the
    3 s backstop can both fire without resetting twice.
  - `initializeDropdowns()` is now awaited in the init, so the selects are populated before the reset clears them (it used
    to race the /settings fetch).
- The Chrome extension's SSE hand-off cancels a pending load-reset (`resetOnLoadDone = true`) before it fills the URL box
  and clicks Scrape, so a push that lands in the first second cannot be wiped by the reset.
- **Fix found on the way:** `fullReset()` cleared every `select:not(#skuFlag)` to the empty option, and
  `#conditionMediaType` has no empty option — so Reset All left it blank, and `renderConditionMultiselects()` then hid
  every condition row. It is now put back to `selectedIndex = 0` (LP), so the lists always show something.
- Verified: `node --check app.js`; the ordering (reset before the SSE bridge, after the awaited dropdowns) is visible in
  the init block. Browser behaviour is the user's to test.

### 92. `docs/DISCOGS-FIELD-PROVENANCE.md` — which scraped fields are typed vs picked
**Files:** `docs/DISCOGS-FIELD-PROVENANCE.md`
- Keeps the two live-API checks together: the closed-vocabulary probe (`format=Compilation` returns 2.4M items,
  `format=Pink Marbled` returns 0; `genre=Rok`, `style=Indierock`, `country=U.S.A.` all return 0) and the 30-release
  sample (`format name` 2 distinct, 17 descriptions, 7 genres, 30 styles, 12 countries, 42/42 label rows carrying an id).
- Includes the release 5610215 test case in full: API payload, the output of the real `/scrape` formatting code, and a
  per-token provenance table (only the title, the catno and the format free text were typed).
- Records the rules that follow - match on `name` + `descriptions` rather than the whole Format line (because "Box Set"
  can be typed into the free-text box), pass `text` through as display text, treat `catno` defensively, keep partial
  dates - plus the caveats (the API cannot report the widget; the Discogs page 403s a scripted request) and the exact
  probe URLs for re-running it.
- No code changed: verification and documentation only.

### 93. Colour engine (1/3) — F0T capture and its endpoints
**Files:** `main.py`
- New constant `F0T_FILE = "f0t_last.txt"` (next to the exe, same as `config.json`), plus `COLOUR_RULES_FILE` and
  `DEFAULT_COLOUR_RULES`.
- `write_f0t_file(f0t_text, colour_map_texts, formats_data, note_lines)` writes **`formats[0].text` verbatim** in a `[F0T]`
  section, then `[F0T MAPS]` (the free text of **every Vinyl entry**, one per line, in Discogs order), then `[FORMATS]`
  (the raw formats array as one-line JSON, used to group a box set's media), then `[NOTES]` (title, formats[0]
  name/descriptions, number of vinyl entries, country, released). Overwritten on every scrape. `[F0T]` stays pristine for
  reference; the engine reads `[F0T MAPS]` and falls back to `[F0T]` when that section is absent or empty.
- `/scrape` calls it just before `raw_text_tool` is assembled, using the raw API fields (not the built format line, which
  splits free text on commas/slashes and would corrupt `Blue/Grey Clear`).
- Why the maps section: release 14655692 has two `Vinyl` entries, each with its own text (`Red & White Marble, 180 Gram`
  and `White & Black Marble, 180 Gram`). Only reading formats[0] lost the second colour entirely. Each map is parsed on
  its own and the phrases are stitched inside the single group with `" + "` (rule from the user), duplicates removed.
- New `GET /api/f0t` (text/plain, no-store) returns that file; if it is missing it returns an empty `[F0T]` block.
- New `GET /api/colourrules` returns `colourrules.json`, or `DEFAULT_COLOUR_RULES` when the file is absent.
- The response script that runs after a scrape now calls `prepareColourAssets()` before `parsePastedData()`, so the
  dictionaries and F0T are loaded first; Auto Generate is chained after that instead of a blind 50 ms timer.
- **Undo:** delete the `F0T_FILE`/`COLOUR_RULES_FILE`/`DEFAULT_COLOUR_RULES`/`write_f0t_file` block (marked
  `COLOUR ENGINE (vinyl / F0T)`), the two endpoints (same markers), the `write_f0t_file(...)` call in `/scrape`, and
  restore the injected script to its previous `parsePastedData(rawText)` + separate auto-gen timer.

### 94. Colour engine (2/3) — the vinyl parser in the app
**Files:** `app.js`
- A self-contained block between the markers `// COLOUR ENGINE (vinyl / F0T) -- start` and `-- end` (just above
  `parsePastedData`) holds everything: `lastF0T`, `lastF0TMaps`, the two dictionary caches, `loadColourAssets()`,
  `loadF0T()`, `prepareColourAssets()`, `colourEngineApplies()`, `colourStripPrefix()`, `colourRemovePhrases()`,
  `colourTidy()`, `colourIsBasic()`, `colourPhraseFromF0T()` and `colourPhraseFromMaps()`.
- **Multiple colour maps:** `colourPhraseFromMaps()` runs each vinyl entry's free text through the engine separately and
  stitches the results inside one group with `" + "` (duplicates dropped). `loadF0T()` reads `[F0T MAPS]` and falls back
  to `[F0T]` for older files.
- **Gate:** `colourEngineApplies(mediaFormatValue, formatLine)` — true when the Media Format select reads `Vinyl`, **or**
  the Format line contains `vinyl` (a box set with another type selected). Everything else falls through to the old
  `data.json['Color']` scan, which is untouched.
- **Engine order:** strip a leading `Colored`/`Coloured`/`Color` (unless it is a dictionary term such as `Color-in-Color`)
  → drop `noise` phrases (so `White Label` cannot become `Colored (White)`) → fence at `stops` and at `,`/`;` → keep only
  segments containing a colour or textmod anchor → tidy → one group. Basic-only segments normalise `and` to `/`;
  complex segments (any textmod or unknown word) keep the source wholesale with `and` → `&`.
- Slash entries in `colourmap.json` (`Gold / Golden`) are split when the dictionaries are built, so either spelling
  matches.
- **Wiring:** inside the existing `format:` branch of `parsePastedData`, the old colour scan is now the `else` arm of the
  new gate. The result is still written to `#mediaColor`, so the rest of the builder is unchanged.
- **Bug #1 fix (gate):** the first version tested `/\bvinyl\b/i` against the format line, which never matched our own
  `2xVinyl` (there is no word boundary between `x` and `V`). On release 12644069 the Media Format select had also latched
  onto `All Media` (longest match wins), so the gate fell through to the old scan and produced `Colored (Blue & Clear &
  Grey)` instead of `Colored (Blue/Grey Clear)`. The test is now `/(?:^|\d+x|[^a-z0-9])vinyl(?:$|[^a-z0-9])/i`, which
  accepts the quantity prefix; verified against that release's real format line
  (`2xVinyl, LP, Limited Edition, Blue, Grey Clear, CD, All Media` → gate true) and against CD/cassette lines (false).
- Separate, pre-existing quirk seen in the same output: the Media Format select picks `All Media` over `Vinyl` because
  the longest option wins, so the description reads `LP 2xAll Media`. Not part of the colour work - flagged, untouched.
- **Complex-format path** (`generateListingData`, `formatLineRaw` contains `" + "`): the old loop that wrapped every
  colour word separately is replaced by a single in-place `Colored (<phrase>)`, matching the phrase words in order with
  any separator between them (the format line may have flattened `/` and `,`). This is what removes the
  `Colored (Blue) Colored (Pink)` output.
- **Undo:** delete the marked block, change the `if (colourEngineApplies(...))` arm back to the bare old colour code
  (i.e. remove the gate and the `else` wrapper), and restore the old colour-injection loop in `generateListingData`.

### 95. Colour engine (3/3) — rules file and packaging
**Files:** `colourrules.json` (new), `!build.bat`, `WYSIWYG.spec`, `wysiWyg-installer.iss`
- `colourrules.json` holds `noise` (dropped inside the bracket only: 180g, 180 Gram, Gatefold, Numbered, Stereo, Mono,
  Remastered, Club Edition, White Label) and `stops` (fences the phrase: Vinyl, LP, CD, Cassette, DVD, Blu-ray, Box Set,
  All Media, Gatefold, Insert, Poster, Edition, Album, Compilation, Single, EP, Reissue, Repress, Remastered, Limited
  Edition, Pressed On, Pressed). `_notes` explains the file for whoever edits it next.
- Shipped three ways: `--add-data "colourrules.json;."` in `!build.bat`, `('colourrules.json', '.')` in
  `WYSIWYG.spec`, and a `[Files]` entry in the installer (`ignoreversion uninsneveruninstall`, like `colourmap.json`).
- `f0t_last.txt` is generated at runtime and is deliberately **not** shipped.
- **Undo:** delete `colourrules.json` and remove the three packaging lines.

**Change manifest (for review/removal)**

| File | Area | Kind |
|---|---|---|
| `main.py` | constants + `write_f0t_file()` | new, marked block |
| `main.py` | `/api/f0t`, `/api/colourrules` | new endpoints, marked |
| `main.py` | `/scrape` | new `write_f0t_file(...)` call, marked |
| `main.py` | scrape response script | auto-gen/parse re-ordered around `prepareColourAssets()` |
| `app.js` | above `parsePastedData` | new marked block (whole engine) |
| `app.js` | `parsePastedData` colour scan | old code kept as the non-vinyl `else` |
| `app.js` | `generateListingData` complex branch | old multi-wrapper loop replaced |
| `colourrules.json` | — | new file |
| `!build.bat`, `WYSIWYG.spec`, `wysiWyg-installer.iss` | — | one line each |

### 96. Weight/Speed written twice — "180 Gram 180 gram"
**Files:** `app.js`
- Cause: `data.json` → `Weight/Speed` contains **both** `"180 Gram"` and `"180 gram"` as separate entries. The scrape parser matches options
  case-insensitively, so both get selected, and `getVal('weightSpeed')` joins them, giving `180 Gram 180 gram` in the description.
  Not caused by the two vinyl entries - it happens on any release whose line says `180 Gram` (the twin entry in the release just
  made it obvious).
- Fix: new `dedupeCaseInsensitive(values)` helper, used for the generic multi-select join in `getVal()` (Weight/Speed, Format Tags,
  Pre/Post FM, Packaging Feature, Sleeve Packaging). The first selected spelling wins, so the list order decides: `180 Gram`
  beats `180 gram`. Single-value selects and the special `edition` branch are untouched.
- Verified with a harness: `["180 Gram","180 gram"]` → `["180 Gram"]`, `["180g","180 Gram","180 gram"]` → `["180g","180 Gram"]`,
  `["180 gram","180 Gram"]` → `["180 gram"]` (first wins), unrelated values unaffected.
- **Undo:** delete `dedupeCaseInsensitive()` and change the join in `getVal()`'s multi-select branch back to
  `Array.from(el.selectedOptions).map(o => o.value).filter(v => v).join(joiner)`.

### 97. Box sets — rebuild the media portion from the formats array
**Files:** `main.py`, `app.js`
- Symptom (release 2853111, Soundgarden – Telephantasm): `NTSC Colored (…) LP 7" 2xDVD-Video Box Set` instead of
  `2xCD + NTSC DVD-Video + Colored (…) 3xLP + 7" Box Set`. The old media string was assembled from the tag/format-tag
  selects, which have no concept of per-entry grouping or quantity, so a box set lost the CD/DVD blocks entirely.
- Fix: the server now also writes the raw formats array to `f0t_last.txt` as `[FORMATS]` (one-line JSON), and
  `buildBoxSetMediaString(formats, colourPhrase)` rebuilds the media portion from it. **Gated on a `Box Set` format
  entry** - every other release keeps the existing assembly, unchanged (Cypress Hill's accepted `LP 2xAll Media` output
  is untouched).
- Rules implemented, in Discogs order:
  - each medium becomes its own block, joined with ` + `;
  - a count is added whenever a medium totals more than one (`2xCD`, `3xLP`, `2x7"`), summed across entries;
  - `Vinyl` with `LP` in its descriptions becomes `LP`; a bare size description (`7"`, `12"`) is used as the label; other
    vinyl falls back to `Vinyl`;
  - an `LP` block carries the word **Vinyl** the same way a single-disc release does - `LP Vinyl`, `3xLP Vinyl`,
    `7xLP Vinyl` (sizes such as `7"` stay bare, matching the earlier accepted Telephantasm output);
  - `DVD` takes `DVD-Video` / `DVD-Audio` from its descriptions, and media modifiers - `Promo`, `NTSC`, `PAL`, `SECAM`,
    `Multichannel`, `Quadraphonic`, plus speeds (`45 RPM`, `33 RPM`, `33⅓ RPM`, `78 RPM`, `16 RPM`) - are placed **in
    front** of their own medium (`Promo 45 RPM 7"`, `NTSC DVD-Video`, `Multichannel Blu-ray`, `45 RPM 4x12"`); they are
    written in the order of that list, not the order Discogs happens to list them, and they are kept out of the edition
    fold so they never appear twice or in the wrong place (a `Promo` that belongs to the 7" no longer shows with the
    editions);
  - **a modifier is written once**: after `45 RPM 4x12"` the following `7"` does not repeat it, because the speed was
    already stated for the run of formats;
  - **kind suffixes** (`Single`, `EP`, `Maxi-Single`, `Mini-Album`) are appended when *every* entry merged into that block
    carries the same one - `7" Single` yes, while the four 12" entries (Mini-Album / EP / EP / Single Sided+Single) agree
    on nothing, so nothing is appended;
  - the single `Colored (…)` group is placed immediately in front of the first vinyl block (`… Colored (…) 3xLP …`), not as
    its own ` + ` segment;
  - `Box Set` is appended as a word at the end (not ` + Box Set`);
  - `All Media` entries are skipped and `Box Set` entries contribute only the trailing word.
- **Format Tags on a box set (bug #2):** because the media string is now built only from media entries, a tag that lives
  on a media entry was lost - release 22212301 (Ramones) has `Reissue` on the 6×Vinyl entry, so it vanished from the output.
  `processFormatData()` now folds `formatTags` into the `edition` string when `isBoxSetFormats(lastFormats)` is true, which
  puts it exactly where the user's correction wants it: `… Numbered Record Store Day Reissue 2022 Worldwide …`. If the
  Format Tags select comes back empty, the tags are read straight from the raw descriptions (filtered against
  `data.json` → `Format Tags`) so a tag cannot silently disappear. Non-box releases are untouched (their tags still ride
  in the media string).
- Verified with harnesses: Telephantasm produces exactly
  `2xCD + NTSC DVD-Video + Colored (Green Starburst + Red/Orange Starburst + Blue-Green with Black Smoke + Purple Marble) 3xLP + 7" Box Set`;
  Ramones produces `Colored (Pink & Black Splatter On Clear (Neon Pink)) 7xLP Box Set` (6+1 LP entries); a CD+DVD-Audio box
  gives `CD + DVD-Audio Box Set`; a non-box release returns `""` (old path); the `[FORMATS]` JSON round-trips and the
  section regexes were re-checked after the new section was added (the maps regex had to stop at `[FORMATS]` as well,
  otherwise the JSON would have been read as colour maps).
- **Undo:** remove `isBoxSetFormats()` / `buildBoxSetMediaString()` and the `const boxSetMedia = …` branch in
  `generateListingData()`, remove the format-tag fold in `processFormatData()`, drop `[FORMATS]` from `write_f0t_file()`,
  and delete `lastFormats` from `loadF0T()`.

---

## Notes / gotchas
- **Never leave a test listener on 8008 / 8010.** While verifying the port-owner kill logic I left
  `python -m http.server 8008` processes running; the app then served CPython's
  `404 - Nothing matches the given URI` page instead of the real UI (13 Nov 2026). Use a port outside
  the app's range (e.g. 8123) for throwaway tests, and check `Get-NetTCPConnection -LocalPort
  8008,8010 -State Listen` is empty before finishing.
- **Restarting the app does NOT restart WysiScan.** `POST /run-wysiscan` returns "already running" as
  soon as port 8010 is in use, so clicking WysiScan again re-uses the old process — and that process
  caches `scanner_test.html` in memory (`_INDEX_HTML_CACHE`). Scanner edits therefore need the scanner
  process killed (or a ~2 min idle shutdown from closing its window) before reopening it:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*scanner_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`
  Symptom of a stale scanner: code changes "don't apply" even after a restart (13 Nov 2026).
- **Image quality drops with repeated edits** (reported by users, investigated 13 Nov 2026; **fixed
  13 Nov 2026** — see entry 68): every edit endpoint (`rotate-image`, `deskew-image`,
  `rotate-image-fine`, `manual-crop`, `adjust-image`, and the crop/straighten/tilt steps) does
  `cv2.imwrite(path, …)` back onto the **JPEG** after reading the already-compressed file. OpenCV's
  default save is quality 95 **with 4:2:0 chroma subsampling**, which on a real scan measures only
  28.0 dB PSNR (saturation-plane error 11.7) and gets worse with each generation: 26.1 dB after two,
  25.0 dB after four. All scan writes now go through `_imwrite_image()` (97, 4:4:4): 44.3 dB after one
  generation and 44.2 dB after four, i.e. generations barely compound any more. A full
  crop → adjust → tilt pass on a 6 MB scan went from **21.7 dB to 40.0 dB** versus an ideal in-memory
  version. Files are ~2.5x larger (250 KB → 640 KB cropped), which is worth it. **Never call
  `cv2.imwrite` directly for a scan** — use `_imwrite_image`. The remaining option, if it ever matters,
  is a lossless PNG master per scan with JPEG written only on export.
- Scanner changes need a scanner restart; HTML/JS changes only need Ctrl+F5, but the new
  in-memory HTML cache means `scanner_test.html` edits require restarting the scanner server.
- Main app changes need an app restart (uvicorn runs without reload).
- `ChromeExt` changes need the unpacked extension reloaded in chrome://extensions. Client machines
  load the shared copy (`\\<server>\FYRTOOLS\WYSIWYG\ChromeExt`), which only refreshes when the
  installer runs on the server — a repo-only edit reaches nobody until then. "My extension change
  did nothing" is almost always a stale loaded copy: check the version on chrome://extensions first.
- The `Adds/` pages (Amazon/Discogs) are bundled into the exe via `--add-data "Adds;Adds"` and served
  from `_MEIPASS`, so page/JS changes there need a rebuild, not just an app restart.
- `WysiScan/UI-COMPACTION-NOTES.md` documents the scanner top-area layout compaction.
- **Tesseract is not used on this machine** (verified 13 Nov 2026): no `tesseract.exe` on PATH, in
  Program Files, LOCALAPPDATA or the registry, no `TESSDATA_PREFIX`, and `pytesseract` is absent from
  `.venv311`, `.venv` *and the embedded build* (`build\WYSIWYG\warn-WYSIWYG.txt`: "missing module
  named pytesseract"). The scanner guards every call (`if pytesseract:`, `except
  TesseractNotFoundError`) and logs "Tesseract not available, skipping CD matrix orientation", so OCR
  silently degrades; the Extract Text feature uses Gemini, not Tesseract. Builds deliberately omit it.
