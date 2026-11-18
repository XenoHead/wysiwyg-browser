"""FastAPI routes for the WalmartAPI page.

Self-contained: nothing here imports ``WalmartSheet`` (protected files) and
nothing in ``main.py`` references this package. ``python -m WalmartAPI`` serves
these two routes on their own port (see ``__main__.py``); wiring them into the
main app is deliberately deferred.

    GET  /walmart-api                  the page
    POST /api/walmart-api/lookup       {"upc": "656605531151"} -> lookup result

Two Walmart calls per lookup, both read-only:

1. ``GET /v3/items/walmart/search`` -- the whole Walmart catalog (is this item
   already sold on Walmart by anyone?).
2. ``GET /v3/items/{upc}?productIdType=UPC`` -- *our* catalog (do we already
   have an offer for it, and is it live?).

The second one 400s on a bad check digit and 4xx on "not ours", so it is
wrapped -- a failed seller lookup is information, not an error.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse

from .walmart_api import WalmartAPI, WalmartAPIError

router = APIRouter()

_client: Optional[WalmartAPI] = None
_client_lock = threading.Lock()


def _get_client() -> WalmartAPI:
    """One client per process so the 15-minute token is reused across scans."""
    global _client
    with _client_lock:
        if _client is None:
            _client = WalmartAPI(timeout=25.0)
        return _client


def resource_path(relative_path: str) -> str:
    """Same resolution order used by WalmartSheet/walmart.py (dev + PyInstaller)."""
    if getattr(sys, "frozen", False):
        base_local = os.path.dirname(sys.executable)
        try:
            base_bundled = sys._MEIPASS  # pyright: ignore[reportAttributeAccessIssue]
        except Exception:
            base_bundled = os.path.abspath(".")
        local_path = os.path.join(base_local, relative_path)
        bundled_path = os.path.join(base_bundled, relative_path)
        if os.path.exists(local_path):
            return local_path
        return bundled_path
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)


@router.get("/walmart-api")
async def serve_walmart_api_page():
    return FileResponse(resource_path(os.path.join("WalmartAPI", "walmart_api.html")))


# --------------------------------------------------------------- lookup core --

def _candidate_queries(digits: str) -> List[Dict[str, str]]:
    """Identifier variants, most-likely first.

    A 12-digit UPC and its 13-digit EAN and 14-digit GTIN are the same barcode.
    Walmart treats them as different query params, so try the shapes we have not
    tried yet until one returns a hit.
    """
    if len(digits) == 12:
        return [{"upc": digits}, {"ean": "0" + digits}, {"gtin": "00" + digits}]
    if len(digits) == 13:
        return [{"ean": digits}, {"upc": digits[1:]}, {"gtin": "0" + digits}]
    if len(digits) == 14:
        return [{"gtin": digits}, {"upc": digits[2:]}, {"ean": digits[1:]}]
    if len(digits) == 8:  # EAN-8
        return [{"upc": digits}, {"ean": digits}]
    return [{"upc": digits}]


def _catalog_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
    return []


def _text(value: Any, limit: Optional[int] = None) -> str:
    """Decode the HTML entities Walmart puts in its free text.

    The catalog/search payloads come back with ``Obituary&apos;s`` and
    ``&quot;senseless gurgles&quot;`` literally in the strings, so a page that
    escapes for HTML renders the entity itself. Decode once, here, and both the
    page and the raw JSON show real characters. The page still escapes on the way
    back into the DOM, so this is not an XSS hole.
    """
    out = html.unescape(str(value if value is not None else ""))
    return out[:limit] if limit else out


def _summarise_catalog_item(item: Dict[str, Any]) -> Dict[str, Any]:
    props = item.get("properties") or {}
    images = item.get("images") or []
    image = ""
    if images and isinstance(images[0], dict):
        image = images[0].get("url", "")
    price = item.get("price")
    amount = price.get("amount") if isinstance(price, dict) else price
    categories = props.get("categories") or []
    return {
        "itemId": item.get("itemId", ""),
        "title": _text(item.get("title")),
        "brand": _text(item.get("brand")),
        "productType": _text(item.get("productType")),
        "price": amount,
        "currency": (price or {}).get("currency") if isinstance(price, dict) else "USD",
        "isMarketPlaceItem": bool(item.get("isMarketPlaceItem")),
        "image": image,
        "categories": [_text(c) for c in categories],
        "description": _text(item.get("description"), 600),
    }


def _summarise_seller_item(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    rows = payload.get("ItemResponse")
    if isinstance(rows, list):
        row = rows[0] if rows else None
    elif isinstance(rows, dict):
        row = rows
    else:
        row = None
    if not row:
        return None

    price = row.get("price") or {}
    reasons = row.get("unpublishedReasons") or {}
    reason_list = reasons.get("reason") if isinstance(reasons, dict) else None
    if isinstance(reason_list, str):
        reason_list = [reason_list]

    return {
        "sku": row.get("sku", ""),
        "itemId": row.get("itemId", ""),
        "wpid": row.get("wpid", ""),
        "productName": _text(row.get("productName")),
        "price": price.get("amount"),
        "currency": price.get("currency", "USD"),
        "publishedStatus": row.get("publishedStatus", ""),
        "lifecycleStatus": row.get("lifecycleStatus", ""),
        "unpublishedReasons": [_text(r) for r in (reason_list or [])],
        "availability": row.get("availability", ""),
        "condition": _text(row.get("condition")),
        "productType": _text(row.get("productType")),
        "shelf": _text(row.get("shelf")),
        "upc": row.get("upc", ""),
        "gtin": row.get("gtin", ""),
    }


def _decide(catalog: List[Dict[str, Any]], seller: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Turn the two lookups into one plain-English verdict."""
    if seller:
        if seller.get("publishedStatus") == "PUBLISHED":
            return {
                "code": "yours-live",
                "headline": "Already yours, and live",
                "detail": "Your offer is published. A second feed would overwrite the existing listing, not create one.",
            }
        if seller.get("publishedStatus"):
            return {
                "code": "yours-unpublished",
                "headline": "Already yours, but not live",
                "detail": "Your offer exists in the catalog but is UNPUBLISHED - fix the listed reason rather than re-listing it.",
            }
    if catalog:
        marketplace = [i for i in catalog if i.get("isMarketPlaceItem")]
        if marketplace:
            return {
                "code": "offer",
                "headline": "In Walmart's catalog - offer only (MP_ITEM_MATCH)",
                "detail": "Another seller already has this item. Add an offer against the existing catalog item; no full item setup needed.",
            }
        return {
            "code": "offer",
            "headline": "In Walmart's catalog - offer only (MP_ITEM_MATCH)",
            "detail": "Walmart (first-party) sells this item, so an offer can be matched against it instead of a full item setup.",
        }
    return {
        "code": "new",
        "headline": "Not in Walmart - full item setup (MP_ITEM)",
        "detail": "No catalog match. This needs a complete MP_ITEM payload, not an offer.",
    }


@router.post("/api/walmart-api/lookup")
async def walmart_api_lookup(data: dict = Body(...)) -> Any:
    raw = str(data.get("upc") or data.get("gtin") or "")
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No digits in that barcode."})
    if not 8 <= len(digits) <= 14:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": f"UPC/GTIN should be 8-14 digits, got {len(digits)}."},
        )

    warnings: List[str] = []
    catalog_items: List[Dict[str, Any]] = []
    used_query: Dict[str, str] = {}

    try:
        api = _get_client()
    except WalmartAPIError as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    # 1. Walmart-wide catalog search, trying identifier variants until one hits.
    for query in _candidate_queries(digits):
        try:
            payload = api.search_catalog(**query)
        except WalmartAPIError as exc:
            # A 400/404 on a derived variant (EAN for a UPC, etc.) is expected
            # noise -- only surface genuine failures.
            if exc.status not in (400, 404):
                warnings.append(f"catalog search {query}: {exc}")
            continue
        items = _catalog_items(payload)
        if items:
            catalog_items = [_summarise_catalog_item(i) for i in items]
            used_query = query
            break
        used_query = query

    # 2. Our own catalog. A 400 here is usually an invalid check digit.
    seller_item: Optional[Dict[str, Any]] = None
    check_digit_error = False
    try:
        seller_item = _summarise_seller_item(api.get_item(digits, id_type="UPC"))
    except WalmartAPIError as exc:
        if exc.status == 400:
            check_digit_error = "check digit" in str(exc.payload).lower()
            if check_digit_error:
                warnings.append("Barcode failed Walmart's check-digit validation - rescan or retype it.")
        elif exc.status != 404:
            warnings.append(f"seller lookup: {exc}")

    decision = _decide(catalog_items, seller_item)
    if decision["code"] == "new" and check_digit_error:
        decision = {
            "code": "invalid",
            "headline": "Barcode failed validation",
            "detail": "Walmart rejected this UPC's check digit, so 'not found' here means nothing. Rescan or retype the number.",
        }

    return {
        "ok": True,
        "upc": digits,
        "matched_query": used_query,
        "decision": decision,
        "catalog": {"found": bool(catalog_items), "items": catalog_items},
        "seller": {"found": bool(seller_item), "item": seller_item},
        "warnings": warnings,
    }


# ------------------------------------------------------------ pending list --

PENDING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending.json")
_pending_lock = threading.Lock()


def _gtin14(digits: str) -> str:
    return digits.zfill(14) if 0 < len(digits) <= 14 else digits


@router.get("/api/walmart-api/pending")
async def walmart_api_pending() -> Any:
    """The staged list, as it stands on disk."""
    with _pending_lock:
        rows = _read_pending()
    return {"ok": True, "pending": len(rows), "items": rows}


@router.post("/api/walmart-api/stage")
async def walmart_api_stage(data: Dict[str, Any] = Body(...)) -> Any:
    """Add a Walmart-catalog hit to the pending list.

    Deliberately local: this writes ``WalmartAPI/pending.json`` and nothing else.
    No catalog write, no feed, and nothing in ``WalmartSheet/`` is touched -- this
    is the input a later submit step would read.

    The card fields come from the page, which already has them from the lookup, so
    adding an item costs no extra Walmart API call.
    """
    digits = re.sub(r"\D", "", str(data.get("upc") or ""))
    if not digits:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No barcode to add."})

    item = data.get("item") if isinstance(data.get("item"), dict) else {}
    record = {
        "upc": digits,
        "gtin": _gtin14(digits),
        "addedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision": str(data.get("decision") or ""),
        "title": str(item.get("title") or ""),
        "brand": str(item.get("brand") or ""),
        "productType": str(item.get("productType") or ""),
        "itemId": str(item.get("itemId") or ""),
        "price": item.get("price"),
        "currency": str(item.get("currency") or "USD"),
        "image": str(item.get("image") or ""),
        "isMarketPlaceItem": bool(item.get("isMarketPlaceItem")),
    }

    with _pending_lock:
        rows = _read_pending()
        existing = next((r for r in rows if r.get("upc") == digits), None)
        if existing:
            existing.update(record)
            added = False
        else:
            rows.append(record)
            added = True
        _write_pending(rows)

    return {
        "ok": True,
        "added": added,
        "pending": len(rows),
        "record": record,
        "file": os.path.relpath(PENDING_FILE, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    }


@router.post("/api/walmart-api/unstage")
async def walmart_api_unstage(data: Dict[str, Any] = Body(...)) -> Any:
    """Drop a staged item -- the Remove side of + Add. Local only, no Walmart call."""
    digits = re.sub(r"\D", "", str(data.get("upc") or ""))
    if not digits:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No barcode to remove."})

    with _pending_lock:
        rows = _read_pending()
        kept = [r for r in rows if r.get("upc") != digits]
        removed = len(kept) != len(rows)
        if removed:
            _write_pending(kept)

    return {"ok": True, "removed": removed, "pending": len(kept), "record": None}


_LISTING_TEXT_LIMITS = {
    "productName": 200,
    "brand": 100,
    "manufacturerPartNumber": 60,
    "genre": 80,
    "sku": 60,
    "shortDescription": 4000,
}
_LISTING_CONDITIONS = ("New", "Refurbished", "Used")


_CREATE_TEXT_LIMITS = {
    "productName": 200,
    "description": 4000,
    "mainImageUrl": 1000,
    "productSubcategory": 120,
    "productType": 60,
    "manufacturerPartNumber": 60,
    "brand": 100,
}
_CREATE_REQUIRED = (
    ("productName", "Product name"),
    ("description", "Description"),
    ("mainImageUrl", "Main image URL"),
    ("productSubcategory", "Product subcategory"),
    ("manufacturerPartNumber", "MPN"),
    ("brand", "Brand name"),
)
_CREATE_FULFILLMENT = ("Seller Fulfilled", "Walmart Fulfilled")


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


@router.post("/api/walmart-api/create")
async def walmart_api_create(data: Dict[str, Any] = Body(...)) -> Any:
    """Save the "Create item" screen for a barcode Walmart does not carry.

    Mirrors the required attributes only -- the same fields Walmart's Seller
    Center asks for before it will list a new Music item. Local, like everything
    else here: the record lands in ``WalmartAPI/pending.json`` and a later feed
    builder would turn it into an ``MP_ITEM`` payload.
    """
    digits = re.sub(r"\D", "", str(data.get("upc") or ""))
    if not digits or not 8 <= len(digits) <= 14:
        return JSONResponse(status_code=400, content={"ok": False, "error": "UPC/GTIN should be 8-14 digits."})

    form = data.get("listing") if isinstance(data.get("listing"), dict) else {}

    listing: Dict[str, Any] = {}
    for key, limit in _CREATE_TEXT_LIMITS.items():
        listing[key] = str(form.get(key) or "").strip()[:limit]

    missing = [label for key, label in _CREATE_REQUIRED if not listing[key]]
    if missing:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Required: " + ", ".join(missing) + "."},
        )

    if not listing["mainImageUrl"].lower().startswith(("http://", "https://")):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Main image URL must start with http:// or https://."},
        )

    if not _is_true(form.get("certified")):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Tick the certification box before creating the item."},
        )

    fulfillment = str(form.get("fulfillmentOperation") or "").strip()
    listing["fulfillmentOperation"] = (
        fulfillment if fulfillment in _CREATE_FULFILLMENT else "Seller Fulfilled"
    )
    listing["certified"] = True

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _pending_lock:
        rows = _read_pending()
        record = next((r for r in rows if r.get("upc") == digits), None)
        if record is None:
            record = {
                "upc": digits,
                "gtin": _gtin14(digits),
                "addedAt": now,
                "decision": "new-item",
                "source": "create",
                "itemId": "",
                "price": None,
                "currency": "USD",
                "isMarketPlaceItem": False,
            }
            rows.append(record)
        record.update({
            "decision": "new-item",
            "source": "create",
            "title": listing["productName"],
            "brand": listing["brand"],
            "productType": listing["productType"],
            "image": listing["mainImageUrl"],
            "listing": listing,
            "submittedAt": now,
        })
        _write_pending(rows)

    return {"ok": True, "record": record, "pending": len(rows)}


@router.post("/api/walmart-api/submit")
async def walmart_api_submit(data: Dict[str, Any] = Body(...)) -> Any:
    """Save the item-setup form against a staged record.

    Still local: this stores what the fields said on ``WalmartAPI/pending.json``
    and echoes it back so the page can render it as "Your listing". Nothing is
    sent to Walmart -- a real submit would build an MP_ITEM feed from this record.
    """
    digits = re.sub(r"\D", "", str(data.get("upc") or ""))
    if not digits:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No barcode to submit."})

    form = data.get("listing") if isinstance(data.get("listing"), dict) else {}

    listing: Dict[str, Any] = {}
    for key, limit in _LISTING_TEXT_LIMITS.items():
        listing[key] = str(form.get(key) or "").strip()[:limit]

    if not listing["productName"]:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Product Name is required."})
    if not listing["sku"]:
        return JSONResponse(status_code=400, content={"ok": False, "error": "SKU is required."})

    raw_price = str(form.get("price") or "").replace("$", "").replace(",", "").strip()
    try:
        price = round(float(raw_price), 2)
    except ValueError:
        price = 0.0
    if not math.isfinite(price) or price <= 0:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Selling Price must be greater than 0."})
    listing["price"] = f"{price:.2f}"

    try:
        raw_qty = float(str(form.get("quantity") or "0"))
        quantity = max(0, int(raw_qty)) if math.isfinite(raw_qty) else 0
    except (ValueError, OverflowError):
        quantity = 0
    listing["quantity"] = quantity

    condition = str(form.get("condition") or "New").strip()
    listing["condition"] = condition if condition in _LISTING_CONDITIONS else "New"

    with _pending_lock:
        rows = _read_pending()
        record = next((r for r in rows if r.get("upc") == digits), None)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "That barcode is not in the pending list."},
            )
        record["listing"] = listing
        record["submittedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_pending(rows)

    return {"ok": True, "record": record, "pending": len(rows)}


def _read_pending() -> List[Dict[str, Any]]:
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def _write_pending(rows: List[Dict[str, Any]]) -> None:
    tmp = PENDING_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, PENDING_FILE)
