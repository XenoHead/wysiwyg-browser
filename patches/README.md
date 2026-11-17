# WYSIWYG loose-file patches

> **Easiest way in:** double-click **`patches\Patch GUI.bat`**. It does the three
> things below (bump, build, apply) with tick boxes and no command line. The rest of
> this file is the same process written out for the command prompt.

Patching without reinstalling. A patch carries only the files this app reads from
its **install folder** at runtime, so no PyInstaller build and no 325 MB installer
is needed for a JS/HTML/CSS/data fix.

## Why this works

`resource_path()` in `main.py` prefers a file next to `WYSIWYG.exe` over the copy
bundled inside the exe:

```python
local_path = os.path.join(base_local, relative_path)
if os.path.exists(local_path):
    return local_path
```

The installer already puts `app.js`, `index.html`, `styles.css`, `data.json`,
`colourmap.json`, `changelog.txt` and friends in `C:\FYRTOOLS\WYSIWYG`. Replacing
those files is all a patch does - the exe is untouched.

## What a patch can carry

| File | Notes |
|---|---|
| `app.js`, `index.html`, `editor.html`, `admin.html`, `search.html`, `style_guide.html`, `styles.css` | UI and builder logic |
| `data.json`, `media_formats.json`, `colourmap.json`, `colourrules.json` | lists and colour rules |
| `version.json`, `changelog.txt` | always included, so the client's version advances |
| `fyrlogo.png`, `fyrlogo.ico`, `fyr-sign-front.png` | artwork |
| `ChromeExt\*` | extension files (the extension already self-updates, but allowed) |

**Deliberately not patchable:**

- `Conditions.json` - every machine keeps its own favourites and edits; a patch
  must never overwrite them.
- `.env`, `keys.txt` - secrets.
- Anything Python (`main.py`, `WysiScan\*.py`, `Uberpaste\`, `WysiChat\`, `Adds\`,
  `WalmartSheet\`, `WysiScan\*.html`). Bundled Python cannot be replaced at
  runtime - those changes need `!build.bat`.

`make_patch` enforces this: if a changed file is neither whitelisted nor ignorable
it refuses to build and names the offender.

## Build a patch

0. Or open `Patch GUI.bat`, type the note, tick the files and press **Build patch**.
   The GUI's **Bump patch version** button does step 1 for you.
1. Bump the version first (as usual): `version.json`, `wysiWyg-installer.iss`,
   and a new heading in `changelog.txt`.
2. From the repo root:

```bat
patches\make_patch.bat -Note "what this fixes" -Changed
```

`-Changed` reads `git status` and picks up every modified/untracked file that is
patchable. Only want some of them?

```bat
patches\make_patch.bat -Note "multi-medium descriptions" -Files app.js,index.html
```

Output lands in `patches\out\<version>\` (gitignored):

```
patches\out\1.20.17.0\
    patch.json          version, note, sha256 + size per file
    files\...           the payload
    apply_patch.bat     client-side applier
    apply_patch.ps1
    kill-wysiwyg.ps1
    close_local_chrome.ps1
```

## Publish it

```bat
patches\make_patch.bat -Note "what this fixes" -Changed -Publish
```

`-Publish` robocopies the folder to
`\\<server>\FYRShare\Tools\FYRTools\WYSIWYG\patches\<version>\`. Without it, copy
the folder there yourself. The share path can be overridden with `-ShareRoot`.

## How clients find out

Once a patch is on the share, nothing else needs doing:

1. A running app asks `/api/server-version` when it loads, and again whenever you
   come back to its tab.
2. If the newest published patch is newer than the installed version, the title
   bar shows `* UPDATE AVAILABLE *` and the banner reads
   `PATCH 1.20.19.0 AVAILABLE - CLICK HERE TO UPDATE`.
3. Clicking it asks once, then copies and verifies the files, starts a fresh
   instance and reloads the page on the new version - the same
   `apply_patch.ps1` as the command line.
4. If a full installer is published with a version **higher** than the newest
   patch, the banner offers that instead.

Clients therefore never run `apply_patch.bat` by hand; it stays as the fallback
for a machine where the app cannot start.

> **Bootstrap:** the check lives in the app. The first release that contains it
> has to go out as a full installer; after that, JS/HTML/CSS/data fixes are
> patches all the way.

## Apply it (client)

Run from the share:

```
\\<server>\FYRShare\Tools\FYRTools\WYSIWYG\patches\1.20.17.0\apply_patch.bat
```

`apply_patch` will:

1. Find the install folder (registry `InstallLocation`, else `C:\FYRTOOLS\WYSIWYG`).
2. Refuse if the patch is not newer than the installed `version.json`.
3. Ask for confirmation (skip with `-Yes`).
4. Back up every file it is about to replace to `C:\FYRTOOLS\wysiwyg.patch-backup\`.
5. Copy the payload, `version.json` **last** - while the app is still running
   (none of these files are locked).
6. Verify every copied file against `patch.json`'s SHA-256. On any mismatch it
   restores the backup and reports the failure - a half-applied patch cannot
   survive.
7. If the app is running, leave it alone: it reads these files from disk on
   every request, so the page just reloads on the new version. No restart, no
   second browser tab. If the app was closed, it is started.

When started from the app's update banner, the page shows a live
**Patching WYSIWYG** screen and reloads itself once `version.json` is in place
(it is copied last, so a match means the copy is complete). Every run appends to
`%TEMP%\wysiwyg_patch_apply.log`, and a failed run keeps its window open with the
reason.

It asks for admin only when the install folder is not writable.

Extra switches:

| Switch | Effect |
|---|---|
| `-Yes` | no confirmation prompt |
| `-NoStart` | do not start the app afterwards |
| `-DryRun` | check install path, versions and payload hashes, change nothing |
| `-SkipStop` | accepted for compatibility; the app is no longer stopped first |
| `-InstallDir "D:\..."` | override the detected install folder |
| `-PatchDir "D:\patch"` | apply a patch that is not in the script's own folder |

### Manual rollback

```
C:\FYRTOOLS\wysiwyg.patch-backup\
```

Copy its contents back over `C:\FYRTOOLS\WYSIWYG` with the app closed. The folder
also holds `patch-backup-info.txt` naming the version that was replaced.

## Rules of thumb

- **One version, one meaning.** If a batch of changes includes Python, do the full
  build and skip the patch. Never ship a full installer under a version that was
  already patched to clients, or the Python changes will never reach them.
- Keep patches small and frequent; they apply in seconds.
- `-Changed` will refuse while Python files are dirty. Commit or stash those, or
  list the patchable files explicitly with `-Files`.
- The update banner still points at the full installer. Patches are a separate,
  deliberate channel - send the `apply_patch.bat` link.
