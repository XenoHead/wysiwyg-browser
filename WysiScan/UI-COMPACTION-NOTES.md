# Scanner top-area compaction (2026-10-27)

## Goal
Make the lower scanner UI (previews / results / status) easier to see by shrinking
everything from the top of the page down to and including the **Crop Mode** box.

## File touched
`WysiScan/scanner_test.html` — **CSS only**. No HTML markup and no JavaScript was changed.

## What was added
One new CSS block at the end of the existing `<style>` section, immediately after the
`#tilt-ui button` rule and just before `</style>`. It is delimited by the comment:

```
/* ==== COMPACT TOP AREA (2026-10-27) ==== ... Undo = delete this whole block. */
```

The block overrides the inline `style="..."` attributes already present in the markup.
Stylesheet `!important` beats inline styles, so no inline attributes had to be edited.

## Exact changes (before → after)

### Page shell
| Element | Before | After |
|---|---|---|
| `body` padding | 20px | 8px |
| `.container` padding | 20px | 8px 10px |
| `.container > p` | default 16px, browser margins | 11px, `margin: 0 0 6px` |
| `.app-topbar` | no margin rule | `margin-bottom: 4px` |

### Top row (Scanner Settings + Image Convert)
| Element | Before | After |
|---|---|---|
| `.top-row-layout` gap / margin-bottom | 20px / 20px (inline) | 8px / 6px (`!important`) |
| `.scanner-settings-left` gap | 15px (inline) | 4px (`!important`) |
| `.scanner-settings-left label` | inherited (~16px) | 11px |
| `#scannerSelect` padding / font | 10px / 16px (inline) | 3px 6px / 12px |
| `#saveLocation`, `#groupName` padding / font / margin-bottom | 10px / 16px / 10px | 3px 6px / 12px / 0 |
| `.scanner-settings-left .input-group button` | 10px 20px / 16px (global `button`) | 3px 8px / 11px |
| `.converter-panel-right` padding / gap | 15px / 12px (inline) | 6px 8px / 4px |
| Image Convert title | 16px bold (inline) | 12px, padding-bottom 2px |
| Converter labels / spans / strong | 13–14px | 11px |
| Converter text/number inputs | 6px 10px / 14px (inline) | 2px 5px / 11px, margin 0 |
| Converter radio/checkbox | browser default (13–16px) | 11×11px, margin 0 |
| Converter buttons (Browse etc.) | 6px 12px / 13px (inline) | 2px 8px / 11px |
| `#convWidth`, `#convHeight` width | 70px | 58px |
| `#btnBatchConvert`, `#btnOpenGUI` | 10px / 14px (inline) | 4px / 12px |

### Controls row (Scan / Import / Crop / Padding / Crop Mode)
| Element | Before | After |
|---|---|---|
| `.controls` margin-bottom / padding / gap | 20px / 15px 0 / 10px (inline) | 6px / 6px 0 / 5px |
| `.controls button` | 10px 20px / 16px (global) | 3px 10px / 12px |
| `.controls label` | inherited 16px | 12px |
| Crop Mode box (`div` inside `.controls`) | padding 6px 10px, gap 12px, 14px (inline) | padding 2px 8px, gap 8px, 11px |
| Crop Mode radio labels | 14px (inline) | 11px |
| `#cropPadding` | 60px wide, 6px padding, 14px font | 48px wide, 2px 4px, 12px |
| All checkboxes/radios in `.controls` | browser default | 12×12px |

The vertical separator `<span>`s, borders, colours and all element positions/order are untouched.

## How to undo
1. Open `WysiScan/scanner_test.html`.
2. Delete the entire CSS block between the `/* ==== COMPACT TOP AREA (2026-10-27) ==== */`
   comment and the following `#cropPadding { ... }` rule (the block ends just before `</style>`).
3. Reload the scanner window (Ctrl+F5). No restart of the server is required — the HTML is
   served from disk on each request.

Deleting the block restores every value listed above to its original (inline/global) setting,
because nothing else was modified.

## Follow-up (2026-10-27, same day): Extract Text button moved

**File:** `WysiScan/scanner_test.html` (HTML markup only).

- **Removed** the `🤖 Extract Text` button (`onclick="openCliModal()"`, purple `#6f42c1`) from
  the top bar; the top bar now contains only the `☰ Menu` button.
- **Added** the same button to the **Group Actions** button row inside the right sidebar,
  immediately to the right of the `📂` (Open Folder, `onclick="openSaveFolder()"`) button,
  separated by a vertical divider:
  `<span style="border-left: 1px solid var(--border-color); height: 20px; margin: 0 4px;"></span>`

**Undo:** move the button markup back inside `<div class="app-topbar">` and delete the
divider `<span>`.

No JavaScript was changed — `openCliModal()` is unchanged.
