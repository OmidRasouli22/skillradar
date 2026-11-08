"""Checks for the local-only APIs (review page, CV analysis).

The pages run on this machine only, but any website open in the same browser could send
requests to 127.0.0.1. So every request must name this server as its host (stops DNS
rebinding), and writes must come from this page (Origin) as JSON, which a page on another
site can't send without the server's permission.
"""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def local_only(request: Request) -> None:
    host = request.headers.get("host", "")
    if urlsplit(f"//{host}").hostname not in LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="only for this computer")


def same_page_json(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).hostname not in LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="only from the local page")
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(status_code=415, detail="send JSON")
