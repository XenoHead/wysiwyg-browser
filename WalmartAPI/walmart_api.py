"""Walmart Marketplace API client -- seller (client-credentials) flow.

Why this shape
--------------
The credentials in the repo-root ``.env`` (``WALMART_CLIENT_ID`` /
``WALMART_CLIENT_SECRET``) belong to an app created inside *our own* Seller
Center account. That is the "Get started as a seller" path, so the OAuth 2.0
authorization-code dance described at
https://developer.walmart.com/global-marketplace/docs/oauth-authorization
does **not** apply -- that page is for approved Solution Providers acting on
someone else's behalf.

What we do instead: one POST to ``/v3/token`` with
``grant_type=client_credentials`` and HTTP Basic auth. Response is
``{access_token, token_type, expires_in}`` -- 900 seconds, no refresh token,
no sellerId, no redirect URI. Verified against the live account.

Every other call carries ``WM_SEC.ACCESS_TOKEN`` plus the three header
staples ``WM_SVC.NAME``, ``WM_QOS.CORRELATION_ID``, ``Accept``.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional

import httpx

PROD_BASE = "https://marketplace.walmartapis.com"
SANDBOX_BASE = "https://sandbox.walmartapis.com"

TOKEN_PATH = "/v3/token"
DEFAULT_MARKET = "us"
DEFAULT_SERVICE = "Walmart Marketplace"
DEFAULT_GLOBAL_VERSION = "3.1"

# Seen in this account's own MP_ITEM feed history (GET /v3/feeds). Pinned so
# payloads do not drift; confirm with WalmartAPI.spec() when they publish a new
# one.
DEFAULT_SPEC_VERSION = "5.0.20260829-12_49_39"


class WalmartAPIError(RuntimeError):
    """Non-2xx response, with Walmart's structured error text preserved."""

    def __init__(self, status: int, payload: Any, url: str = ""):
        self.status = status
        self.payload = payload
        self.url = url
        super().__init__(f"{status} {_squash_errors(payload) or 'request failed'} [{url}]")


def _squash_errors(payload: Any) -> str:
    """Turn Walmart's error body into one readable line."""
    if isinstance(payload, dict):
        for key in ("error", "errors"):
            block = payload.get(key)
            if isinstance(block, dict):
                block = [block]
            if isinstance(block, list):
                parts = []
                for e in block:
                    if not isinstance(e, dict):
                        parts.append(str(e))
                        continue
                    code = e.get("code") or ""
                    desc = e.get("description") or e.get("info") or ""
                    field = e.get("field") or ""
                    line = " ".join(x for x in (code, desc) if x).strip()
                    if field:
                        line += f" (field: {field})"
                    parts.append(line)
                if parts:
                    return " | ".join(parts)
        if payload.get("message"):
            return str(payload["message"])
    return str(payload)[:400] if payload is not None else ""


def load_env(paths: Optional[List[str]] = None) -> Dict[str, str]:
    """Read ``KEY=VALUE`` pairs without adding a python-dotenv dependency.

    Mirrors ``_load_env_file()`` in ``main.py``: real environment variables win,
    a ``.env`` only fills gaps. When running under the app, ``main.py`` has
    already populated ``os.environ``; this keeps the CLI working standalone.
    """
    found: Dict[str, str] = {}
    if paths is None:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)  # repo root
        exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None
        candidates = [os.path.join(root, ".env"), os.path.join(os.getcwd(), ".env")]
        if exe_dir:
            candidates.append(os.path.join(exe_dir, ".env"))
        paths = candidates

    for path in paths:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in found and k not in os.environ:
                        found[k] = v
        except OSError:
            continue
    return found


class WalmartAPI:
    """Thin, boring wrapper around the Marketplace REST endpoints.

    Read methods are safe. Write methods (inventory, price, feeds) change the
    live catalog -- the CLI gates them behind ``--yes``.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        market: str = DEFAULT_MARKET,
        base_url: str = PROD_BASE,
        channel_type: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        env: Optional[Dict[str, str]] = None,
    ):
        env = env if env is not None else load_env()
        self.client_id = client_id or os.environ.get("WALMART_CLIENT_ID") or env.get("WALMART_CLIENT_ID", "")
        self.client_secret = (
            client_secret
            or os.environ.get("WALMART_CLIENT_SECRET")
            or env.get("WALMART_CLIENT_SECRET", "")
        )
        if not self.client_id or not self.client_secret:
            raise WalmartAPIError(
                0,
                {"error": "WALMART_CLIENT_ID / WALMART_CLIENT_SECRET not found in environment or .env"},
            )

        self.market = market
        self.base_url = base_url.rstrip("/")
        self.channel_type = channel_type
        self.timeout = timeout
        self.max_retries = max_retries

        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- auth --

    @property
    def access_token(self) -> str:
        """Cached bearer token, renewed 60 s before the 900 s expiry."""
        with self._lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            self._token, expires_in = self._fetch_token()
            self._token_expires_at = time.time() + max(30.0, expires_in - 60.0)
            return self._token

    def _fetch_token(self) -> tuple:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {basic}",
            "WM_SVC.NAME": DEFAULT_SERVICE,
            "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.channel_type:
            headers["WM_CONSUMER.CHANNEL_TYPE"] = self.channel_type

        url = self.base_url + TOKEN_PATH
        resp = httpx.post(url, headers=headers, data={"grant_type": "client_credentials"}, timeout=self.timeout)
        payload = _json_or_text(resp)
        if resp.status_code >= 400:
            raise WalmartAPIError(resp.status_code, payload, url)

        value = payload
        if isinstance(payload, dict) and not payload.get("access_token"):
            # Some responses wrap the token: {"clientCredentialsRes": {"value": {...}}}
            for key in ("clientCredentialsRes", "tokenAPIRes", "value"):
                inner = payload.get(key)
                if isinstance(inner, dict):
                    value = inner.get("value", inner) if isinstance(inner.get("value"), dict) else inner
                    if isinstance(value, dict) and value.get("access_token"):
                        break
        if not isinstance(value, dict) or not value.get("access_token"):
            raise WalmartAPIError(resp.status_code, payload, url)
        return value["access_token"], int(value.get("expires_in") or 900)

    def token_info(self) -> Dict[str, Any]:
        """Token metadata without leaking the token itself (for CLI/debug)."""
        started = time.time()
        token = self.access_token
        return {
            "obtained": True,
            "expires_in_approx": int(max(0, self._token_expires_at - time.time())),
            "token_length": len(token),
            "market": self.market,
            "base_url": self.base_url,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # ------------------------------------------------------------- plumbing --

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "WM_SEC.ACCESS_TOKEN": self.access_token,
            "WM_SVC.NAME": DEFAULT_SERVICE,
            "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
            "WM_MARKET": self.market,
            "WM_GLOBAL_VERSION": DEFAULT_GLOBAL_VERSION,
            "Accept": "application/json",
        }
        if self.channel_type:
            headers["WM_CONSUMER.CHANNEL_TYPE"] = self.channel_type
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        files: Any = None,
        accept: str = "application/json",
        retries: Optional[int] = None,
    ) -> Any:
        """One API call with retry/backoff on 429 and 5xx."""
        url = self.base_url + path
        attempts = self.max_retries if retries is None else max(1, retries)
        last_error: Optional[WalmartAPIError] = None

        for attempt in range(attempts):
            headers = self._headers({"Accept": accept})
            resp = httpx.request(
                method,
                url,
                headers=headers,
                params=_clean_params(params),
                json=json_body,
                files=files,
                timeout=self.timeout,
            )
            payload = _json_or_text(resp)

            if resp.status_code < 400:
                return payload

            last_error = WalmartAPIError(resp.status_code, payload, url)

            if resp.status_code == 401 and attempt == 0:
                with self._lock:  # token died early -- force one refresh
                    self._token = None
                    self._token_expires_at = 0.0
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
                time.sleep(min(delay, 30.0))
                continue
            break

        assert last_error is not None
        raise last_error

    # --------------------------------------------------------------- reads --

    def get_items(self, limit: int = 200, offset: int = 0, **params: Any) -> Dict[str, Any]:
        """GET /v3/items -- one page. ``limit`` caps at 200 server-side."""
        query = {"limit": limit, "offset": offset}
        query.update({k: v for k, v in params.items() if v is not None})
        return self.request("GET", "/v3/items", params=query)

    def iter_items(self, page_size: int = 200, **params: Any) -> Iterator[Dict[str, Any]]:
        """Walk the whole seller catalog, newest page first."""
        offset = 0
        while True:
            page = self.get_items(limit=page_size, offset=offset, **params)
            rows = page.get("ItemResponse") or []
            if not rows:
                return
            for row in rows:
                yield row
            offset += len(rows)
            total = page.get("totalItems")
            if isinstance(total, int) and offset >= total:
                return

    def get_item(self, identifier: str, id_type: str = "SKU", **params: Any) -> Dict[str, Any]:
        """GET /v3/items/{id} -- id_type: SKU | GTIN | UPC | EAN | ISBN | ITEM_ID."""
        query = {"productIdType": id_type}
        query.update({k: v for k, v in params.items() if v is not None})
        return self.request("GET", f"/v3/items/{identifier}", params=query)

    def item_count(self, status: str = "ALL") -> int:
        """GET /v3/items/count -- status is mandatory (ALL | PUBLISHED | UNPUBLISHED ...)."""
        payload = self.request("GET", "/v3/items/count", params={"status": status})
        if isinstance(payload, dict):
            return int(payload.get(status, payload.get("count", 0)) or 0)
        return 0

    def search_catalog(
        self,
        upc: Optional[str] = None,
        gtin: Optional[str] = None,
        ean: Optional[str] = None,
        isbn: Optional[str] = None,
        asin: Optional[str] = None,
        query: Optional[str] = None,
        spec: bool = False,
    ) -> Dict[str, Any]:
        """GET /v3/items/walmart/search -- does Walmart already have this item?

        ``spec=True`` (US only) returns a ready MP_ITEM / MP_ITEM_MATCH payload
        instead of the light catalog hit.
        """
        params: Dict[str, Any] = {}
        for key, value in (("upc", upc), ("gtin", gtin), ("ean", ean), ("isbn", isbn), ("asin", asin), ("query", query)):
            if value:
                params[key] = value
        if not params:
            raise ValueError("search_catalog needs one of upc/gtin/ean/isbn/asin/query")
        if spec:
            params["responseFormat"] = "SPEC"
        return self.request("GET", "/v3/items/walmart/search", params=params)

    def get_inventory(self, sku: str, ship_node: Optional[str] = None) -> Dict[str, Any]:
        params = {"sku": sku}
        if ship_node:
            params["shipNode"] = ship_node
        return self.request("GET", "/v3/inventory", params=params)

    def list_feeds(self, feed_type: Optional[str] = None, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if feed_type:
            params["feedType"] = feed_type
        return self.request("GET", "/v3/feeds", params=params)

    def feed_status(self, feed_id: str, include_details: bool = True, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """GET /v3/feeds/{feedId} -- item-level ingestion results when asked."""
        params: Dict[str, Any] = {}
        if include_details:
            params = {"includeDetails": "true", "offset": offset, "limit": limit}
        # '@' in feed ids must be percent-encoded
        safe_id = feed_id.replace("@", "%40")
        return self.request("GET", f"/v3/feeds/{safe_id}", params=params)

    def wait_for_feed(self, feed_id: str, timeout: float = 900.0, interval: float = 15.0) -> Dict[str, Any]:
        """Poll until the feed leaves RECEIVED/INPROGRESS. Feeds are async."""
        deadline = time.time() + timeout
        status = {}
        while time.time() < deadline:
            status = self.feed_status(feed_id, include_details=False)
            if status.get("feedStatus") not in ("RECEIVED", "INPROGRESS"):
                return status
            time.sleep(interval)
        return status

    def taxonomy(self, feed_type: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """GET /v3/utilities/taxonomy -- category > product type groups."""
        params: Dict[str, Any] = {}
        if feed_type:
            params["feedType"] = feed_type
        if version:
            params["version"] = version
        return self.request("GET", "/v3/utilities/taxonomy", params=params)

    def spec(self, product_types: List[str], feed_type: str = "MP_ITEM", version: Optional[str] = None) -> Dict[str, Any]:
        """POST /v3/items/spec -- JSON-Schema of required attributes (max 20 types)."""
        body = {
            "feedType": feed_type,
            "version": version or DEFAULT_SPEC_VERSION,
            "productTypes": product_types[:20],
        }
        return self.request("POST", "/v3/items/spec", json_body=body)

    # -------------------------------------------------------------- writes --

    def update_inventory(self, sku: str, quantity: int, ship_node: Optional[str] = None,
                         available_date: Optional[str] = None) -> Dict[str, Any]:
        """PUT /v3/inventory -- single SKU, single node. Synchronous."""
        body: Dict[str, Any] = {"sku": sku, "quantity": {"unit": "EACH", "amount": int(quantity)}}
        if ship_node:
            body["shipNode"] = ship_node
        if available_date:
            body["inventoryAvailableDate"] = available_date
        return self.request("PUT", "/v3/inventory", json_body=body)

    def update_price(self, sku: str, amount: float, currency: str = "USD",
                     price_type: str = "BASE") -> Dict[str, Any]:
        """PUT /v3/price -- single SKU. price_type: BASE | REDUCED | CLEARANCE."""
        body = {
            "sku": sku,
            "pricing": [
                {
                    "currentPriceType": price_type,
                    "currentPrice": {"currency": currency, "amount": float(amount)},
                }
            ],
        }
        return self.request("PUT", "/v3/price", json_body=body)

    def item_feed_payload(self, items: List[Dict[str, Any]], business_unit: str = "WALMART_US",
                          locale: str = "en", version: Optional[str] = None) -> Dict[str, Any]:
        """Wrap MPItem entries in the required MPItemFeedHeader."""
        return {
            "MPItemFeedHeader": {
                "businessUnit": business_unit,
                "locale": locale,
                "version": version or DEFAULT_SPEC_VERSION,
            },
            "MPItem": items,
        }

    def submit_feed(self, feed_type: str, payload: Any, filename: Optional[str] = None) -> Dict[str, Any]:
        """POST /v3/feeds?feedType=... -- returns {"feedId": ...}."""
        name = filename or f"{feed_type.lower()}-{int(time.time())}.json"
        blob = json.dumps(payload).encode("utf-8")
        files = {"file": (name, blob, "application/json")}
        return self.request("POST", "/v3/feeds", params={"feedType": feed_type}, files=files)

    def submit_item_feed(self, items: List[Dict[str, Any]], feed_type: str = "MP_ITEM",
                         version: Optional[str] = None) -> Dict[str, Any]:
        """Convenience: full item setup (MP_ITEM) or partial update (MP_MAINTENANCE)."""
        return self.submit_feed(feed_type, self.item_feed_payload(items, version=version))


# ------------------------------------------------------------------ helpers --

def _clean_params(params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _json_or_text(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return (resp.text or "").strip()[:2000]
