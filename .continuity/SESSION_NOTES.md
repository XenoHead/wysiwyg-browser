# Session Notes — WysiWYG-Browser

> Current as of 2026-11-17. Replaces the stale 2026-05 / 2026-07 / 2026-10-27 sections
> (those are in git history on the previous revision of this file, and in docs/WORK_LOG.md).

## Where we are

- **Version 1.20.24.1** — 2026-11-17. `version.json`,
  `wysiWyg-installer.iss` (`#define MyAppVersion`) and the `changelog.txt` header agree.
- HEAD `c3fcb5e "24.1"`, which already contains `WalmartAPI/` and `!run-walmart.bat`
  (Scott committed the whole session's work there). Tree was clean before the
  `SESSION_NOTES.md` update that follows.
- Recent commits: `040b4e3 1.20.15.0`, `8a89330 Fix pasted-URL scrape returning nothing after
  Reset All`, `a4c2b81 Security: upgrade the Python runtime dependencies`,
  `a702bdc WysiScan overhaul, Box Set sleeve conditions, and the editor colour map`.

## 2026-11-17 — WalmartAPI (new, deliberately standalone)

- **New package `WalmartAPI/`** — Walmart Marketplace REST client plus a UPC lookup
  page. Files: `walmart_api.py` (client), `routes.py` (two routes), `walmart_api.html`
  (the page), `__main__.py` (standalone server), `cli.py` (smoke tests), `README.md`.
  Plus `!run-walmart.bat` in the repo root. WORK_LOG entry 131.
- **Not wired into the app.** `main.py`, `WYSIWYG.spec` and `install.py` were briefly
  edited and then reverted to their committed state — how this should work into the
  app is still an open decision (continuity decisions 275/276). The package itself is
  committed in `c3fcb5e "24.1"`; "separate" here means *not loaded by the app*, not
  *untracked*.
- **Run it:** `!run-walmart.bat` → `http://127.0.0.1:8009/walmart-api`. Port 8009 so it
  coexists with the installed app on 8008. `--port` / `-n` (no browser) supported.
- **Auth is client_credentials, not OAuth authorization-code.** The `.env` keys are a
  seller-owned app, so `POST /v3/token` with `grant_type=client_credentials` is correct
  and sufficient (900 s bearer, no refresh token, no sellerId). The authorization-code
  flow is only for approved Solution Providers acting for other sellers. Verified live:
  token OK, 11,875 items.
- **Lookup verdicts:** `yours-live`, `yours-unpublished`, `offer` (→ `MP_ITEM_MATCH`),
  `new-item` (→ `MP_ITEM`), `invalid` (bad check digit). Two read-only calls per scan.
- **Card → setup → listing (WORK_LOG 132/133):** a Walmart hit renders as a walmart.com-style
  card with `+ Add`; staging flips it to **Remove** and turns the "Your listing" panel into a
  compact item-setup form (Product Name, Brand, MPN, Genre, Condition, Site Description, SKU,
  Price, Quantity, read-only GTIN-14). `Submit` saves the form on the pending record and the
  panel re-renders it as "Your listing" (Status `Draft — not submitted`). Everything is local:
  `WalmartAPI/pending.json`, no feed, no catalog write, `WalmartSheet/` untouched.
- **No catalog match → Create item (WORK_LOG 135):** the `new` verdict opens a Seller
  Center-style create screen in the right panel, required attributes only (Product name,
  Description, Main image URL, Product subcategory, Product type, MPN, Brand name,
  Fulfillment, certification tick). `POST /create` validates and stores it with
  `source: "create"`; the panel then shows the draft listing with an `Edit` link.
  SKU/price are deliberately not asked for here.
- **The 404 from the installed build was expected** — `C:\FYRTOOLS\WYSIWYG` has no
  `WalmartAPI` folder, so the then-present guard dropped the route. That whole wiring is
  gone now; use the batch file.
- **Walmart Developer Docs MCP was evaluated and skipped** — docs-only (5 schema/auth
  tools, no live calls), gated to approved solution providers with sellers "soon", and
  the live `POST /v3/items/spec` already gives the authoritative schema.



- **Details/HTML tab:** Format line follows the Discogs page — Discogs order, repeats once,
  "Album" dropped. New Genre and Style lines. Label line reads "Name - CAT#". Release date in
  Discogs form ("Apr 19, 2014"), partial dates keep what is known.
- **Colour engine (vinyl only):** `Colored (...)` built from the Discogs format free text parsed
  against `colourmap.json`; noise (180g, Gatefold, Stereo, Promo, etc.) dropped; multiple colours
  separated with "/", a complex phrase keeps the submitter's "&"/"+"; multi-disc colours stitch
  with " + ". CD/cassette keep the old behaviour.
- **Box sets:** media portion rebuilt from the `formats` array in Discogs order with counts;
  media modifiers sit in front of their own medium; Format Tags stay with their medium; Box Set
  closes the line.
- **Conditions:** plain click toggles in the Media/Sleeve lists; per-list ✕ clears one list
  (the sleeve ✕ also clears the LP/CD/Cassette/Box Set sleeve lists); favouriting a Media
  Condition from right-click works again; Reset All puts Media Type back on LP.
- **App:** F5 / Refresh / menu Refresh now runs Reset All first.
- **WysiScan:** Autoscan remembered; Image Adjust sliders are editable number boxes with
  presets and Zero Out; crop-mode names renameable by right-clicking the selected radio;
  Menu button docked left; CD/45 Front levels text locally without an AI rotation; Adjust Pad
  auto-aligns first; Extract Text Discogs search by Cat#/UPC plus a no-spaces Barcode box.
- **WysiChat:** bubble resizable (Small/Medium/Large/Extra Large), remembered.
- **Installer:** `run_me_Installer.bat` reports stopped/skipped processes, shuts down UberPaste,
  narrates the backup and warns when it fails.

## Release artifacts (2026-11-16)

- `WysiScan\dist\WysiScan.exe` — 83.3 MB
- `dist\WYSIWYG\WYSIWYG.exe` — 11.6 MB, plus `WysiChat\dist\Wysichat.exe` — 23.9 MB
- `dist_install\INSTALL_WYSIWYG.exe` — 310.9 MB, `run_me_Installer.bat` refreshed
- Rebuild order: `WysiScan\WysiScan.spec` (PyInstaller) → `!build.bat` →
  `ISCC.exe wysiWyg-installer.iss`.

## Open work

- **WalmartAPI:** the UPC lookup page is built, with the card → `+ Add` / `Remove` →
  setup form → `Submit` → "Your listing" loop (local only). Scott to test it via
  `!run-walmart.bat`. The open question is **how it should work into the app** — nothing
  is wired (decisions 275/276). After the loop is signed off, the next real step is
  turning `pending.json` records into an `MP_ITEM` / `MP_ITEM_MATCH` feed, or
  `responseFormat=SPEC` prefill for a Walmart Sheet row.
- Nothing recorded as open at the end of WORK_LOG entry 98.
- Verification of the 1.20.15.0 build is Scott's — he tests from source, not the exe.

## Standing gotchas

- **Restart map:** main app change → restart the app (uvicorn has no reload); scanner change →
  kill the scanner process (it caches `scanner_test.html` in memory); ChromeExt change → reload
  in `chrome://extensions`; plain HTML/JS → Ctrl+F5; `Adds/` pages are bundled, so a rebuild is
  needed.
- **Protected areas:** `WalmartSheet/` and `Adds/` — no edits without an explicit request.
  Walmart Sheet was retired from the menu/hotkeys/installer at 1.19.8.3; the source stays.
- **Never leave a test listener on 8008 / 8010** — use e.g. 8123 for throwaway tests.
- **Batch-file traps met while writing `!run-walmart.bat`** (17 Nov 2026): `findstr /C:":8009 "`
  with a trailing space inside the quoted pattern silently matches nothing; a
  `netstat | findstr` "is the port free" check was non-deterministic (matched, then didn't, on
  identical input). Let the server report its own bind failure instead. Also keep `.bat` files
  CRLF — LF-only breaks labels/goto in places.
- **Log conventions:** every change gets a `docs/WORK_LOG.md` entry (files, why, undo) and a
  `changelog.txt` bullet under the current version header.
- **Changelog is newest-first** — the current section is at the top; some legacy appended
  entries sit lower down.
- **Pixel parity and nomenclature** are non-negotiable: identical fixed widths for repeated
  controls; UPC/GTIN, Genre, MPN, Site Description — exact terms.

## History

- Full detail: `docs/WORK_LOG.md` entries 1–98.
- Superseded session notes: previous revision of this file in git.
