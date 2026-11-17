# WalmartAPI — what Walmart's Marketplace API can do for us

Scratchpad turned reference. Everything below was checked against Walmart's live
docs **and** against our own seller account on 17 Nov 2026 (read-only calls).

---

## 1. Short version

We are a **seller with our own app keys**, not a Solution Provider. That means:

- **No OAuth redirect dance.** The page you were reading
  (`/docs/oauth-authorization`) describes *approved Solution Providers* acting on
  someone else's behalf — `walmartCallbackUri`, `sellerId`, authorization codes,
  refresh tokens. None of that applies to us.
- Instead: **`grant_type=client_credentials`**, one POST, 900-second bearer token.
  No sellerId, no refresh token, no callback URL.
- **Verified working** with the keys already in `.env` (`WALMART_CLIENT_ID`,
  `WALMART_CLIENT_SECRET`): `HTTP 200`, `expires_in: 900`, `token_type: Bearer`.

```
POST https://marketplace.walmartapis.com/v3/token
Authorization: Basic base64(client_id:client_secret)
WM_SVC.NAME: Walmart Marketplace
WM_QOS.CORRELATION_ID: <uuid4>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

Then every call carries:

| Header | Value |
|---|---|
| `WM_SEC.ACCESS_TOKEN` | the raw token (15 min life) |
| `WM_SVC.NAME` | `Walmart Marketplace` |
| `WM_QOS.CORRELATION_ID` | fresh uuid4 per request (for support/debugging) |
| `WM_MARKET` | `us` |
| `WM_GLOBAL_VERSION` | `3.1` |
| `Accept` | `application/json` |
| `WM_CONSUMER.CHANNEL_TYPE` | optional; ours is in the feed history if it's ever needed |

---

## 2. What our account actually looks like

Read from the API, not guessed:

| Fact | Value |
|---|---|
| Items in catalog | **11,875** (`GET /v3/items/count?status=ALL`) |
| Product type | `Music` — e.g. `Braids - Deep In The Iris - Music & Performance - Vinyl` |
| Shelf/category | `Home Page/Music/Rock Music/All Rock Music` |
| Partner ID (virtual node) | `10001373153` |
| Channel type | `57c99571-b460-43e2-bcd6-7d12f3ddd5a9` |
| Feed history | 403 feeds so far — `MP_ITEM`, `DELETE_ITEM`, … |
| Item spec version in use | `5.0.20260829-12_49_39` |
| Paging | `limit` (max 200) + `offset`, response has `totalItems` |

Two things worth noticing in the data:

1. **There are unpublished items.** Example: `1740-MP2022-1230-1135` at
   `$199.98` is `UNPUBLISHED` because it trips Walmart's *Pricing Rule*
   (price-gouging guard). The API reports the exact reason verbatim, so an audit
   pass is genuinely useful.
2. **Catalog search already finds our own listings** by UPC
   (`isMarketPlaceItem: true`), which is how the offer-setup-vs-full-setup
   decision gets made automatically.

---

## 3. What we can do — capability map

Everything is `https://marketplace.walmartapis.com`. ✅ = useful to us, 💤 = ignore for now.

### Items / catalog ✅

| What | Call |
|---|---|
| Read one item by SKU / GTIN / UPC / EAN / ISBN / item ID | `GET /v3/items/{id}?productIdType=SKU` |
| Walk the whole catalog | `GET /v3/items?limit=200&offset=n` |
| Count by status | `GET /v3/items/count?status=ALL` |
| Does Walmart already sell this? (offer vs full setup) | `GET /v3/items/walmart/search?upc=…` |
| …and get a ready-to-edit payload back | `…&responseFormat=SPEC` (US only) |
| Full item create | `POST /v3/feeds?feedType=MP_ITEM` |
| Partial update (name, description, genre, features…) | `POST /v3/feeds?feedType=MP_MAINTENANCE` |
| Offer-only for an existing Walmart item | `POST /v3/feeds?feedType=MP_ITEM_MATCH` |
| Retire / delete | `feedType=RETIRE_ITEM` / `DELETE_ITEM` |
| Required attributes per product type (JSON Schema) | `POST /v3/items/spec` |
| Category → product type tree | `GET /v3/utilities/taxonomy` |
| Read the feed result per SKU | `GET /v3/feeds/{feedId}?includeDetails=true` |

### Price / inventory ✅

| What | Call |
|---|---|
| Set one price | `PUT /v3/price` → `{sku, pricing:[{currentPriceType, currentPrice}]}` |
| Bulk price | `POST /v3/feeds` (`SKU_PRICING`-style feed) |
| Set one inventory | `PUT /v3/inventory` → `{sku, quantity:{unit:"EACH", amount:n}}` |
| Read inventory | `GET /v3/inventory?sku=…` |
| Bulk inventory | `POST /v3/feeds` |
| Promotions / incentives / repricer | separate APIs, exist, not needed yet |

Price and inventory are **synchronous** — a 200 means it landed (price takes up
to 5 min to show on site). Item changes are **asynchronous feeds** — you get a
`feedId` and poll.

### Insights / reports ✅ (later)

- Listing Quality score + per-item issues → `POST /v3/insights/items/listingQuality/items`
  — note **1 request per minute** in the US, so cache it.
- On-request reports (item performance, buy box, search insights) — request, poll, download.
- Seller performance metrics (OTD, cancellations, returns).

### Orders / returns / shipping 💤

Real and complete (acknowledge, ship, cancel, refund, buy labels, WFS inbound),
but FYR is not order-fulfilling through this app. Park it.

---

## 4. Limits and gotchas

- **Token: 900 s.** Refresh proactively; the client does this with a 60 s margin.
- **Rate limits** are per seller per API, token-bucket, `429` on overflow, and the
  response headers `x-current-token-count` / `X-Next-Replenishment-Time` tell you
  where you stand. Feeds status is generous (5000/min); listing-quality is 1/min.
- **Feeds are async and can be slow.** Docs suggest polling at 15 min → 1 h → 2 h
  → 4 h. `MP_ITEM` up to 10,000 items / 25 MB per file.
- **Compliance review** can freeze an item for up to 24 h
  (`ingestionStatus: INPROGRESS` + `pendingStatusDescription`). Edits bounce until it clears.
- **Sandbox** (`sandbox.walmartapis.com`) is **read-only mock data** with separate
  credentials — no writes, no persistence. Useful for parsing tests only.
- **Price fields are cents-free floats** (`amount: 199.98`), currency `USD`.
- **`MP_ITEM` needs the matching header version.** Our account uses
  `5.0.20260829-12_49_39`; it is pinned in `walmart_api.py`. Re-check with
  `spec()` when Walmart publishes a new one, or payloads get rejected.

---

## 5. How to use this module

Three pieces:

- `walmart_api.py` — the client (token cache, retries on 429/5xx, one method per
  endpoint above, `WalmartAPIError` carrying Walmart's own error text).
- `routes.py` — two routes, no app wiring: `GET /walmart-api` (the page) and
  `POST /api/walmart-api/lookup` (the lookup).
- `cli.py` — smoke tests. Reads are open; catalog writes need `--yes`.

This package is **kept outside the main app on purpose** — `main.py`,
`WYSIWYG.spec` and `install.py` do not reference it. How it should be worked in
is still open, so it runs on its own port in the meantime.

### Standalone runner

```powershell
!run-walmart.bat                        # double-click, or run from a shell
!run-walmart.bat 8010                   # another port
!run-walmart.bat -n                     # don't open a browser
```

Or without the batch file:

```powershell
.venv311\Scripts\python -m WalmartAPI            # http://127.0.0.1:8009/walmart-api
.venv311\Scripts\python -m WalmartAPI --open     # same, opens the browser
.venv311\Scripts\python -m WalmartAPI --port 8010 --sandbox
```

`__main__.py` builds a small FastAPI app holding just the two routes and serves
it on **8009** (8008 belongs to the main app). `GET /` redirects to the page, and
the FastAPI docs are at `/docs`. Credentials still come from the repo-root
`.env`, so the working directory does not matter.

### The page

**`http://127.0.0.1:8009/walmart-api`** when run standalone.

Scan or type a UPC / EAN / GTIN; it runs by itself at 12–14 digits, or on Enter.
Each lookup makes exactly two read-only calls:

1. `GET /v3/items/walmart/search` — is this barcode in the Walmart catalog at all?
   Tries the UPC / EAN / GTIN spelling of the same number until one hits, because
   Walmart treats them as separate query params.
2. `GET /v3/items/{upc}?productIdType=UPC` — do *we* already have an offer?

One verdict banner, one of five:

| Banner | Meaning | Next move |
|---|---|---|
| `yours-live` | Ours, published | Nothing to do — a feed would overwrite it |
| `yours-unpublished` | Ours, but dead | Fix the reason shown (e.g. pricing rule) |
| `offer` | Someone else's / Walmart's | `MP_ITEM_MATCH` — offer only |
| `new-item` | Nowhere | `MP_ITEM` — full item setup |
| `invalid` | Bad check digit | Rescan; "not found" is meaningless here |

Below that: a "Walmart catalog" panel (title, brand, type, price, item ID, image,
link to walmart.com) and a "Your listing" panel (SKU, status, price, stock, and
Walmart's verbatim unpublished reason), plus raw JSON and clickable session chips.

```
# from the repo root, with the venv
.venv311\Scripts\python -m WalmartAPI.cli token
.venv311\Scripts\python -m WalmartAPI.cli count
.venv311\Scripts\python -m WalmartAPI.cli items --limit 10
.venv311\Scripts\python -m WalmartAPI.cli item 1740-MP2022-1230-1135
.venv311\Scripts\python -m WalmartAPI.cli search --upc 656605531151
.venv311\Scripts\python -m WalmartAPI.cli inventory 1740-MP2022-1230-1135
.venv311\Scripts\python -m WalmartAPI.cli feeds --limit 5
.venv311\Scripts\python -m WalmartAPI.cli spec --product-types Music
```

Writes (deliberately awkward to type by accident):

```
.venv311\Scripts\python -m WalmartAPI.cli inv-set <sku> 3 --yes
.venv311\Scripts\python -m WalmartAPI.cli price <sku> 24.98 --yes
```

From Python:

```python
from WalmartAPI import WalmartAPI

api = WalmartAPI()                                   # reads WALMART_* from env / .env
item = api.get_item("1740-MP2022-1230-1135")         # dict, straight from Walmart
count = api.item_count("PUBLISHED")
for row in api.iter_items(page_size=200):            # walks all 11,875
    ...

hit = api.search_catalog(upc="656605531151", spec=True)   # MP_ITEM vs MP_ITEM_MATCH
feed = api.submit_item_feed([...], feed_type="MP_MAINTENANCE")
api.wait_for_feed(feed["feedId"])
```

Nothing here imports `WalmartSheet/` and nothing there was touched.

---

## 6. Roadmap — how this actually helps FYR

Ordered by value per unit of risk. Each is a separate decision.

1. **Audit** *(read-only, zero risk)*
   Pull all 11,875 items, write `sku, productName, price, publishedStatus,
   unpublishedReasons, productType` to JSON/CSV. First real win: a list of every
   unpublished item and *why* — starting with the pricing-rule ones.

2. **Lookup before listing** *(read-only)* — **done: the `/walmart-api` page.**
   `search_catalog(upc=…, spec=True)` answers "offer-only or full setup?" in one
   call, and hands back the attributes Walmart already knows. Extending the page
   later: the `SPEC` variant so it can prefill a Walmart Sheet row.

3. **Price + inventory sync** *(sync writes, reversible)*
   The safe direction: our price/stock → Walmart. No feeds, immediate confirmation.

4. **Listing maintenance** *(feeds — this is the big one)*
   `MP_MAINTENANCE` for Name / Site Description / Key Features / Music Genre on
   existing SKUs, using the same field names the Walmart Sheet already produces.
   Genre fixes, description cleanups and "Hijacked genre" repairs become scriptable
   instead of one-by-one.

5. **Item creation from the WysiWyg data**
   `MP_ITEM` feed built from a history entry. This is the automated Walmart
   exporter the SESSION_NOTES have been chasing — but only after (2) and (4) have
   proven the payload shape against real SKUs.

**Not doing:** orders/fulfilment/WFS, promotions, advertising, repricers.

---

## 7. Loose end worth knowing

`WalmartSheet/walmart.py` defines an `APIRouter` (`/walmart-sheet`,
`/api/walmart/process-item`, …) that **is no longer included anywhere**.
`main.py` had it up to commit `2710fbc`; commit `a702bdc` ("WysiScan overhaul…")
rewrote `main.py` without it, so those routes have been dead since. The page
files and the UI are still there, so it fails as a 404 rather than breaking.

I have not touched any of it — `WalmartSheet/` is on the do-not-edit list in
`docs/CONVENTIONS.md`. But if the Walmart Sheet is still expected to work from
`main.py`, that's a two-line fix in a separate change.
