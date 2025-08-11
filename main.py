#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import argparse
import asyncio
import curses
import csv
import time
from datetime import datetime
import aiohttp

try:
    import yaml  # opcjonalnie dla CLI
except Exception:
    yaml = None

from phorn.ui_curses import CursesUI
from phorn.crawl import crawl
from phorn.net import get_public_ip

def save_csv(domain: str, hits: list):
    fname = f"contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source_domain","username","phone","email","url"])
        w.writeheader()
        for h in hits:
            w.writerow(dict(
                source_domain=h.source_domain, username=h.username,
                phone=h.phone, email=h.email, url=h.url
            ))
    return fname

async def detect_netinfo_async(proxy: str | None) -> str:
    timeout = aiohttp.ClientTimeout(total=10, connect=5, sock_connect=5, sock_read=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        v4 = await get_public_ip(session, family="ipv4", proxy=proxy)
        v6 = await get_public_ip(session, family="ipv6", proxy=proxy)
    via = "via Proxy" if proxy else "direct"
    warn = ""
    if (not proxy) and v6:
        warn = "  ⚠ IPv6 aktywne — jeśli VPN nie tuneluje IPv6, rozważ wyłączenie IPv6."
    return f"Network: IPv4 {v4 or '-'} | IPv6 {v6 or '-'} ({via}){warn}"

# -------------------- CLI (opcjonalne) --------------------
def run_cli(cfg: dict):
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)

    domain  = cfg["domain"]
    mode    = int(cfg.get("mode", 1))
    pages   = int(cfg.get("max_pages", 200))

    # mapuj resztę opcji jak w TUI:
    kwargs = {
        "start_url": cfg.get("start_url"),
        "delay_ms": int(cfg.get("delay_ms", 0)),
        "render_mode": int(cfg.get("render_mode", 0)),
        "proxy": cfg.get("proxy"),
        "use_sitemap": bool(cfg.get("use_sitemap", False)),
        "interactive_unlock": bool(cfg.get("interactive_unlock", False)),
        "interactive_timeout_s": int(cfg.get("interactive_timeout_s", 60)),
        "seed_cookie_header": cfg.get("seed_cookie"),
        "bootstrap_headful_first": bool(cfg.get("bootstrap_headful_first", False)),
        "aggr_net": bool(cfg.get("aggr_net", False)),
        "concurrency": int(cfg.get("concurrency", 1)),
        "obey_robots": bool(cfg.get("obey_robots", False)),
        "max_depth": None if (cfg.get("max_depth") in (None,"","-1")) else int(cfg.get("max_depth")),
        "include_re": cfg.get("include_re") or "",
        "exclude_re": cfg.get("exclude_re") or "",
        "cookies_in_file": cfg.get("cookies_in_file") or "",
        "cookies_out_file": cfg.get("cookies_out_file") or "",
    }

    print(f"[PHORN/CLI] target={domain} mode={mode} max_pages={pages}")
    hits = loop.run_until_complete(
        crawl(domain, mode, pages,
              on_scan=lambda u: print("[SCAN]", u),
              on_found=lambda h: print("[FOUND]", h.phone, h.email, h.url),
              on_status=lambda s,q,f,e: print(f"[STAT] scanned={s} q={q} f={f} e={e}"),
              on_detail=lambda m: print("[DETAIL]", m),
              **kwargs)
    )
    fname = save_csv(domain, hits)
    print("[PHORN/CLI] saved:", fname)

# -------------------- TUI --------------------
def curses_main(stdscr):
    ui = CursesUI(stdscr)
    curses.curs_set(1)
    row = ui.show_logo()

    # Prompty
    domain    = ui.prompt(row + 0, "Enter domain (e.g., example.com): ")
    ui._safe_add(row + 1, 0, "Choose mode: 1) Phones only  2) Emails only  3) Phones + Emails")
    mode_str  = ui.prompt(row + 2, "Select [1/2/3] (default 1): ")
    pages_str = ui.prompt(row + 3, "Max pages (default 200): ")
    start_url = ui.prompt(row + 4, "Start URL (optional; e.g., https://example.com/listing): ")
    ui._safe_add(row + 5, 0, "Rendering: 0) off  1) fallback (auto)  2) always (slow)")
    render_str = ui.prompt(row + 6, "Render mode [0/1/2] (default 0): ")
    proxy_str  = ui.prompt(row + 7, "Proxy (optional, e.g., http://user:pass@host:port): ")
    ui._safe_add(row + 8, 0, "Sitemap seeding: 0) no  1) yes")
    sm_str     = ui.prompt(row + 9, "Use sitemap.xml as seeds? [0/1] (default 0): ")
    delay_str  = ui.prompt(row +10, "Delay per page [ms] (default 0): ")
    ui._safe_add(row +11, 0, "Interactive CF unlock (opens browser if needed)")
    iu_str     = ui.prompt(row +12, "Enable interactive unlock? [y/N]: ")
    iu_to_str  = ui.prompt(row +13, "Interactive unlock timeout [s] (default 60): ")
    seed_cookie = ui.prompt(row +14, "Seed Cookie (optional, e.g., cf_clearance=...; __cf_bm=...): ")
    boot_first  = ui.prompt(row +15, "Browser bootstrap first? [y/N]: ")
    aggr_str    = ui.prompt(row +16, "Aggressive CF networking (HTTP/2 + pełne nagłówki)? [y/N]: ")
    # NOWE:
    conc_str    = ui.prompt(row +17, "Concurrency (HTTP workers, default 1): ")
    robots_str  = ui.prompt(row +18, "Obey robots.txt? [y/N]: ")
    depth_str   = ui.prompt(row +19, "Max depth (empty = unlimited): ")
    inc_re      = ui.prompt(row +20, "Include regex (optional): ")
    exc_re      = ui.prompt(row +21, "Exclude regex (optional): ")
    cin_path    = ui.prompt(row +22, "Cookies import file (optional): ")
    cout_path   = ui.prompt(row +23, "Cookies export file (optional): ")

    # Parsy
    try: mode = int(mode_str or "1")
    except: mode = 1
    if mode not in (1,2,3): mode = 1

    try: max_pages = int(pages_str or "200")
    except: max_pages = 200

    try: render_mode = int(render_str or "0")
    except: render_mode = 0
    if render_mode not in (0,1,2): render_mode = 0

    proxy = (proxy_str or "").strip() or None
    try: use_sitemap = bool(int(sm_str or "0"))
    except: use_sitemap = False
    try: delay_ms = int(delay_str or "0")
    except: delay_ms = 0

    interactive_unlock = (iu_str or "").strip().lower() in ("y","yes","1","true")
    try: interactive_timeout_s = int(iu_to_str or "60")
    except: interactive_timeout_s = 60

    seed_cookie_header = (seed_cookie or "").strip() or None
    bootstrap_headful_first = (boot_first or "").strip().lower() in ("y","yes","1","true")
    aggr_net = (aggr_str or "").strip().lower() in ("y","yes","1","true")

    try: concurrency = int(conc_str or "1")
    except: concurrency = 1
    obey_robots = (robots_str or "").strip().lower() in ("y","yes","1","true")
    max_depth = None if not (depth_str or "").strip() else int(depth_str)
    include_re = (inc_re or "").strip()
    exclude_re = (exc_re or "").strip()
    cookies_in_file  = (cin_path or "").strip()
    cookies_out_file = (cout_path or "").strip()

    # Net info
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try:
        netinfo = loop.run_until_complete(detect_netinfo_async(proxy))
    except Exception:
        netinfo = "Network: (failed to detect IP)"
    curses.curs_set(0)

    # UI
    ui.build(
        domain, mode, max_pages,
        netinfo=netinfo,
        options=dict(
            start_url=start_url or "",
            render_mode=render_mode,
            interactive_unlock=interactive_unlock,
            interactive_timeout_s=interactive_timeout_s,
            proxy=proxy or "",
            use_sitemap=use_sitemap,
            delay_ms=delay_ms,
            seed_cookie=bool(seed_cookie_header) or bool(cookies_in_file),
            bootstrap_headful_first=bootstrap_headful_first,
            aggr_net=aggr_net,
            concurrency=concurrency,
            obey_robots=obey_robots,
            max_depth=max_depth if max_depth is not None else "-",
            include_re=include_re or "-",
            exclude_re=exclude_re or "-",
            cookies_in_file=cookies_in_file or "-",
            cookies_out_file=cookies_out_file or "-",
        )
    )
    ui.set_start_time(time.time())

    # Callbacks
    def on_scan(url):
        ui.log_scan(url)
        ui.detail_start(url)

    def on_found(hit):
        ui.log_found(hit)

    def on_status(s,q,f,e):
        ui.update_metrics(scanned=s, queued=q, found=f, errors=e)

    def on_detail(msg):
        ui.detail(msg)

    def on_stats(u_phones,u_emails,top_paths):
        ui.update_stats(u_phones,u_emails,top_paths)

    # Run
    hits = loop.run_until_complete(
        crawl(
            domain, mode, max_pages,
            on_scan, on_found, on_status,
            start_url=(start_url or None),
            delay_ms=delay_ms,
            render_mode=render_mode,
            proxy=proxy,
            use_sitemap=use_sitemap,
            interactive_unlock=interactive_unlock,
            on_detail=on_detail,
            on_stats=on_stats,
            interactive_timeout_s=interactive_timeout_s,
            seed_cookie_header=seed_cookie_header,
            bootstrap_headful_first=bootstrap_headful_first,
            aggr_net=aggr_net,
            concurrency=concurrency,
            obey_robots=obey_robots,
            max_depth=max_depth,
            include_re=include_re,
            exclude_re=exclude_re,
            cookies_in_file=cookies_in_file,
            cookies_out_file=cookies_out_file,
        )
    )
    curses.curs_set(1)
    fname = save_csv(domain, hits)
    ui._safe_add(ui.status_row, 0, f"Saved results to {fname}")
    ui.stdscr.getch()

if __name__ == "__main__":
    # tryb CLI: --cli --config cfg.yaml
    if "--cli" in sys.argv:
        ap = argparse.ArgumentParser()
        ap.add_argument("--config", required=True)
        args = ap.parse_args()
        if yaml is None:
            print("Install PyYAML: pip install pyyaml"); sys.exit(1)
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        run_cli(cfg)
    else:
        curses.wrapper(curses_main)
