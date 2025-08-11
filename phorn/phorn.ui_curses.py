# phorn/ui_curses.py
import curses
import locale
from .models import Hit

locale.setlocale(locale.LC_ALL, '')

class CursesUI:
    def __init__(self, stdscr: curses.window):
        self.stdscr = stdscr
        curses.start_color(); curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_RED,   -1)  # status
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # found
        curses.init_pair(3, curses.COLOR_YELLOW,-1)  # header
        curses.init_pair(4, curses.COLOR_CYAN,  -1)  # scan

    def _safe_add(self, row:int, col:int, text:str, attr:int=0):
        max_y, max_x = self.stdscr.getmaxyx()
        if 0<=row<max_y:
            self.stdscr.addstr(row, col, text[:max_x-col-1], attr)

    def show_logo(self) -> int:
        """Rysuje splash z logo PHORN; zwraca pierwszą wolną linię pod logiem."""
        self.stdscr.clear()
        self.max_y, self.max_x = self.stdscr.getmaxyx()
        logo = [
            "██████╗  ██╗  ██╗ ██████╗ ██████╗ ███╗   ██╗",
            "██╔══██╗ ██║  ██║██╔═══██╗██╔══██╗████╗  ██║",
            "██████╔╝ ███████║██║   ██║██████╔╝██╔██╗ ██║",
            "██╔═══╝  ██╔══██║██║   ██║██╔══██╔██║╚██╗██║",
            "██║      ██║  ██║╚██████╔╝██║  ██║██║ ╚████║",
            "╚═╝      ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝",
            "          We suck digits out of the web",
            "        phone & email crawler by RECONICA",
        ]
        for i,l in enumerate(logo):
            self._safe_add(i, 0, l, curses.color_pair(3) | curses.A_BOLD)
        first_free_row = len(logo) + 1
        self._safe_add(first_free_row, 0, "-"*(self.max_x-1), curses.color_pair(3))
        self.stdscr.refresh()
        return first_free_row + 1

    def prompt(self, row:int, prompt:str) -> str:
        max_y, max_x = self.stdscr.getmaxyx()
        shown = prompt[:max_x-1]
        self._safe_add(row, 0, shown)
        self.stdscr.clrtoeol()
        start = min(len(shown), max_x-2)
        self.stdscr.move(row, start)
        curses.echo()
        s = self.stdscr.getstr(row, start, max(1, max_x-start-1)).decode(errors="ignore").strip()
        curses.noecho()
        return s

    def build(self, domain:str, mode:int, max_pages:int):
        # ekran pracy z logami
        self.stdscr.clear()
        self.max_y, self.max_x = self.stdscr.getmaxyx()
        header = f"Target: {domain}   Mode: {mode}   Max pages: {max_pages}"
        self._safe_add(0, 0, header, curses.color_pair(3) | curses.A_BOLD)
        self._safe_add(1, 0, "-"*(self.max_x-1), curses.color_pair(3))
        self.log_top = 2
        self.status_row = self.max_y-1
        h = max(3, self.status_row - self.log_top)
        self.log = self.stdscr.subwin(h, self.max_x, self.log_top, 0)
        self.log.scrollok(True)
        self.draw_status(0,0,0,0)

    def draw_status(self, scanned:int, queued:int, errors:int, found:int=0):
        txt = f" Scanned: {scanned} | Found: {found} | Errors: {errors} | Queue: {queued} "
        self._safe_add(self.status_row, 0, " "*(self.max_x-1), curses.color_pair(1))
        self._safe_add(self.status_row, 0, txt, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.refresh()

    def log_scan(self, url:str):
        self.log.addstr(f"[SCAN] {url}\n", curses.color_pair(4)); self.log.refresh()

    def log_found(self, hit:Hit):
        self.log.addstr(f"[FOUND] {hit.username if hit.phone else ''} | {hit.phone} | {hit.email} | {hit.url}\n",
                        curses.color_pair(2)); self.log.refresh()

