# Discogs data provenance — what is typed, what is picked

Verified against the live Discogs API on **2026-11-16** (release 5610215 plus a 30-release sample).
Purpose: know which parts of the scraped summary are **safe to match literally** and which ones a
submitter typed, so parsing rules (dropping "Album", grouping editions, matching "Box Set") can be
aimed at the right fields.

---

## 1. Are the fields closed vocabularies?

`/database/search` filters against Discogs' enumerated values. A misspelling returns **0** items while
the real term returns millions, so these are fixed lists rather than free text:

| Filter | Items returned |
|---|---|
| `format=Vinyl` | 8,108,782 |
| `format=Compilation` | 2,387,517 |
| `format=Limited Edition` | 1,176,308 |
| **`format=Pink Marbled`** | **0** |
| `genre=Rock` | 6,383,679 |
| `genre=Rok` | **0** |
| `style=Indie Rock` | 479,001 |
| `style=Indierock` | **0** |
| `country=US` | 4,618,234 |
| `country=U.S.A.` | **0** |

Reading: `Vinyl`, `Compilation`, `Limited Edition`, every genre, every style and every country are
vocabulary terms. The italic format text (`Pink Marbled`) is **not** in that vocabulary at all.

## 2. Structure of a 30-release sample

Values collected from 30 releases pulled through `/releases/{id}` (search terms: rock, jazz,
compilation, cassette, soul, electronic):

```
format name  (2 distinct): Vinyl, CD
descriptions (17 distinct): 7", Record Store Day, Single, Limited Edition, Picture Disc,
                             12", 33⅓ RPM, LP, Album, Stereo, Compilation, 45 RPM,
                             Club Edition, Reissue, Remastered, Mixed, Repress
genres       (7 distinct): Rock, Electronic, Reggae, Pop, Blues, Hip Hop, Latin
styles       (30 distinct): Glam, House, Techno, Acid House, Heavy Metal, Surf, Rock & Roll,
                             Pop Rock, Classic Rock, Psychobilly, Dub, Punk, Doo Wop, Blues Rock,
                             Electro, Folk Rock, Psychedelic Rock, Country Rock, Hard Rock, Arena Rock
countries    (12 distinct): Europe, US, UK, Australia, Brazil, France, Germany, Netherlands,
                             UK & Europe, Canada, Spain, Italy

label rows: 42   ·   rows with a Discogs label id: 42 (all of them)
```

Bounded sets, repeated across unrelated releases. Schema shape tells you the widget:

- **arrays** → multi-select (checkboxes): `formats[].descriptions`, `genres`, `styles`
- **single strings** → single-select (pull-down): `formats[].name`, `country`
- **plain strings with no id** → typed: `title`, `labels[].catno`, `formats[].text`

## 3. Free-text fields, as found in the sample

`formats[].text` is genuinely unconstrained:

```
"Carrollton Pressing", "Red", "Box Set", "Embossed Gatefold",
"Gatefold, Santa Maria Pressing", "Gatefold", "Specialty Pressing, Gatefold",
"Embossed Gatefold, Half Speed Mastered", "MON - Monarch Pressing, Gatefold",
"PRCW, Gatefold", "Embossed Gatefold, 180g", "Gatefold, 180 gr", "Gatefold, SP"
```

Note `"Box Set"`: a vocabulary format name typed into the free-text box. The same word reaches the
API by two different routes, so a literal string match on the whole format line cannot tell them
apart — match `name` when it must be authoritative.

Catalogue numbers are free text too — the sample contained a cat# entered literally as `none`
(the scraper already treats `none` / blank as empty).

`released` is a date field that accepts partial dates: the sample held `1995`, `1972`, `1983`
alongside `2014-04-19`, `2020-03-19`, `2007-10-09`.

---

## 4. Test case — release 5610215

`https://www.discogs.com/release/5610215-Various-Kanine-Records-Presents-Non-Violent-Femmes`

**API payload:**

```
artists[0]   {"name": "Various", "anv": "", "join": "", "id": 194}
title        "Kanine Records Presents Non Violent Femmes"
labels[0]    {"name": "Kanine Records", "catno": "KR107", "id": 55188}
formats[0]   {"name": "Vinyl", "qty": "1",
              "descriptions": ["LP", "Compilation", "Limited Edition"],
              "text": "Pink Marbled"}
country      "US"
released     "2014-04-19"
genres       ["Rock", "Pop"]
styles       ["Shoegaze", "Indie Rock", "Indie Pop", "Alternative Rock", "Psychedelic Rock"]
```

**Output of the real `/scrape` formatting code** (lifted out of `main.py`, not re-implemented):

```
Various - Kanine Records Presents Non Violent Femmes
Label: Kanine Records - KR107
Format: Vinyl, LP, Compilation, Limited Edition, Pink Marbled
Country: US
Released: Apr 19, 2014
Genre: Rock, Pop
Style: Shoegaze, Indie Rock, Indie Pop, Alternative Rock, Psychedelic Rock
Track Count: 11

Tracklist
A1 No Below (Ocean Shitty Demo) 3:17
A2 All I Want 2:09
A3 Goodnight Goodbye 2:43
A4 Sunday 5 3:12
A5 All My Friends Were Punks 2:55
B6 Honey Do (Demo) 3:05
B7 Secret Surprise 2:43
B8 Glynis 3:18
B9 I Came 2:54
B10 Chimera 4:01
B11 If You Had Wings You'd Fly 3:28
```

**Per token:**

| Output token | Field | Entry type |
|---|---|---|
| `Various` | `artists[0].name` (id 194; `anv` empty) | database pick |
| `Kanine Records Presents…` | `title` | **free text** |
| `Kanine Records` | `labels[0].name` (id 55188) | database pick |
| `KR107` | `labels[0].catno` | **free text** |
| `Vinyl` | `formats[0].name` | fixed list |
| `LP`, `Compilation`, `Limited Edition` | `formats[0].descriptions[]` | checkbox multi-select |
| **`Pink Marbled`** | `formats[0].text` | **free text** (italic on the page) |
| `US` | `country` | fixed list |
| `Apr 19, 2014` | `released` (`2014-04-19`) | date entry |
| `Rock, Pop` | `genres[]` | fixed list |
| `Shoegaze, …` | `styles[]` | fixed list |

Only three values in that block were typed by a human: **the title, the catalogue number, and the
format free text**.

---

## 5. Practical rules that follow

1. **Aim string matching at `name` + `descriptions`, never at the whole Format line.** "Album",
   "Compilation", "Box Set" and "Limited Edition" are vocabulary terms there; the same words can
   also appear in `text` by accident.
2. **Pass `formats[].text` through as display text.** It is often already comma-separated
   (`"Gatefold, Santa Maria Pressing"`), so splitting on commas and rejoining with `", "` is safe —
   it only affects duplicate removal, not the visible output.
3. **Country, Genre and Style are safe to match literally** — invalid spellings simply never appear.
4. **`catno` needs defensive handling** — blank / `none` / `N/A` all occur in the wild.
5. **`released` can be a bare year**, so the date formatter keeps `2014` and `Apr 2014` as-is rather
   than padding a missing day.
6. **`anv` is free text** (the "as on release" name variation) and the scraper prefers it over
   `artists[].name`, so an artist line can carry typed spelling on purpose.

## 6. Caveats

- The API cannot report the literal widget. Discogs' submission form needs a login (the public
  release page answers **403** to a scripted request), so "pull-down vs checkbox" here is inferred
  from the schema shape plus the closed value sets above — not from reading the form markup.
- The 30-release sample is a sample. The conclusions are about which fields are *closed*; the exact
  membership of each list was not enumerated.

## 7. How to re-run

The probes used the token from `.env` (`DISCOGS_TOKEN`) as a `Discogs token=` header:

```
# closed vocabulary? nonsense value should return 0 items
GET /database/search?format=Compilation&type=release&per_page=1
GET /database/search?format=Pink%20Marbled&type=release&per_page=1
GET /database/search?genre=Rok&type=release&per_page=1

# one release, full payload
GET /releases/5610215
```
