# Plan: Media Condition Phrase Logic (Mirror Sleeve Condition Logic)

## Goal
Copy the Sleeve Condition multiselect + text box logic to the Media Description text box + Media Condition multiselects, creating a `mediaconditionPhrase` that appears **directly after the media type** in the generated description.

## Current State Analysis

### Data Flow Differences
| Aspect | Sleeve Condition | Media Condition |
|--------|------------------|-----------------|
| Multiselect | `sleeveConditionOptions` (synced to legacy `lpOptions`/`cdOptions`/`customOptions`) | `mediaConditionOptions` (NOT synced, uses separate `customOptionsData.mediaCondition`) |
| Text Box | `sleeveDesc` (manual entry) | `mediaDescriptionText` (manual entry) |
| Legacy Collection | Included in `customOptionsSelected` | NOT included in `customOptionsSelected` |
| Processing | In `processFormatData` lines 2047-2100 | Needs new logic |
| Output Placement | After `sleevePkg` + `sleeveTypeLabel` (Case B) or appended to `sleeveDesc` (Case A) | **NEW**: After `finalFormatString` (media type) |

### Example Target Output
```
Used Like New 1989 USA Reissue Cassette %mediaconditionPhrase% Very Good JCard %conditionPhrase% is Out-of-Print with 6 Tracks - Epic PET 36973
```

## Implementation Plan

### 1. Collect Media Condition Selections in `generateListingData`
Add new input `mediaCustomOptionsSelected` collecting from `mediaConditionOptions` multiselect.

```javascript
// Line ~1845 in generateListingData()
mediaCustomOptionsSelected: [
    ...Array.from(document.getElementById('mediaConditionOptions')?.selectedOptions || []).map(o => o.value)
]
```

### 2. Pass Through to `processFormatData`
Update destructuring at line 1928 to include `mediaCustomOptionsSelected`.

### 3. Create `mediaconditionPhrase` in `processFormatData`
Add new logic block mirroring lines 2047-2100 but for media conditions:

```javascript
// After sleeve condition logic (around line 2101)
let mediaconditionPhrase = "";
if (mediaCustomOptionsSelected && mediaCustomOptionsSelected.length > 0) {
    let mediaFlaws = [];
    mediaCustomOptionsSelected.forEach(optJson => {
        try {
            const opt = JSON.parse(optJson);
            if (opt.title === "Final Sale") {
                // FINAL SALE rule: append to mediaconditionPhrase (was finalFormatString)
                // or handle specially per user requirement
                mediaconditionPhrase = (mediaconditionPhrase ? mediaconditionPhrase + " " : "") + opt.text;
            } else {
                if (opt.text) mediaFlaws.push(opt.text);
                else mediaFlaws.push(opt.title);
            }
        } catch (e) { }
    });

    if (mediaFlaws.length > 0) {
        mediaFlaws = groupFlaws(mediaFlaws);
        const combinedMediaFlaws = mediaFlaws.length === 1
            ? mediaFlaws[0]
            : mediaFlaws[0] + " & " + mediaFlaws.slice(1).join(" / ");
        
        // Placement logic mirroring sleeve:
        const hasMediaCond = inputs.mediaCond && inputs.mediaCond.trim() !== "";
        const hasMediaDesc = mediaDesc && mediaDesc.trim() !== "";
        
        if (hasMediaCond && hasMediaDesc) {
            // Case A: mediaDesc present -> append to mediaDesc with " & "
            mediaDesc += (mediaFlaws.length === 1)
                ? ' & ' + mediaFlaws[0]
                : ' & ' + mediaFlaws[0] + ' / ' + mediaFlaws.slice(1).join(' / ');
        } else if (hasMediaCond && !hasMediaDesc) {
            // Case B: mediaCond set, mediaDesc BLANK -> store in mediaconditionPhrase
            mediaconditionPhrase = combinedMediaFlaws;
        } else if (mediaDesc) {
            // mediaDesc only
            mediaDesc += " & " + combinedMediaFlaws;
        } else {
            // Fallback: attach to finalFormatString
            finalFormatString += " with " + combinedMediaFlaws;
        }
    }
}
```

### 4. Return `mediaconditionPhrase` from `processFormatData`
Add to return object (line 2107-2116).

### 5. Insert in `assembleDescription`
Modify both Case A and Case B to include `mediaconditionPhrase` after `finalFormatString`:

```javascript
// Case B (conditionPhrase exists) - lines 2130-2141
parts = [
    inputs.mediaCond,
    fmtData.pkgFeature,
    fmtData.edition,
    inputs.year,
    country,
    fmtData.finalFormatString,
    fmtData.mediaconditionPhrase || '',  // NEW
    fmtData.mediaDesc,
    inputs.sleeveCond,
    fmtData.sleeveTypeLabel,
    sleeveTail ? sleeveTail : ''
];

// Case A (default) - lines 2145-2157
parts = [
    inputs.mediaCond,
    fmtData.pkgFeature,
    fmtData.edition,
    inputs.year,
    country,
    fmtData.finalFormatString,
    fmtData.mediaconditionPhrase || '',  // NEW
    fmtData.mediaDesc,
    inputs.sleeveCond,
    fmtData.sleevePkg,
    fmtData.sleeveTypeLabel,
    fmtData.sleeveDesc
];
```

### 6. Update `assembleWalmartDescription` (Optional)
Add `fmtData.mediaconditionPhrase` after `finalFormatString` for Walmart export.

### 6. Handle "FINAL SALE" Rule
Currently (line 2054-2055): `finalFormatString += " " + opt.text;`
For media: apply to `mediaconditionPhrase` instead (or in addition to existing behavior).

## Key Decisions Needed

1. **FINAL SALE handling**: Should "Final Sale" media conditions go into `mediaconditionPhrase` only, or also stay in `finalFormatString`?
   - **Recommendation**: Move to `mediaconditionPhrase` exclusively (matching new placement after media type)

2. **Case A/B logic for media**: Mirror sleeve exactly?
   - **Recommendation**: Yes, mirror exactly:
     - `hasMediaCond` = `inputs.mediaCond` (dropdown) is set
     - `hasMediaDesc` = `mediaDescriptionText` is set
     - Case A: mediaDesc present → append to mediaDesc with " & "
     - Case B: mediaCond set, mediaDesc blank → `mediaconditionPhrase` after media type
     - Other fallbacks as per sleeve logic

3. **Empty mediaDesc + no mediaCond but mediaFlaws exist**: Attach to `finalFormatString` with " with " (mirrors sleevePkg fallback)

4. **Walmart description**: Include `mediaconditionPhrase`?

## Files to Modify
- `app.js`: `generateListingData()` (collect selections), `processFormatData()` (new logic), `assembleDescription()` (insert phrase), `assembleWalmartDescription()` (optional)

## Validation Scenarios
| Scenario | Expected mediaconditionPhrase Placement |
|----------|----------------------------------------|
| MediaCond dropdown SET, mediaDesc BLANK, media multiselect has flaws | After media type (finalFormatString), before sleeveCond |
| MediaCond dropdown SET, mediaDesc SET, media multiselect has flaws | Appended to mediaDesc with " & " |
| MediaCond dropdown EMPTY, mediaDesc SET, media multiselect has flaws | Appended to mediaDesc with " & " |
| No mediaCond, no mediaDesc, media multiselect has flaws | Attached to finalFormatString with " with " |
| "Final Sale" in media multiselect | In mediaconditionPhrase (after media type) |