# Session Notes - 2026-07-07

> **Collaborative workspace for you and AI**

## 🎯 Session Goals
- Automate Walmart Exporter data flow.
- Ensure correct nomenclature (UPC/GTIN, Genre, MPN, Site Description).
- Add UI flexibility for Key Features reordering.
- Add right-click page background scraping support for active Discogs release/master pages.
- Rename WysiScan crop mode radio buttons (CD Matrix, Tape, LP) to (Custom1, Custom2, Custom3).
- Rearrange and rename cropped image action buttons (Full, Open Image, Save This Image) to an equally-spaced row at the bottom of the section in WysiScan.
- Replace WysiScan image placeholders with a custom SVG saying "Scan or Import now".
- Rename the Help button (❓ Help) to "❓ Hot Keys" in WysiScan.
- Remove the "Tips" section from the WysiScan "Hot Keys" modal.
- Move the Clear button in WysiScan to the right of the Start Group button.
- Disable Scan, Import, and Crop buttons in WysiScan during manual typing in "Group Name" until "Start Group" is clicked.
- Move WysiScan's gallery refresh button (🔄) next to "Save Marked" under Group Actions, and rename the "Scan Group" header to "Group".
- Replace "Save Marked", "Delete Marked", and "Open Folder" button text with icons (💾, 🗑️, 📂) in WysiScan.
- Add group and individual file renaming functionality with a modal dialog in WysiScan.

## 💡 Key Decisions Made
- **Automated Pipeline**: Set page to auto-load from Builder AND Discogs sequentially on start.
- **Nomenclature**: Implemented strict 13-digit GTIN trigger and "Exact Match" genre logic to avoid mapping errors.
- **UI Flexibility**: Added native Drag & Drop + button reordering to the Features modal.
- **Cleanup**: Stripped "Out-of-Print" from descriptions and standardized CD -> Audio CD and DVD -> DVD-Video.
- **Timezone**: Locked Site Start Date to CST (America/Chicago) to prevent "tomorrow" dates after 6pm.
- **Fallbacks**: Configured MPN to fall back to UPC/GTIN and Label to fall back to Artist if Discogs fields are empty.
- **Forced Updates**: Set Country of Origin and SKU/Description to force-overwrite even if defaults (like "United States") are present.
- **Condition Grouping**: Implemented general grouping logic to combine shared adjectives/nouns (e.g., "water damage to Booklet/Inlay") with a `/` separator.
- **Extension Enhancements**: Added a context menu item ("Send Page to WYSIWYG Scraper") to scrape the current page URL when right-clicking on the background of active Discogs release/master pages.
- **HTML Description Cleanups**: Filtered out the '--- Scraped via Master Release ---' header line in the HTML formatter to prevent it from rendering as the main album header on the Details tab.
- **WysiScan Generalization**: Renamed Crop Mode radio buttons from "CD Matrix", "Tape", and "LP" to "Custom1", "Custom2", and "Custom3" in the UI to more general labels, preserving values and logic.
- **WysiScan Button Optimization**: Moved "Full" and "Open Image" buttons down next to "Save This Image", simplified their labels to "Full", "Open", and "Save", and aligned them in a clean, equally-spaced horizontal flexbox container.
- **WysiScan Custom Placeholders**: Replaced default/broken image placeholders with a custom dark-mode SVG displaying a "Scan or Import now" message.
- **WysiScan Help Renaming**: Renamed the "❓ Help" button in the WysiScan header to "❓ Hot Keys" to make its utility for showing shortcuts clearer.
- **WysiScan Modal De-cluttering**: Removed the obsolete "Tips" section from the "Hot Keys" modal to keep the content strictly focused on keyboard shortcuts.
- **WysiScan Clear Control Relocation**: Moved the "Clear" button to the right of the "Start Group" button inside the Group Name input group to align and style them consistently.
- **WysiScan Safe Group Name State**: Disabled Scan, Import, and Crop action buttons while the user is manually editing or typing in the Group Name text box, ensuring a group is explicitly started/resumed first.
- **WysiScan Sidebar Refresh**: Relocated the gallery refresh button (🔄) to the Group Actions bar (to the left of "Save Marked") and renamed the header "Scan Group" to "Group".
- **WysiScan Icon Toolbars**: Replaced text labels for "Save Marked", "Delete Marked", and "Open Folder" with emoji icons (💾, 🗑️, 📂) and hover tooltips for a more compact sidebar layout.
- **WysiScan File Renaming Modal**: Added a rename button (✏️) to the Group Actions toolbar that launches a modal to rename either a single file or a whole group (preserving numeric suffixes like _1, _2), automatically syncing the active Group Name UI state.
- **WysiScan Rename Fixes**: Solved Windows-specific FileExistsError during same-name renames by skipping redundant os.rename calls, and improved UX by auto-detecting numeric suffixes in single-file renames (e.g. Vlad_6) to keep the active group selection aligned.
- **WysiScan Gallery Labels**: Replaced the default "Cropped #X" checkbox headers in the gallery list with the actual file names, and removed the duplicate filename text block from the bottom of each item.
- **WysiScan Checkbox Relocation**: Moved the item selection checkbox to the left of the filename inside the gallery item header for standard alignment.
- **WysiScan Manual Crop Canvas**: Configured the manual crop window to open with no default/automatic selection box on the screen, creating a clean canvas to easily draw a custom crop box directly.
- **WysiScan Layout Optimizations**: 
  - Reduced gallery thumbnail item width to `150px` for a more compact list view.
  - Relocated "Select All" checkbox to the right of the "Group Actions" header, removing the redundant "Group" label header.
  - Moved the red "EXIT" button to the top header right next to the "Theme" button via a flexbox container, removing it from the action toolbar.
- **Installer Process Lock Resolution**:
  - Added `CloseApplications=force` in `wysiwyg-installer.iss` to use Windows Restart Manager for unlocking files.
  - Resolved potential issues with broken system `PATH` envs by using `ExpandConstant('{sys}\taskkill.exe')`.
  - Added `Sleep(1500)` delays to allow the OS to cleanly release file locks before setup tries to overwrite files.- **Scanner Server Heartbeat Timeout**: Increased heartbeat timeout from 8 seconds to 60 seconds. Browser tab throttling in background tabs was stopping the heartbeat interval and causing the server to shut down prematurely, resulting in "failed to fetch" errors.
- **Scanner Exit Logic**: Fixed the Exit button and the fetch auto-close logic in `scanner_test.html`. Ensured `window.close()` is executed on success, failure (fetch wrapper reject), or timeout, resolving the issue where the page stayed open showing "Server is shutting down".

## ✅ Next Steps
- Verify that backgrounding the WysiScan tab for longer than 8 seconds no longer causes a "failed to fetch" network error when returning and scanning.
- Verify that clicking the EXIT button cleanly terminates the server and closes the browser window.
- Verify WysiScan crop mode names, button layouts, custom placeholders, the renamed "Hot Keys" button, Clear button position, typing-disabling behavior, and the relocated refresh/icon/rename actions in the UI.

---
*Last updated by AI: 2026-07-15 11:08*

---

## Session 2026-10-27 (release 1.15.3.18)

### Completed
- Editor: pre-overwrite server backups (conditions_pre_/data_pre_ timestamps), toast notifications, search clear + blank-item visibility, no-store caching.
- Passwords: PBKDF2 in allpass.json + server-side verify; set_password.exe (icon, BOM/empty/corrupt-JSON tolerant, not shipped).
- Main app: lazy share probing (no UNC at startup), tab-aware heartbeat auto-exit, service-status cache, share paths via DEFAULT_SERVER_ROOT.
- Heartbeat/exit, WYSIWYG dialog runner (--run-script), Image Convert availability check for packaged layout.
- Conditions: All Types pickers unified (Media/Sleeve switch, type selector, Unfavorite All, blue active column), search autofocus + clear in picker and Edit Conditions, Close button, object-identity row actions (fixed filtered-index bug).
- Descriptions: "with" sleeve prefix, Artwork collapse rules (Insert / Jcard / LP Sleeve), flaw grouping (Corner/Edge/Spine, adjectives, leading objects, 3+ separators A / B & C, description text joins its own side, noun capitalisation with "of" exception).
- WysiScan: all blocking endpoints moved off the event loop, visibility-aware heartbeat, thumbnails + disk cache + in-memory HTML, CORS/path hardening, frozen launch polling, popup-gesture fix (open tab before await), Image Convert bundled in standalone (excluding .venvic).
- Build: favorites stripped from source + shipped Conditions.json, .env/keys.txt copied into dist, version 1.15.3.18, changelog entry, Inno installer rebuilt.

### Artifacts (final)
- dist\WYSIWYG\WYSIWYG.exe (1.15.3.18)
- dist_install\INSTALL_WYSIWYG.exe (487,189,876 bytes, 17:43)
- WysiScan\dist\WysiScan.exe (87.2 MB, Image Convert bundled)
- dist_tools\set_password.exe (private tool)

### Notes
- Full details/undo steps: docs\WORK_LOG.md (entries 1-43).
- Rebuild order: `!build.bat` -> `WysiScan\build_scanner.py` -> ISCC on wysiWyg-installer.iss -> optional set_password PyInstaller.
- Standing rule: never edit WalmartSheet/ or Adds/ without explicit request.
