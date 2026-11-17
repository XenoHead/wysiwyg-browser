"""Smoke-test CLI for the Walmart Marketplace client.

Read commands are safe. Anything that changes the live catalog needs --yes.

    python -m WalmartAPI.cli token
    python -m WalmartAPI.cli count
    python -m WalmartAPI.cli items --limit 5
    python -m WalmartAPI.cli item 1740-MP2022-1230-1135
    python -m WalmartAPI.cli search --upc 656605531151
    python -m WalmartAPI.cli inventory 1740-MP2022-1230-1135
    python -m WalmartAPI.cli feeds --limit 5
    python -m WalmartAPI.cli feed <feedId>
    python -m WalmartAPI.cli taxonomy --filter music
    python -m WalmartAPI.cli spec --product-types Music

    python -m WalmartAPI.cli inv-set <sku> 3 --yes
    python -m WalmartAPI.cli price <sku> 24.98 --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .walmart_api import SANDBOX_BASE, WalmartAPI, WalmartAPIError


def _dump(value: Any, limit: int = 0) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    if limit and len(text) > limit:
        text = text[:limit] + f"\n... ({len(text)} chars total)"
    print(text)


def _require_yes(args: argparse.Namespace, what: str) -> bool:
    if getattr(args, "yes", False):
        return True
    print(f"refusing: {what} changes the live Walmart catalog -- re-run with --yes", file=sys.stderr)
    return False


def build_client(args: argparse.Namespace) -> WalmartAPI:
    if getattr(args, "sandbox", False):
        return WalmartAPI(base_url=SANDBOX_BASE)
    return WalmartAPI()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="WalmartAPI.cli", description="Walmart Marketplace smoke tests")
    parser.add_argument("--sandbox", action="store_true", help="use sandbox.walmartapis.com (read-only mock data)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("token", help="fetch a token and report its lifetime (token itself is not printed)")

    p = sub.add_parser("count", help="item count by status")
    p.add_argument("--status", default="ALL")

    p = sub.add_parser("items", help="one page of the seller catalog")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--full", action="store_true", help="print every field instead of a summary line")

    p = sub.add_parser("item", help="one item by identifier")
    p.add_argument("identifier")
    p.add_argument("--id-type", default="SKU", choices=["SKU", "GTIN", "UPC", "EAN", "ISBN", "ITEM_ID"])

    p = sub.add_parser("search", help="search the Walmart catalog by identifier")
    p.add_argument("--upc")
    p.add_argument("--gtin")
    p.add_argument("--ean")
    p.add_argument("--isbn")
    p.add_argument("--asin")
    p.add_argument("--query")
    p.add_argument("--spec", action="store_true", help="return an MP_ITEM / MP_ITEM_MATCH payload (US only)")

    p = sub.add_parser("inventory", help="read inventory for a SKU")
    p.add_argument("sku")
    p.add_argument("--ship-node")

    p = sub.add_parser("inv-set", help="WRITE: set inventory for a SKU")
    p.add_argument("sku")
    p.add_argument("quantity", type=int)
    p.add_argument("--ship-node")
    p.add_argument("--yes", action="store_true")

    p = sub.add_parser("price", help="WRITE: set the price for a SKU")
    p.add_argument("sku")
    p.add_argument("amount", type=float)
    p.add_argument("--price-type", default="BASE", choices=["BASE", "REDUCED", "CLEARANCE"])
    p.add_argument("--yes", action="store_true")

    p = sub.add_parser("feeds", help="recent feeds")
    p.add_argument("--feed-type")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("feed", help="feed status, with per-item results")
    p.add_argument("feed_id")
    p.add_argument("--summary", action="store_true", help="skip item-level details")

    p = sub.add_parser("taxonomy", help="category / product-type taxonomy")
    p.add_argument("--feed-type")
    p.add_argument("--version")
    p.add_argument("--filter", help="only show branches whose names contain this text")

    p = sub.add_parser("spec", help="item-setup schema for one or more product types")
    p.add_argument("--product-types", nargs="+", required=True)
    p.add_argument("--feed-type", default="MP_ITEM")
    p.add_argument("--version")

    args = parser.parse_args(argv)

    try:
        api = build_client(args)

        if args.command == "token":
            _dump(api.token_info())

        elif args.command == "count":
            _dump({args.status: api.item_count(args.status)})

        elif args.command == "items":
            page = api.get_items(limit=args.limit, offset=args.offset)
            rows = page.get("ItemResponse") or []
            print(f"{len(rows)} of {page.get('totalItems')} items")
            if args.full:
                _dump(rows)
            else:
                for row in rows:
                    price = (row.get("price") or {}).get("amount")
                    print(
                        f"{row.get('sku'):<32} {row.get('publishedStatus'):<12} "
                        f"{str(price):>8}  {row.get('productName', '')[:70]}"
                    )

        elif args.command == "item":
            _dump(api.get_item(args.identifier, id_type=args.id_type))

        elif args.command == "search":
            _dump(
                api.search_catalog(
                    upc=args.upc, gtin=args.gtin, ean=args.ean,
                    isbn=args.isbn, asin=args.asin, query=args.query, spec=args.spec,
                )
            )

        elif args.command == "inventory":
            _dump(api.get_inventory(args.sku, ship_node=args.ship_node))

        elif args.command == "inv-set":
            if not _require_yes(args, "inv-set"):
                return 2
            _dump(api.update_inventory(args.sku, args.quantity, ship_node=args.ship_node))

        elif args.command == "price":
            if not _require_yes(args, "price"):
                return 2
            _dump(api.update_price(args.sku, args.amount, price_type=args.price_type))

        elif args.command == "feeds":
            payload = api.list_feeds(feed_type=args.feed_type, limit=args.limit)
            for feed in (payload.get("results") or {}).get("feed", []):
                print(
                    f"{feed.get('feedId')[:40]:<42} {feed.get('feedType', ''):<16} "
                    f"{feed.get('feedStatus', ''):<10} ok={feed.get('itemsSucceeded')} "
                    f"fail={feed.get('itemsFailed')}"
                )
            print(f"total: {payload.get('totalResults')}")

        elif args.command == "feed":
            _dump(api.feed_status(args.feed_id, include_details=not args.summary))

        elif args.command == "taxonomy":
            payload = api.taxonomy(feed_type=args.feed_type, version=args.version)
            if args.filter:
                needle = args.filter.lower()
                for cat in payload.get("itemTaxonomy") or []:
                    groups = [
                        g for g in cat.get("productTypeGroup") or []
                        if needle in str(g.get("productTypeGroupName", "")).lower()
                        or needle in str(cat.get("category", "")).lower()
                        or any(needle in str(pt.get("productTypeName", "")).lower()
                               for pt in g.get("productType") or [])
                    ]
                    if groups:
                        _dump({"category": cat.get("category"), "productTypeGroup": groups})
            else:
                _dump(payload)

        elif args.command == "spec":
            _dump(api.spec(args.product_types, feed_type=args.feed_type, version=args.version))

        return 0

    except WalmartAPIError as exc:
        print(f"Walmart API error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
