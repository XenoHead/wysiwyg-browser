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

import os
import re
import sys
import threading
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


def _summarise_catalog_item(item: Dict[str, Any]) -> Dict[str, Any]:
    props = item.get("properties") or {}
    images = item.get("images") or []
    image = ""
    if images and isinstance(images[0], dict):
        image = images[0].get("url", "")
    price = item.get("price")
    amount = price.get("amount") if isinstance(price, dict) else price
    return {
        "itemId": item.get("itemId", ""),
        "title": item.get("title", ""),
        "brand": item.get("brand", ""),
        "productType": item.get("productType", ""),
        "price": amount,
        "currency": (price or {}).get("currency") if isinstance(price, dict) else "USD",
        "isMarketPlaceItem": bool(item.get("isMarketPlaceItem")),
        "image": image,
        "categories": props.get("categories") or [],
        "description": (item.get("description") or "")[:600],
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
        "productName": row.get("productName", ""),
        "price": price.get("amount"),
        "currency": price.get("currency", "USD"),
        "publishedStatus": row.get("publishedStatus", ""),
        "lifecycleStatus": row.get("lifecycleStatus", ""),
        "unpublishedReasons": reason_list or [],
        "availability": row.get("availability", ""),
        "condition": row.get("condition", ""),
        "productType": row.get("productType", ""),
        "shelf": row.get("shelf", ""),
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
