from dataclasses import dataclass

@dataclass(frozen=True)
class Hit:
    source_domain: str
    username: str      # np. tytuł sekcji/strony; pusty gdy brak
    phone: str         # E.164 (np. +48123456789) lub ""
    email: str         # "" gdy brak
    url: str

@dataclass(frozen=True)
class IPHit:
    ip: str
    url: str

@dataclass(frozen=True)
class FPEvent:
    url: str
    indicator: str   # np. "FingerprintJS", "Canvas FP"
    evidence: str    # krótki fragment/kontext
