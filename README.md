<!-- PHORN – README.md -->

<div align="center">

<picture>
  <!-- Light mode -->
  <source media="(prefers-color-scheme: light)" srcset="assets/phorn-logo-light.png">
  <!-- Dark mode -->
  <source media="(prefers-color-scheme: dark)"  srcset="assets/phorn-logo-light.png">
  <img alt="PHORN Logo" src="assets/phorn-logo-light.png" width="560">
</picture>

**Terminal Phone & Email Crawler (TUI + Playwright)**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/OSINT-Tool-orange.svg)](#)

</div>

---

PHORN to terminalowy skaner stron WWW, który:

- zbiera **numery telefonów (PL)** i **adresy e-mail** z witryny (w ramach jednej domeny),
- radzi sobie z częścią blokad JS/WAF (fallback do **Playwright/Chromium**, **interactive unlock**, **HTTP/2**),
- zapisuje wynik do **CSV**,
- pokazuje **na żywo** postęp i statystyki w czytelnym interfejsie **curses** (TUI).

> ⚠️ Używaj zgodnie z prawem i regulaminami serwisów. Projekt ma charakter edukacyjny/OSINT.

---

## Wymagania

- **Linux** (Debian/Ubuntu/Kali; inne dystrybucje też powinny działać).
- **Python 3.10+** (zalecane 3.11/3.12/3.13).
- Dostęp do Internetu; przy „trudnych” stronach — **HTTP/HTTPS proxy** (np. rezydencyjne).
- ~1 GB miejsca (Playwright pobiera Chromium).

---

## Instalacja (krok po kroku)

```bash
# 1) Pobierz repozytorium
git clone https://github.com/TwojeKonto/phorn.git phorn
cd phorn

# 2) Utwórz i aktywuj środowisko wirtualne Pythona
python3 -m venv .venv
source .venv/bin/activate

# 3) Zaktualizuj pip i zainstaluj zależności
pip install -U pip wheel
pip install aiohttp beautifulsoup4 playwright playwright-stealth "httpx[http2]" pyyaml tldextract rich pandas

# 4) Pobierz przeglądarkę dla Playwright
python -m playwright install chromium
# Na Kali/starszych systemach (gdy brakuje bibliotek):
# python -m playwright install --with-deps chromium
```

---

## Uruchomienie (TUI)

```bash
python crawl_contacts.py --domain example.com --live --concurrency 8 --max-pages 200 --output out/contacts_example.csv
```

Podczas skanowania zobaczysz w terminalu:

- postęp (%),
- liczbę stron odwiedzonych i pozostałych,
- liczbę znalezionych telefonów i e-maili,
- czas trwania.

---

## Opcje skanera

| Parametr         | Opis                                                                 |
|------------------|----------------------------------------------------------------------|
| `--domain`       | Domena startowa (bez `http://` / `https://`). **Wymagane**           |
| `--live`         | Użyj Playwright/Chromium do renderowania JS                          |
| `--concurrency`  | Liczba równoległych pobrań (domyślnie: `4`)                          |
| `--max-pages`    | Limit liczby stron do odwiedzenia                                    |
| `--output`       | Plik CSV z wynikami                                                  |
| `--config`       | Plik YAML z ustawieniami (patrz: [Tryb CLI + YAML](#tryb-cli--yaml)) |

---

## Tryb CLI + YAML

Możesz stworzyć plik `config.yaml`:

```yaml
domain: example.com
live: true
concurrency: 8
max_pages: 200
output: out/results.csv
```

I uruchomić:

```bash
python crawl_contacts.py --config config.yaml
```

---

## Struktura projektu

```
phorn/
├── crawl_contacts.py    # Główny skrypt skanera
├── utils/               # Pomocnicze moduły (regex, parser)
├── out/                 # Domyślny katalog wyników
└── README.md            # Ten plik
```

---

## Format wyników (CSV)

Plik CSV zawiera kolumny:

- `url` — adres strony źródłowej
- `phone` — numer telefonu
- `email` — adres e-mail
- `label` — kontekst w treści (opcjonalnie)
- `timestamp` — data i godzina zapisu

---

## Wydajność i dobre praktyki

- Większa wartość `--concurrency` = szybsze skanowanie, ale większe obciążenie dla serwera.
- `--live` jest wolniejsze niż tryb HTTP-only, ale lepiej radzi sobie z dynamicznymi stronami JS.
- Szanuj plik `robots.txt` i regulaminy serwisów.
- Przy dużych domenach rozważ podział skanu na kilka mniejszych sesji.

---

## Cloudflare / WAF — co działa, a co nie

- Wiele prostych blokad JS przechodzi dzięki Playwright + stealth.
- Bardziej zaawansowane WAF wymagają czasem interakcji (tryb „interactive unlock” w TUI).
- CAPTCHA obrazkowe nie są omijane automatycznie.

---

## Rozwiązywanie problemów

**Problem:** `playwright: command not found`  
**Rozwiązanie:**  
```bash
python -m pip install playwright
python -m playwright install --with-deps chromium
```

**Problem:** Błędy przy instalacji zależności systemowych  
**Rozwiązanie:** upewnij się, że używasz `sudo` i masz aktualne repozytoria pakietów (`apt update`).

**Problem:** Skrypt nie zapisuje wyników  
**Rozwiązanie:** sprawdź, czy katalog `out/` istnieje i masz prawa zapisu.

---

## FAQ

**Czy potrzebuję kluczy API?**  
Nie — narzędzie działa na publicznych stronach.

**Czy to legalne?**  
Tak, jeśli zbierasz dane z własnych zasobów lub masz na to zgodę. Nie łam prawa ani regulaminów.

**Czy narzędzie omija CAPTCHA/logowanie?**  
Nie. Projekt nie omija zabezpieczeń wymagających uwierzytelnienia.

**Czy działa na Windows/Mac?**  
Tak, ale oficjalnie testowane jest na Linuxie.

---

## Licencja

Projekt objęty licencją **Apache 2.0**.  
Pełna treść licencji znajduje się w pliku [LICENSE](LICENSE).
