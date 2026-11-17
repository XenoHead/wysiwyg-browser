# Session Notes — WysiWYG-Browser

> Current as of 2026-11-17. Replaces the stale 2026-05 / 2026-07 / 2026-10-27 sections
> (those are in git history on the previous revision of this file, and in docs/WORK_LOG.md).

## Where we are

- **Version 1.20.15.0** — released 2026-11-16. `version.json`,
  `wysiWyg-installer.iss` (`#define MyAppVersion`), `changelog.txt` and WORK_LOG entry 98 agree.
- Working tree clean at HEAD `718107b Update WORK_LOG.md`.
- Recent commits: `040b4e3 1.20.15.0`, `8a89330 Fix pasted-URL scrape returning nothing after
  Reset All`, `a4c2b81 Security: upgrade the Python runtime dependencies`,
  `a702bdc WysiScan overhaul, Box Set sleeve conditions, and the editor colour map`.

## What shipped in 1.20.15.0

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
- **Log conventions:** every change gets a `docs/WORK_LOG.md` entry (files, why, undo) and a
  `changelog.txt` bullet under the current version header.
- **Changelog is newest-first** — the current section is at the top; some legacy appended
  entries sit lower down.
- **Pixel parity and nomenclature** are non-negotiable: identical fixed widths for repeated
  controls; UPC/GTIN, Genre, MPN, Site Description — exact terms.

## History

- Full detail: `docs/WORK_LOG.md` entries 1–98.
- Superseded session notes: previous revision of this file in git.
