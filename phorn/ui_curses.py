# phorn/ui_curses.py
import curses
import locale
import time
from collections import deque

locale.setlocale(locale.LC_ALL, '')

MODE_MAP = {1: "Phones", 2: "Emails", 3: "Phones+Emails"}
RENDER_MAP = {0: "off", 1: "fallback", 2: "always"}

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


class CursesUI:
    def __init__(self, stdscr: curses.window):
        self.stdscr = stdscr
        curses.start_color()
        curses.use_default_colors()
        # Kolory
        curses.init_pair(1, curses.COLOR_RED,    -1)  # legacy
        curses.init_pair(2, curses.COLOR_GREEN,  -1)  # FOUND
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # "pomarańcz"
        curses.init_pair(4, curses.COLOR_CYAN,   -1)  # SCAN
        self.accent = curses.color_pair(3)

        self.start_ts = None
        self._options = {}
        self._pps = deque(maxlen=60)

        # Bezpieczniejsze wejście: timeout i keypad (obsługa KEY_RESIZE)
        try:
            self.stdscr.keypad(True)
            self.stdscr.timeout(100)  # 100ms, żeby łapać KEY_RESIZE w promptach
        except Exception:
            pass

    # ------------- helpers -------------
    def _safe_add(self, row: int, col: int, text: str, attr: int = 0):
        max_y, max_x = self.stdscr.getmaxyx()
        if 0 <= row < max_y:
            try:
                self.stdscr.addstr(row, col, text[: max_x - col - 1], attr)
            except curses.error:
                pass

    def prompt(self, row: int, prompt: str) -> str:
        """
        Bezpieczny prompt:
        - brak blokującego getstr()
        - obsługa KEY_RESIZE (przerysowanie i kontynuacja)
        - backspace, Enter, Ctrl+C
        """
        buf: list[str] = []
        curses.curs_set(1)
        while True:
            max_y, max_x = self.stdscr.getmaxyx()
            shown = prompt[: max_x - 1]

            # narysuj linię poleceń i aktualny bufor
            try:
                # czyść wiersz
                self._safe_add(row, 0, " " * (max_x - 1))
                # prompt
                self._safe_add(row, 0, shown, self.accent | curses.A_BOLD)
                start = min(len(shown), max_x - 2)
                # dopasuj wyświetlaną część bufora do szerokości
                fit = max(0, (max_x - 1) - start)
                disp = "".join(buf)[-fit:]
                self._safe_add(row, start, disp)
                # ustaw kursor
                self.stdscr.move(row, start + len(disp))
            except curses.error:
                pass

            # pobierz znak (z timeoutem ustawionym w __init__)
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                # timeout – po prostu odśwież pętlę
                continue
            except KeyboardInterrupt:
                raise

            # ENTER
            if ch in ("\n", "\r"):
                curses.curs_set(0)
                return "".join(buf).strip()

            # BACKSPACE (różne kody)
            if ch in ("\b", "\x7f") or ch == curses.KEY_BACKSPACE:
                if buf:
                    buf.pop()
                continue

            # RESIZE – przerysujemy w następnym obiegu pętli
            if ch == curses.KEY_RESIZE:
                continue

            # Ctrl+C
            if ch == "\x03":
                raise KeyboardInterrupt

            # normalny znak
            if isinstance(ch, str) and ch.isprintable():
                if len("".join(buf)) < (max_x - 1):
                    buf.append(ch)
                continue

            # ignoruj inne klawisze
            continue

    def show_logo(self) -> int:
        self.stdscr.clear()
        banner = [
            "██████╗ ██╗      ██████╗ ██████╗ ███╗   ██╗",
            "██╔══██╗██║     ██╔═══██╗██╔══██╗████╗  ██║",
            "██████╔╝███████║██║   ██║██████╔╝██╔██╗ ██║",
            "██╔═══╝ ██╔══██║██║   ██║██╔══██╔██║╚██╗██║",
            "██║     ██║  ██║╚██████╔╝██║  ██║██║ ╚████║",
            "╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝",
            "PHORN — We suck the digits out of the web",
            "      made by S.A.R.A. & Sh@dowRig",
        ]
        for i, l in enumerate(banner):
            self._safe_add(i, 0, l, self.accent | curses.A_BOLD)
        self.stdscr.refresh()
        return len(banner) + 1

    def set_start_time(self, ts: float | None):
        self.start_ts = ts

    # ------------- layout -------------
    def build(self, domain: str, mode: int, max_pages: int, *, netinfo: str = "", options: dict | None = None):
        self.stdscr.clear()
        self.max_y, self.max_x = self.stdscr.getmaxyx()
        self._options = options or {}

        title = f" Target: {domain}   Mode: {MODE_MAP.get(mode, str(mode))}   Max pages: {max_pages} "
        self._safe_add(0, 0, title, self.accent | curses.A_BOLD)
        self._safe_add(1, 0, netinfo, self.accent)

        self.left_w = max(40, int(self.max_x * 0.60))
        self.right_w = self.max_x - self.left_w - 1
        self.top = 2
        self.status_row = self.max_y - 1

        # separator kolumn (pomarańcz)
        for r in range(self.top, self.status_row):
            try:
                self.stdscr.addch(r, self.left_w, ord('|'), self.accent)
            except curses.error:
                pass

        left_h = self.status_row - self.top
        right_h = self.status_row - self.top

        # lewy log
        self.log = self.stdscr.subwin(left_h, self.left_w, self.top, 0)
        self.log.scrollok(True)

        # prawa kolumna
        settings_h = 18
        runtime_h = 8
        stats_h = 7
        url_h = 3
        used_h = settings_h + runtime_h + stats_h + url_h
        details_h = max(1, right_h - used_h)

        self.win_settings = self.stdscr.subwin(settings_h, self.right_w, self.top, self.left_w + 1)
        self.win_runtime = self.stdscr.subwin(runtime_h, self.right_w, self.top + settings_h, self.left_w + 1)
        self.win_stats = self.stdscr.subwin(stats_h, self.right_w, self.top + settings_h + runtime_h, self.left_w + 1)
        self.win_url = self.stdscr.subwin(url_h, self.right_w, self.top + settings_h + runtime_h + stats_h, self.left_w + 1)
        self.win_details = self.stdscr.subwin(details_h, self.right_w, self.top + used_h, self.left_w + 1)
        self.win_details.scrollok(True)

        self._draw_settings(domain, mode, max_pages)
        self._draw_runtime(0, 0, 0, 0, pps=None)
        self._draw_stats(0, 0, [])
        self._draw_url("-")
        self._details_header()

        self.draw_status(0, 0, 0, 0)
        self.stdscr.refresh()

    def _hdr(self, win, label):
        try:
            win.addstr(0, 0, f"[{label}]\n", self.accent | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_settings(self, domain: str, mode: int, max_pages: int):
        opt = self._options

        def yn(b): return "yes" if b else "no"
        def trunc(s, n=38):
            s = str(s)
            return (s[: n - 1] + "…") if len(s) > n else s

        rm = RENDER_MAP.get(opt.get("render_mode", 0), str(opt.get("render_mode", 0)))
        self.win_settings.clear()
        self._hdr(self.win_settings, "SETTINGS")
        # UWAGA: wstawiamy IP tuż po 'domain'
        lines = [
            f"domain: {domain}",
            f"ip: {opt.get('domain_ip', '-')}",
            f"mode: {MODE_MAP.get(mode, str(mode))}",
            f"max_pages: {max_pages}",
            f"start_url: {trunc(opt.get('start_url','') or '-')}",
            f"render: {rm}",
            f"interactive_unlock: {yn(opt.get('interactive_unlock', False))}",
            f"unlock_timeout_s: {opt.get('interactive_timeout_s', 60)}",
            f"sitemap_seed: {yn(opt.get('use_sitemap', False))}",
            f"delay_ms: {opt.get('delay_ms', 0)}",
            f"proxy: {trunc((opt.get('proxy') or '-') if '@' not in (opt.get('proxy') or '-') else opt.get('proxy').split('@')[-1])}",
            f"seed_cookie: {yn(opt.get('seed_cookie', False))}",
            f"bootstrap_first: {yn(opt.get('bootstrap_headful_first', False))}",
            f"aggr_net: {yn(opt.get('aggr_net', False))}",
            f"concurrency: {opt.get('concurrency', 1)}",
            f"obey_robots: {yn(opt.get('obey_robots', False))}",
            f"max_depth: {opt.get('max_depth', '-')}",
            f"include_re: {trunc(opt.get('include_re', '-'))}",
            f"exclude_re: {trunc(opt.get('exclude_re', '-'))}",
            f"cookies_in:  {trunc(opt.get('cookies_in_file', '-'))}",
            f"cookies_out: {trunc(opt.get('cookies_out_file', '-'))}",
            f"extras_only_on_phone: {yn(opt.get('extras_only_on_phone', False))}",
        ]
        row = 1
        for ln in lines:
            try:
                self.win_settings.addstr(row, 0, ln + "\n", self.accent)
            except curses.error:
                pass
            row += 1
        try:
            self.win_settings.noutrefresh()
        except curses.error:
            pass

    def _sparkline(self, data, width):
        if not data:
            return " " * width
        vals = list(data)[-width:]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1e-9
        out = []
        for v in vals:
            idx = int((v - lo) / span * (len(SPARK_BLOCKS) - 1))
            out.append(SPARK_BLOCKS[max(0, min(idx, len(SPARK_BLOCKS) - 1))])
        return "".join(out).ljust(width)

    def _draw_runtime(self, scanned: int, queued: int, found: int, errors: int, pps: float | None):
        elapsed = max(0.0, (time.time() - self.start_ts)) if self.start_ts else 0.0
        if pps is None:
            pps = (scanned / elapsed) if elapsed > 0 else 0.0
        self._pps.append(pps)

        eta_s = (queued / pps) if pps > 0 and queued > 0 else None
        mmss = "--:--" if eta_s is None else f"{int(eta_s) // 60:02d}:{int(eta_s) % 60:02d}"

        self.win_runtime.clear()
        self._hdr(self.win_runtime, "RUNTIME")
        lines = [
            f"elapsed: {int(elapsed)}s",
            f"scanned: {scanned}   queue: {queued}",
            f"found: {found}   errors: {errors}",
            f"speed: {pps:.2f} pages/s",
            f"ETA(queue): {mmss}",
            f"spark: {self._sparkline(self._pps, max(8, self.right_w - 8))}",
        ]
        row = 1
        for ln in lines:
            try:
                self.win_runtime.addstr(row, 0, ln + "\n", self.accent)
            except curses.error:
                pass
            row += 1
        try:
            self.win_runtime.noutrefresh()
        except curses.error:
            pass

    def _draw_stats(self, u_phones: int, u_emails: int, top_paths: list[tuple[str, int]]):
        self.win_stats.clear()
        self._hdr(self.win_stats, "STATS")
        row = 1
        try:
            self.win_stats.addstr(row, 0, f"unique phones: {u_phones}\n", self.accent)
            row += 1
            self.win_stats.addstr(row, 0, f"unique emails: {u_emails}\n", self.accent)
            row += 1
            self.win_stats.addstr(row, 0, "top paths:\n", self.accent)
            row += 1
            for seg, cnt in top_paths[:3]:
                bar = "█" * min(cnt, 20)
                self.win_stats.addstr(row, 0, f"  /{seg or ''} {bar} {cnt}\n", self.accent)
                row += 1
        except curses.error:
            pass
        try:
            self.win_stats.noutrefresh()
        except curses.error:
            pass

    def _draw_url(self, url: str):
        self.win_url.clear()
        self._hdr(self.win_url, "URL")
        try:
            self.win_url.addstr(1, 0, (url or "-")[: self.right_w - 1] + "\n", self.accent)
        except curses.error:
            pass
        try:
            self.win_url.noutrefresh()
        except curses.error:
            pass

    def _details_header(self):
        self.win_details.clear()
        self._hdr(self.win_details, "DETAILS")
        try:
            self.win_details.noutrefresh()
        except curses.error:
            pass

    # ------------- API używane przez crawler -------------
    def update_metrics(self, *, scanned: int, queued: int, found: int, errors: int):
        elapsed = max(0.0, (time.time() - self.start_ts)) if self.start_ts else 0.0
        pps = (scanned / elapsed) if elapsed > 0 else 0.0
        self._draw_runtime(scanned, queued, found, errors, pps=pps)
        self.draw_status(scanned, queued, errors, found)

    def update_stats(self, u_phones: int, u_emails: int, top_paths: list[tuple[str, int]]):
        self._draw_stats(u_phones, u_emails, top_paths)

    def log_scan(self, url: str):
        try:
            self.log.addstr(f"[SCAN] {url}\n", curses.color_pair(4))
            self.log.refresh()
        except curses.error:
            pass

    def log_found(self, hit):
        try:
            line = f"[FOUND] {hit.username if getattr(hit,'phone','') else ''} | {hit.phone} | {hit.email} | {hit.url}\n"
            self.log.addstr(line, curses.color_pair(2))
            self.log.refresh()
        except curses.error:
            pass

    def detail_start(self, url: str):
        self._draw_url(url)
        self._details_header()

    def detail(self, msg: str):
        try:
            self.win_details.addstr("• " + msg + "\n", self.accent)
            self.win_details.refresh()
        except curses.error:
            pass

    # ------------- status bar (pomarańcz) -------------
    def _progress_bar(self, scanned: int, queued: int, width: int) -> str:
        total = max(1, scanned + queued)
        pct = scanned / total
        filled = int(pct * width)
        return "█" * filled + " " * (width - filled)

    def draw_status(self, scanned: int, queued: int, errors: int, found: int = 0):
        maxw = self.max_x - 1
        pct = int((scanned / max(1, scanned + queued)) * 100)
        barw = max(10, min(40, maxw // 4))
        bar = self._progress_bar(scanned, queued, barw)
        txt = f" Scanned: {scanned} | Found: {found} | Errors: {errors} | Queue: {queued} | {pct:3d}% "

        # wypełnij cały wiersz akcentem
        self._safe_add(self.status_row, 0, " " * (maxw), self.accent | curses.A_BOLD)
        # progress bar
        self._safe_add(self.status_row, 0, "[" + bar + "] ", self.accent | curses.A_BOLD)
        # statystyki
        self._safe_add(self.status_row, barw + 3, txt, self.accent | curses.A_BOLD)
        try:
            self.stdscr.noutrefresh()
        except curses.error:
            pass
        curses.doupdate()
