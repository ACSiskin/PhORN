# PhORN
Asynchronous Python crawler to extract Polish phone numbers and optionally emails from a chosen domain. Curses-based UI, saves results to CSV with source domain, username, phone, email, and URL. Supports page limit, filtering, and pairing phone numbers with related emails.

Asynchroniczny crawler w Pythonie do wyciągania polskich numerów telefonów i opcjonalnie e-maili z wybranej domeny. Interfejs w curses, zapis wyników do CSV z danymi: domena źródłowa, username, telefon, e-mail, URL. Obsługa limitu stron, filtrowanie i parowanie numerów z mailami.

Funkcje
> Skany w obrębie pojedynczej domeny (http/https).

> Telefony: tylko PL (9 cyfr lub +48 + 9 cyfr; separatory dopuszczone).

> Maile: z tekstu i linków mailto: (opcjonalnie).

> Parowanie telefon ↔ e-mail na poziomie jednej strony (najbliższy węzeł DOM).

> username tylko przy rekordach z telefonem (np. nagłówek strony/profilu).

> CSV z kolumnami: source_domain, username, phone, email, url.

> UI w curses: nagłówek przypięty, log przewijany, status na dole.

> Łagodne zakończenie (Ctrl+C) z zapisem wyników.

Wymagania (Linux)
Python 3.10+ (zalecane 3.11)

Systemowe:

`sudo apt update`

`sudo apt install -y python3 python3-venv python3-pip`

`sudo apt install -y libncursesw5`

`sudo apt install -y ca-certificates`

Pakiety Pythona:

`python3 -m venv .venv`

`source .venv/bin/activate`

`pip install --upgrade pip`
`pip install aiohttp beautifulsoup4`

(Opcjonalnie, TYLKO jeśli planujesz później dodać render JS) Playwright:

`pip install playwright`
`playwright install chromium`
> Uwaga: na Windows do curses potrzebny będzie pip install windows-curses (Linux nie wymaga).

Struktura repo:

`phorn/`
  `__init__.py`
  `types.py          # struktury danych`
  
  `extract.py        # regexy, parsowanie i łączenie phone↔email na stronie`
  
  `net.py            # sieć, normalizacja linków`
  
  `crawl.py          # główna pętla crawl + callbacki do UI`
  
  `ui_curses.py      # interfejs w terminalu (logo, log, status)`
  
`main.py             # punkt startowy (prompty, zapis CSV)`

`README.md`

ak to działa (skrót techniczny)
Pobieramy HTML asynchronicznie (aiohttp), parsujemy BeautifulSoup.

Telefony i maile wyszukiwane są w:

tekście strony,

linkach tel: / mailto:.

Parowanie phone↔email odbywa się przez najbliższego wspólnego przodka w DOM (LCA) z progiem odległości (domyślnie 6).

username (np. nagłówek profilu/ogłoszenia) tylko wtedy, gdy na stronie znaleziono telefon.

Parametry i rozszerzenia (dev)
Normalizacja numerów – obecnie zostawiamy format “tak jak na stronie” (po lekkim czyszczeniu). Chcesz zawsze +48 123 456 789? Dodaj normalizację w extract.clean_phone().

Whitelist/Blacklist ścieżek – prosta modyfikacja w crawl.py przed queue.append(nxt).

Render JS – jeśli trafisz na treści ładowane JS (Snap/Cloudflare), dołóż opcjonalny fallback Playwrighta (mamy to gotowe w starszej wersji – można włączyć warunkowo).

Autosave/Resume – łatwo dodać zapis co X sekund i wznowienie z CSV.

Problemy i rozwiązania
Kursor/input “ucieka” w UI: upewnij się, że terminal ma UTF-8 i czcionkę monospace. W kodzie używamy locale.setlocale(LC_ALL, '') + rysujemy teksty przycinając do szerokości okna, więc nie powinno się zawijać (powiększ okno jeśli masz wąski terminal).

Brak wyników: część stron generuje dane JS-em. W tej bazowej wersji render JS jest wyłączony — rozważ włączenie fallbacku Playwright (patrz “Rozszerzenia”).

Za wolno: zwiększ limit równoległości w crawl.py (aktualnie pętla idzie sekwencyjnie), dodaj whitelistę ścieżek i wstępne filtry linków (odrzuć #, pliki .jpg/.png/.pdf/.zip/.css/.js, inne domeny).

Bezpieczeństwo i etyka
Szanuj robots.txt i warunki serwisu.

Nie bombarduj jednego hosta — zostaw minimalny await asyncio.sleep(…) i rozsądne limity.

Dane kontaktowe traktuj zgodnie z prawem i politykami prywatności.
