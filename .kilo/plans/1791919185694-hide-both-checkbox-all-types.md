# Plan: Hide "Both" checkbox in the Select Conditions "All Types" views

**Goal:** When opening "Open Media (All Types)" or "Open Sleeve (All Types)", hide the dual-column `Both` checkbox (which conflicts with the side-by-side LP/CD/Cassette layout), and keep all other views consistent.

## Context

- The "Both" checkbox lives in the condition-picker modal header, wrapped in a `<label>` (index.html:198–200). It toggles `conditionPickerViewMode` between `'single'` (one column) and `'dual'` (Media + Sleeve of the current type). In the three-column "All Types" layouts it is meaningless and produces a visual mismatch if still checked from an earlier session.
- Each picker-open function (`openConditionPickerForMedia`, `openConditionPickerForSleeve`, `openMediaConditionThreeColumnModal`, `openSleeveConditionThreeColumnModal`, `openDualColumnConditionPicker`) currently manages modal columns/header text and registers `conditionPickerRedraw`, but never touches the `Both` checkbox. There is no caller that restores it either.
- Also: the `change` handler on the checkbox is the only place that fully respects the current view — so adding explicit show/hide at every opener guarantees the UI matches what is actually rendered.

## Decisions

1. Hide the "Both" label in **both** All Types views (openMedia ×2, openSleeve ×2 — already decided by the user).
2. Always render "Both" when entering any single-type view (Open button, current-type media/sleeve openers). If currently in three-column mode, the checkbox gets unchecked (mode reset) and re-shown on top of whatever modal is opened next — the cleanest behavior because the modal DOM is replaced each open.
3. Add an id to the `<label>` wrapper in index.html so we can hide the whole control (including the "Both" text); a helper `setDualColumnToggleVisible(show)` does `label.style.display = show ? '' : 'none'` and unchecks the input when hiding.
4. Revert the redundant line added to `openCustomOptionsBtn` previously (its `renderConditionPicker()` already sets `conditionPickerRedraw`; the triple-set is unnecessary noise).

## Changes

### index.html — 1 element
- Add `id="dualColumnModeLabel"` to the `<label>` wrapping checkbox at line ~198.

### app.js — 1 new function + touches in every picker-open function
- New helper (near the other picker helpers, e.g. after `getConditionPickerConfigs`):
  ```js
  function setDualColumnToggleVisible(visible) {
      const label = document.getElementById('dualColumnModeLabel');
      if (!label) return;
      label.style.display = visible ? '' : 'none';
      const cb = document.getElementById('dualColumnMode');
      if (!cb) return;
      // Uncheck when hiding so a later single-type open isn't stale
      cb.checked = false;
  }
  ```
- `openMediaConditionThreeColumnModal`: after the early returns, call `setDualColumnToggleVisible(false)` at the start of setup.
- `openSleeveConditionThreeColumnModal`: same `setDualColumnToggleVisible(false)`.
- `openConditionPickerForMedia`: call `setDualColumnToggleVisible(true)` (current-type media column — both modes reachable, so show).
- `openConditionPickerForSleeve`: same `setDualColumnToggleVisible(true)`.
- `openDualColumnConditionPicker`: leave as-is (checkbox stays visible for the toggle user action); optionally assert `window.currentThreeColumnMode === 'dualColumn'` and call `setDualColumnToggleVisible(true)`.
- `renderConditionPicker()`: the OPEN path leaves the existing behavior. For symmetry, consider `setDualColumnToggleVisible(true)` at its end — but it's called from `toggleConditionOption` paths too where three-column mode may not be active; `setDualColumnToggleVisible(true)` is safe (sets display='' and doesn't check). Avoid scope creep — put it only where needed and documented. Keep minimal: only the four call sites above; add to `renderConditionPicker` if the fallback path needs it. Recommendation: do NOT add here; the callers cover it. Leave as-is except revert.

### Revert
- Remove the previously appended redundant line under the `openCustomOptionsBtn` click handler (it reassigns `conditionPickerRedraw` which `renderConditionPicker()` already does).

## Validation
- `node --check app.js` — must pass.
- Manual, no server/browser driving: verify open Media All Types → `Both` hidden and unchecked; switch it off (it shouldn't be toggleable, but must not throw); reopen through each opener (context menu / Open / row toggle / Done) → `Both` re-appears; reopen Media Current Type → `Both` visible unchecked; in Dual view → visible checked.

## Out of scope
- Session-aware tracking of previously-checked state across modal open/close — the straightforward approach (uncheck on hide, never force-check) avoids stale state entirely. Do NOT persist checkbox state between closes.
- Changelog entry and decision log are left out of this implementation plan; I will record them after execution in the project convention.
