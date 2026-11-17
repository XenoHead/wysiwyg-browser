"""Standalone launcher for the WalmartAPI page.

This package is deliberately kept *outside* the main app while we decide how it
should work in: nothing in ``main.py``, ``WYSIWYG.spec`` or ``install.py``
references it. Run it on its own port instead.

    python -m WalmartAPI                  -> http://127.0.0.1:8009/walmart-api
    python -m WalmartAPI --port 8010
    python -m WalmartAPI --open           also open the page in the default browser
    python -m WalmartAPI --sandbox        point the client at sandbox.walmartapis.com

Credentials come from the repo-root ``.env`` (``WALMART_CLIENT_ID`` /
``WALMART_CLIENT_SECRET``), resolved relative to this file, so the working
directory does not matter.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8009  # 8008 belongs to the main app


def build_app(sandbox: bool = False):
    """A FastAPI app holding only the WalmartAPI page and its lookup route."""
    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse

    from . import routes

    if sandbox:
        # Same one-client-per-process cache, but pointed at the sandbox host.
        from .walmart_api import SANDBOX_BASE, WalmartAPI

        routes._client = WalmartAPI(base_url=SANDBOX_BASE, timeout=25.0)

    app = FastAPI(title="WalmartAPI (standalone)", docs_url="/docs")
    app.include_router(routes.router)

    @app.get("/", include_in_schema=False)
    async def _root():
        return RedirectResponse(url="/walmart-api")

    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m WalmartAPI",
        description="Run the Walmart Marketplace UPC lookup page on its own port.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="open the page in the default browser")
    parser.add_argument("--sandbox", action="store_true", help="use sandbox.walmartapis.com")
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}/walmart-api"
    print(f"WalmartAPI standalone -> {url}")
    print(f"  lookup: POST http://{args.host}:{args.port}/api/walmart-api/lookup")
    if args.open:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn.run(
        build_app(sandbox=args.sandbox),
        host=args.host,
        port=args.port,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
