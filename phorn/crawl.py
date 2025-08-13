# phorn/crawl.py
import asyncio
import re
import time
from pathlib import Path
from collections import Counter
from urllib.parse import unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup

try:
    from .types import Hit, IPHit, FPEvent
except Exception:
    from .models import Hit, IPHit, FPEvent

from .extract import (
    PHONE_RE, EMAIL_RE, clean_phone, guess_username,
    find_ips, detect_fingerprint_indicators
)
from .net import (
    fetch_html, fetch_html_aggr,
    same_domain, defrag_and_norm, detect_cloudflare, UA
)

_CF_SIGNS = (
    "attention required! | cloudflare",
    "checking your browser before accessing",
    "just a moment...",
    "cf-chl-bypass",
    "cf-browser-verification",
)

LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled","--no-sandbox","--disable-dev-shm-usage"]

def _looks_js_or_cf(html: str | None) -> bool:
    if not html: return True
    low = html.lower()
    if any(s in low for s in _CF_SIGNS): return True
    if low.count("<a ") < 3 and low.count("<script") >= 3: return True
    if "<noscript" in low: return True
    return False

def _normalize_host(netloc: str) -> str:
    return netloc.split(":", 1)[0].lower()

def _host_of(u: str) -> str:
    try: return _normalize_host(urlparse(u).netloc)
    except Exception: return ""

def _cookie_header_from(pw_cookies: list[dict]) -> str:
    parts = []
    for c in pw_cookies:
        n,v = c.get("name"), c.get("value")
        if n and v: parts.append(f"{n}={v}")
    return "; ".join(parts)

def _has_cf_clearance(cookies: list[dict]) -> bool:
    return any(c.get("name","").lower().startswith("cf_clearance") for c in cookies)

def _put_cookie(cookie_hdr: dict[str,str], host: str, header: str):
    if not host or not header: return
    cookie_hdr[host] = header
    if "." in host:
        parent = host.split(".",1)[1]
        cookie_hdr[parent] = header

def _profile_dir_for(domain: str) -> str:
    base = Path.home() / ".phorn" / "profiles"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / domain.replace(":", "_"))

def _cleanup_chrome_singleton(profile_dir: str, on_detail=None):
    if not profile_dir: return
    for name in ("SingletonLock","SingletonCookie","SingletonSocket"):
        p = Path(profile_dir) / name
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            if on_detail: on_detail(f"cleanup warn: {e}")

# ------------ Playwright helpers ------------
async def _render_html(browser_ctx, url: str, timeout_ms: int) -> str | None:
    try:
        page = browser_ctx["page"]
        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        await page.wait_for_timeout(1200)
        return await page.content()
    except Exception:
        return None

async def _ensure_browser(existing_ctx, proxy, *, headless=True, domain_for_profile=None, on_detail=None):
    if existing_ctx is not None:
        return existing_ctx, None
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        ctx_opts = dict(locale="pl-PL", user_agent=UA, viewport={"width":1366,"height":768})
        if proxy: ctx_opts["proxy"] = {"server": proxy}
        context = None; browser = None
        profile_dir = _profile_dir_for(domain_for_profile) if domain_for_profile else None
        use_channel = "chrome"
        if profile_dir: _cleanup_chrome_singleton(profile_dir, on_detail)
        if profile_dir:
            try:
                context = await pw.chromium.launch_persistent_context(
                    profile_dir, channel=use_channel, headless=headless, args=LAUNCH_ARGS, **ctx_opts
                )
            except Exception:
                pass
        if context is None:
            try:
                browser = await pw.chromium.launch(channel=use_channel, headless=headless, args=LAUNCH_ARGS)
            except Exception:
                browser = await pw.chromium.launch(headless=headless, args=LAUNCH_ARGS)
            context = await browser.new_context(**ctx_opts)
        page = await context.new_page()
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except Exception:
            pass
        return {"browser": browser, "context": context, "page": page}, pw
    except Exception as e:
        if on_detail: on_detail(f"browser launch failed: {e}")
        return None, None

async def _interactive_unlock(url, proxy, *, timeout_s, on_detail, domain_for_profile):
    ctx, pw = await _ensure_browser(None, proxy, headless=False, domain_for_profile=domain_for_profile, on_detail=on_detail)
    if not ctx:
        on_detail("interactive: cannot start browser (missing deps?)")
        return None, None
    try:
        page = ctx["page"]
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        start = time.time()
        while time.time() - start < timeout_s:
            try:
                sel = ("button:has-text('Akceptuj'), button:has-text('Zgadzam'), "
                       "button:has-text('Accept'),   button:has-text('I agree'), "
                       "button:has-text('OK'),       button:has-text('Got it')")
                btn = page.locator(sel).first
                if await btn.is_visible():
                    await btn.click(); on_detail("interactive: clicked cookie banner")
                    await page.wait_for_timeout(500); await page.reload(wait_until="domcontentloaded")
            except Exception: pass
            try:
                cookies = await ctx["context"].cookies()
                if _has_cf_clearance(cookies):
                    html = await page.content()
                    return html, _cookie_header_from(cookies)
            except Exception: pass
            waited = int(time.time() - start)
            if waited and waited % 5 == 0:
                on_detail(f"interactive: waiting… {waited}s/{timeout_s}s → reload")
                try: await page.reload(wait_until="domcontentloaded")
                except Exception: pass
            await page.wait_for_timeout(1000)
        on_detail("interactive: timeout")
        return None, None
    finally:
        try:
            await ctx["context"].close()
            if ctx.get("browser"): await ctx["browser"].close()
            if pw: await pw.stop()
        except Exception: pass

# ------------ robots.txt ------------
async def _fetch_robots(session: aiohttp.ClientSession, domain: str, proxy: str | None, on_detail):
    url = f"https://{domain}/robots.txt"
    try:
        async with session.get(url, proxy=proxy, timeout=8) as r:
            if r.status != 200:
                return []
            txt = await r.text(errors="ignore")
    except Exception:
        # spróbuj http
        try:
            async with session.get(f"http://{domain}/robots.txt", proxy=proxy, timeout=8) as r:
                if r.status != 200:
                    return []
                txt = await r.text(errors="ignore")
        except Exception:
            return []
    rules = []
    agent = "*"
    cur_block = None
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        parts = s.split(":",1)
        if len(parts)!=2: continue
        k,v = parts[0].strip().lower(), parts[1].strip()
        if k == "user-agent":
            agent = v.lower()
            cur_block = agent
        elif k == "disallow" and (cur_block in ("*","phorn","phorn-bot")):
            rules.append(v or "/")
    on_detail(f"robots: {len(rules)} disallow rules")
    return rules

def _robots_allowed(url: str, domain: str, rules: list[str]) -> bool:
    try:
        p = urlparse(url).path or "/"
    except Exception:
        return True
    for rule in rules:
        if rule == "/":
            return False
        if p.startswith(rule):
            return False
    return True

# ------------ main crawler ------------
async def crawl(
    domain: str,
    mode: int,
    max_pages: int,
    on_scan,
    on_found,
    on_status,
    *,
    start_url: str | None = None,
    delay_ms: int = 0,
    render_mode: int = 0,
    proxy: str | None = None,
    use_sitemap: bool = False,
    interactive_unlock: bool = False,
    on_detail = None,
    on_stats = None,
    on_ip = None,
    on_fp = None,
    extras_only_on_phone: bool = False,
    interactive_timeout_s: int = 60,
    seed_cookie_header: str | None = None,
    bootstrap_headful_first: bool = False,
    aggr_net: bool = False,
    concurrency: int = 1,
    obey_robots: bool = False,
    max_depth: int | None = None,
    include_re: str = "",
    exclude_re: str = "",
    cookies_in_file: str = "",
    cookies_out_file: str = "",
) -> list[Hit]:
    def detail(msg: str):
        if on_detail: on_detail(msg)

    # no-op callbacks
    if on_ip is None:
        def on_ip(*_args, **_kw): ...
    if on_fp is None:
        def on_fp(*_args, **_kw): ...

    hits: list[Hit] = []
    scanned = found = errors = 0

    uniq_phones, uniq_emails = set(), set()
    path_counter = Counter()

    q: asyncio.Queue = asyncio.Queue()
    visited: set[str] = set()
    vlock = asyncio.Lock()

    inc_re = re.compile(include_re) if include_re else None
    exc_re = re.compile(exclude_re) if exclude_re else None

    seeds = []
    if start_url: seeds.append((start_url, 0))
    seeds += [(f"https://{domain}/", 0), (f"http://{domain}/", 0)]
    for u,d in seeds: await q.put((u,d))

    cookie_hdr: dict[str,str] = {}

    if seed_cookie_header:
        _put_cookie(cookie_hdr, domain.lower(), seed_cookie_header); detail("cookies: seeded (UI)")
    if cookies_in_file:
        try:
            with open(cookies_in_file, "r", encoding="utf-8") as f:
                hdr = f.read().strip()
            if hdr:
                _put_cookie(cookie_hdr, domain.lower(), hdr); detail("cookies: seeded (file)")
        except Exception as e:
            detail(f"cookies import error: {e}")

    browser_ctx = None; pw = None
    render_sem = asyncio.Semaphore(1)
    interact_sem = asyncio.Semaphore(1)

    timeout = aiohttp.ClientTimeout(total=12, connect=6, sock_connect=6, sock_read=8)
    conn = aiohttp.TCPConnector(limit=max(20, 5*concurrency), ttl_dns_cache=300)

    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:

        robots_rules = []
        if obey_robots:
            robots_rules = await _fetch_robots(session, domain, proxy, detail)

        try:
            seed_url = start_url or f"https://{domain}/"
            if await detect_cloudflare(session, seed_url, proxy=proxy) and render_mode == 0:
                render_mode = 1
        except Exception: pass

        if use_sitemap:
            try:
                from .net import fetch_html as _fh
                for path in ("/sitemap.xml", "/sitemap_index.xml"):
                    html = await _fh(session, f"https://{domain}{path}", proxy=proxy) or \
                           await _fh(session, f"http://{domain}{path}",  proxy=proxy)
                    if not html: continue
                    for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", html, re.I):
                        u = m.group(1).strip()
                        if same_domain(u, domain):
                            await q.put((u,0))
            except Exception: pass

        async def _get_html(u: str, extra_headers: dict[str,str] | None):
            if aggr_net:
                return await fetch_html_aggr(u, proxy=proxy, extra_headers=extra_headers)
            else:
                return await fetch_html(session, u, proxy=proxy, extra_headers=extra_headers)

        async def worker(wid:int):
            nonlocal scanned, found, errors, browser_ctx, pw
            while (scanned < max_pages):
                try:
                    url, depth = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if scanned >= max_pages: break
                    await asyncio.sleep(0.05)
                    continue
                async with vlock:
                    if url in visited:
                        q.task_done()
                        on_status(scanned, q.qsize(), found, errors)
                        continue
                    visited.add(url)

                if inc_re and not inc_re.search(url): 
                    q.task_done(); on_status(scanned, q.qsize(), found, errors); continue
                if exc_re and exc_re.search(url): 
                    q.task_done(); on_status(scanned, q.qsize(), found, errors); continue
                if (max_depth is not None) and (depth > max_depth):
                    q.task_done(); on_status(scanned, q.qsize(), found, errors); continue
                if obey_robots and not _robots_allowed(url, domain, robots_rules):
                    detail("robots: disallow"); q.task_done(); on_status(scanned, q.qsize(), found, errors); continue

                on_scan(url); detail("start")

                host = _host_of(url)
                extra = {"Cookie": cookie_hdr[host]} if host in cookie_hdr else {}

                html = None
                if render_mode == 0:
                    detail("fetch: HTTP")
                    html = await _get_html(url, extra)
                elif render_mode == 2:
                    detail("render: Playwright (always)")
                    async with render_sem:
                        if browser_ctx is None:
                            browser_ctx, pw = await _ensure_browser(browser_ctx, proxy, headless=True, domain_for_profile=domain, on_detail=detail)
                        html = await _render_html(browser_ctx, url, timeout_ms=15000) if browser_ctx else None
                        if html and browser_ctx:
                            try:
                                ck = await browser_ctx["context"].cookies(url)
                                if ck:
                                    _put_cookie(cookie_hdr, host, _cookie_header_from(ck))
                                    detail("cookies: captured (render)")
                            except Exception: pass
                    if not html:
                        detail("render failed → fallback HTTP")
                        html = await _get_html(url, extra)
                else:
                    detail("fetch: HTTP (fallback first)")
                    html = await _get_html(url, extra)
                    if _looks_js_or_cf(html):
                        detail("CF/JS detected → render headless")
                        async with render_sem:
                            if browser_ctx is None:
                                browser_ctx, pw = await _ensure_browser(browser_ctx, proxy, headless=True, domain_for_profile=domain, on_detail=detail)
                            if browser_ctx:
                                html2 = await _render_html(browser_ctx, url, timeout_ms=12000)
                                if html2:
                                    html = html2
                                    try:
                                        ck = await browser_ctx["context"].cookies(url)
                                        if ck:
                                            _put_cookie(cookie_hdr, host, _cookie_header_from(ck))
                                            detail("cookies: captured (render)")
                                    except Exception: pass
                    if _looks_js_or_cf(html) and interactive_unlock:
                        detail("still blocked → interactive unlock (opens browser)")
                        async with interact_sem:
                            html2, ck_hdr = await _interactive_unlock(
                                url, proxy, timeout_s=interactive_timeout_s,
                                on_detail=detail, domain_for_profile=domain,
                            )
                        if html2:
                            html = html2
                            if ck_hdr:
                                _put_cookie(cookie_hdr, host, ck_hdr)
                                detail("cookies: captured (interactive)")

                scanned += 1
                if _looks_js_or_cf(html):
                    errors += 1; detail("skip: CF/timeout")
                    on_status(scanned, q.qsize(), found, errors)
                    q.task_done()
                    if delay_ms: await asyncio.sleep(delay_ms/1000)
                    continue

                on_status(scanned, q.qsize(), found, errors)

                soup = BeautifulSoup(html, "html.parser")
                page_text = soup.get_text(" ", strip=True)

                # stats: path segment
                try:
                    seg = (urlparse(url).path or "/").strip("/").split("/",1)[0]
                    path_counter[seg] += 1
                except Exception: pass

                phones=set()
                if mode in (1,3):
                    for m in PHONE_RE.finditer(page_text):
                        ph=clean_phone(m.group(0))
                        if ph: phones.add(ph)
                    for a in soup.find_all("a", href=True):
                        href=a["href"].strip()
                        if href.lower().startswith("tel:"):
                            ph=clean_phone(unquote(href.split(":",1)[1]))
                            if ph: phones.add(ph)

                emails=set()
                if mode in (2,3):
                    for m in EMAIL_RE.finditer(page_text):
                        emails.add(m.group(0))
                    for a in soup.find_all("a", href=True):
                        href=a["href"].strip()
                        if href.lower().startswith("mailto:"):
                            addr=unquote(href.split(":",1)[1]).split("?",1)[0]
                            if EMAIL_RE.fullmatch(addr): emails.add(addr)

                # update UI stats
                uniq_phones.update(phones)
                uniq_emails.update(emails)
                if on_stats:
                    top_paths = sorted(path_counter.items(), key=lambda x:-x[1])[:5]
                    on_stats(len(uniq_phones), len(uniq_emails), top_paths)

                # ---- Extras (IP/FP) tylko jeśli ustawienie pozwala ----
                should_collect_extras = True
                if extras_only_on_phone:
                    should_collect_extras = bool(phones)
                if should_collect_extras:
                    try:
                        all_text = html or ""
                        for sc in soup.find_all("script"):
                            try:
                                if sc.string:
                                    all_text += " " + sc.string
                            except Exception:
                                pass
                        for ip in find_ips(all_text):
                            on_ip(IPHit(ip=ip, url=url))
                    except Exception:
                        pass
                    try:
                        for label, evid in detect_fingerprint_indicators(html or ""):
                            on_fp(FPEvent(url=url, indicator=label, evidence=evid[:200]))
                    except Exception:
                        pass

                # hits
                if phones and emails:
                    uname = guess_username(soup) if phones else ""
                    for ph in phones:
                        for em in emails:
                            hit = Hit(domain, uname, ph, em, url)
                            hits.append(hit); found += 1; on_found(hit)
                elif phones:
                    uname = guess_username(soup)
                    for ph in phones:
                        hit = Hit(domain, uname, ph, "", url)
                        hits.append(hit); found += 1; on_found(hit)
                elif emails:
                    for em in emails:
                        hit = Hit(domain, "", "", em, url)
                        hits.append(hit); found += 1; on_found(hit)

                # enqueue links
                before = q.qsize()
                for a in soup.find_all("a", href=True):
                    nxt=defrag_and_norm(url, a["href"])
                    if not nxt: continue
                    if not same_domain(nxt, domain): continue
                    if inc_re and not inc_re.search(nxt): continue
                    if exc_re and exc_re.search(nxt): continue
                    nd = depth + 1
                    if (max_depth is not None) and (nd > max_depth): continue
                    async with vlock:
                        if nxt not in visited:
                            await q.put((nxt, nd))
                after = q.qsize()
                if after>before: detail(f"enqueued: +{after-before} (queue={after})")

                q.task_done()
                if delay_ms: await asyncio.sleep(delay_ms/1000)

        workers = [asyncio.create_task(worker(i)) for i in range(max(1,concurrency))]
        await asyncio.gather(*workers, return_exceptions=True)

    if cookies_out_file:
        try:
            hdr = cookie_hdr.get(domain.lower()) or next(iter(cookie_hdr.values()), "")
            if hdr:
                Path(cookies_out_file).parent.mkdir(parents=True, exist_ok=True)
                with open(cookies_out_file, "w", encoding="utf-8") as f:
                    f.write(hdr)
        except Exception:
            pass

    on_status(scanned, 0, found, errors)
    return hits
