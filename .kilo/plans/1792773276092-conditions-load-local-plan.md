# Plan: Make "Manage Conditions" window load from local conditions.json

## Summary

Change the "Manage Conditions" window in `editor.html` to load from the
`conditions.json` file next to the running `wysiwyg.exe` instead of the
server master file.

## Background

- `main.py` `get_local_path()` returns `os.path.join(os.path.dirname(sys.executable), filename)` when frozen, so the local `Conditions.json` sits next to the running `wysiwyg.exe`.
- `main.py` `/api/conditions` (no `master` param) returns that local file via `FileResponse`.
- `main.py` `/api/conditions?master=true` returns the server master at `\\192.168.0.108\FYRShare\Tools\FYRTools\WYSIWYG\Conditions.json`.
- `main.py` `/api/save-conditions` (no `master` param) writes to the local file.
- `main.py` `/api/admin/sync-conditions` writes to the server master file.

Currently `editor.html` uses the server master endpoints for both load and save,
so the window edits the wrong file.

## Changes

### `editor.html`

1. **`openConditions()` (line 381-389)**: Change fetch from
   `/api/conditions?master=true` to `/api/conditions` so it loads the local
   file next to the running exe.

2. **`syncConditions()` (line 483-505)**: Change POST from
   `/api/admin/sync-conditions` to `/api/save-conditions` so it saves to the
   local file.

3. **Confirmation message (line 484)**: Update the confirm text from
   "This will overwrite the Conditions.json file on the network server
   (\\192.168.0.108). Proceed?" to something like "This will overwrite the
   local Conditions.json file next to the running version of WYSIWYG. Proceed?"

## Validation

- `node --check editor.html` is not applicable (HTML file). The change is
  limited to `editor.html` only.
- Manual verification: open the "Manage Conditions" window, confirm it shows
  the local file contents; make a change and click "Update To Server",
  confirm the local `Conditions.json` next to the running `wysiwyg.exe` is
  updated (and the server master is untouched).

## Notes

- The comment on line 383 ("User requested ONLY load the server side file")
  is now stale and can be removed or updated.
- No server-side (`main.py`) changes are required; the endpoints already
  support the local path.