# phorn/net.py
from __future__ import annotations

from urllib.parse import urljoin, urlparse, urldefrag
import aiohttp

# HTTP/2 client (aggressive mode)
try:
    import httpx
except Exception:
    httpx = None

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

BROWSER_HEADERS = dict(BASE_HEADERS)  # w aggr używamy tych samych „bezpiecznych” nagłówków

_CF_BODY_SIGNS = (
    "attention required! | cloudflare",
    "checking your browser before accessing",
    "just a moment...",
    "cf-chl-bypass",
    "cf-browser-verification",
)

def same_domain(link: str, domain: str) -> bool:
    try:
        host = urlparse(link).netloc.lower().split(":", 1)[0]
        return (host == "" or host.endswith(domain.lower()))
    except Exception:
        return False

def defrag_and_norm(base: str, href: str) -> str | None:
    try:
        url = urljoin(base, href)
        url, _ = urldefrag(url)
        return url
    except Exception:
        return None

def _looks_cloudflare(status: int, headers: dict[str, str], body: str | None) -> bool:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    if h.get("server", "").lower().startswith("cloudflare"):
        return True
    if "cf-ray" in h:
        return True
    if status in (403, 409, 429, 503):
        return True
    if body:
        low = body.lower()
        if any(s in low for s in _CF_BODY_SIGNS):
            return True
    return False

async def detect_cloudflare(session: aiohttp.ClientSession, url: str, *, proxy: str | None = None) -> bool:
    try:
        async with session.get(url, headers=BASE_HEADERS, allow_redirects=True, proxy=proxy, timeout=8) as r:
            text = await r.text(errors="ignore")
            return _looks_cloudflare(r.status, r.headers, text)
    except Exception:
        return False

# --- standard fetch (aiohttp, szybki) + wewnętrzny fallback na httpx/h2, jeśli wykryje CF ---
async def _fetch_html_httpx(url: str, *, proxy: str | None, headers: dict[str, str]) -> str | None:
    if httpx is None:
        return None
    proxies = {"http://": proxy, "https://": proxy} if proxy else None
    async with httpx.AsyncClient(http2=True, follow_redirects=True, proxies=proxies, headers=headers, timeout=10.0) as client:
        try:
            r = await client.get(url)
            ct = r.headers.get("content-type", "")
            txt = r.text
            if r.status_code == 200 and ("text/html" in ct.lower() or "<html" in (txt.lower() if txt else "")):
                return txt
            return None
        except Exception:
            return None

async def fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    *,
    proxy: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str | None:
    headers = dict(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    try:
        async with session.get(url, timeout=12, allow_redirects=True, headers=headers, proxy=proxy) as r:
            text = await r.text(errors="ignore")
            ct = r.headers.get("Content-Type", "")
            if r.status == 200 and ("text/html" in ct or "<html" in (text.lower() if text else "")):
                return text
            if _looks_cloudflare(r.status, r.headers, text):
                return await _fetch_html_httpx(url, proxy=proxy, headers=headers)
    except Exception:
        pass

    try:
        return await _fetch_html_httpx(url, proxy=proxy, headers=headers)
    except Exception:
        return None

# --- agresywne pobieranie (włączane przełącznikiem aggr_net=True) ---
async def fetch_html_aggr(
    url: str,
    *,
    proxy: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str | None:
    if httpx is None:
        return None
    headers = dict(BROWSER_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    proxies = {"http://": proxy, "https://": proxy} if proxy else None
    try:
        async with httpx.AsyncClient(http2=True, follow_redirects=True, proxies=proxies, headers=headers, timeout=12.0) as client:
            r = await client.get(url)
            ct = r.headers.get("content-type", "").lower()
            txt = r.text
            if r.status_code == 200 and ("text/html" in ct or "<html" in (txt.lower() if txt else "")):
                return txt
            return None
    except Exception:
        return None

# ------- Public IP helpers (do nagłówka UI) -------
async def get_public_ip(session: aiohttp.ClientSession, family: str = "ipv4", proxy: str | None = None) -> str | None:
    endpoints = {
        "ipv4": ("https://api.ipify.org", "http://api.ipify.org"),
        "ipv6": ("https://api64.ipify.org", "http://api64.ipify.org"),
    }.get(family, ("https://api.ipify.org", "http://api.ipify.org"))

    for ep in endpoints:
        try:
            async with session.get(ep, headers={"User-Agent": UA}, proxy=proxy, timeout=6) as r:
                if r.status == 200:
                    txt = (await r.text()).strip()
                    if txt:
                        return txt
        except Exception:
            continue
    return None
