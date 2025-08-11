import re
from bs4 import BeautifulSoup, NavigableString, Tag

# PL: dopuszczamy spacje/kreski/kropki, opcjonalne +48/48
PHONE_RE = re.compile(r"""(?x)
    (?:\+?48[\s\-\.]?)?      # opcjonalny PL prefix
    (?:\d[\s\-\.]?){9}       # 9 cyfr z separatorami
""")
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]{1,255}\.[A-Za-z0-9-]{2,}\b")

def clean_phone(raw: str) -> str | None:
    """
    Zwraca numer w formacie E.164 dla PL: +48XXXXXXXXX.
    Jeśli to nie wygląda na polski numer (9 lub 11 cyfr z 48), zwraca None.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "48" + digits
    if len(digits) == 11 and digits.startswith("48"):
        return f"+{digits}"
    return None

def guess_username(soup: BeautifulSoup) -> str:
    for sel in ("h1", "h2", "h3"):
        h = soup.find(sel)
        if h and h.get_text(strip=True):
            return " ".join(h.get_text(" ", strip=True).split())[:80]
    if soup.title and soup.title.get_text(strip=True):
        return " ".join(soup.title.get_text(" ", strip=True).split())[:80]
    return ""

# ---------- DOM helpers (do parowania w promieniu) ----------

def _text_nodes(root: Tag):
    for el in root.descendants:
        if isinstance(el, NavigableString):
            txt = str(el)
            if txt.strip():
                yield el, txt

def _nearest_common_ancestor(a: Tag, b: Tag) -> tuple[Tag | None, int]:
    if a is b:
        return a, 0
    pa, pb = [], []
    x = a
    while isinstance(x, Tag) and x is not None:
        pa.append(x); x = x.parent
    y = b
    while isinstance(y, Tag) and y is not None:
        pb.append(y); y = y.parent
    pa = pa[::-1]; pb = pb[::-1]
    lca = None; i = 0
    while i < min(len(pa), len(pb)) and pa[i] is pb[i]:
        lca = pa[i]; i += 1
    if lca is None:
        return None, 10**9
    da = len(pa) - i
    db = len(pb) - i
    return lca, da + db

def find_phone_nodes(soup: BeautifulSoup) -> list[tuple[Tag, str]]:
    out: list[tuple[Tag, str]] = []
    for node, txt in _text_nodes(soup):
        for m in PHONE_RE.finditer(txt):
            ph = clean_phone(m.group(0))
            if ph:
                out.append((node.parent if isinstance(node.parent, Tag) else soup, ph))
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if href.startswith("tel:"):
            from urllib.parse import unquote
            ph = clean_phone(unquote(href.split(":",1)[1]))
            if ph:
                out.append((a, ph))
    return out

def find_email_nodes(soup: BeautifulSoup) -> list[tuple[Tag, str]]:
    out: list[tuple[Tag, str]] = []
    for node, txt in _text_nodes(soup):
        for m in EMAIL_RE.finditer(txt):
            out.append((node.parent if isinstance(node.parent, Tag) else soup, m.group(0)))
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            from urllib.parse import unquote
            addr = unquote(href.split(":",1)[1]).split("?",1)[0]
            if EMAIL_RE.fullmatch(addr):
                out.append((a, addr))
    return out

def pair_phones_emails(soup: BeautifulSoup, dom_threshold: int = 6) -> tuple[list[tuple[str, str | None]], list[str]]:
    phones = find_phone_nodes(soup)
    emails = find_email_nodes(soup)

    paired: list[tuple[str, str | None]] = []
    used_email_idx: set[int] = set()

    for pnode, ph in phones:
        best_i = None
        best_d = 10**9
        for i, (enode, _) in enumerate(emails):
            _, dist = _nearest_common_ancestor(pnode, enode)
            if dist < best_d:
                best_d = dist; best_i = i
        if best_i is not None and best_d <= dom_threshold:
            paired.append((ph, emails[best_i][1]))
            used_email_idx.add(best_i)
        else:
            paired.append((ph, None))

    orphan_emails = [em for i, (_, em) in enumerate(emails) if i not in used_email_idx]
    return paired, orphan_emails

