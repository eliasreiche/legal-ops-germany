"""matching — wiederverwendbare Fuzzy-Matching-Bibliothek (P3).

Öffentliche API für Namensvergleich (natürliche und juristische Personen),
genutzt von `plugins/legal-ops/skills/konflikt-check-offline/executor.py`
und künftig von Skill #13 `gwg-live-screening` (Sanktionslisten-Abgleich,
Welle 3). Reine Standardbibliothek, kein Netzwerkzugriff, keine
Persistierung — siehe die einzelnen Module für Regelwerk und Grenzen:

  - `normalisierung` — Normalisierung (Kleinschreibung, Umlaute, Rechtsform-/
    Titel-Stripping, Interpunktion) und Token-Sortierung.
  - `koelner_phonetik` — Kölner Phonetik nach Standard-Definition.
  - `fuzzy` — Zeichenketten- und tokenbasierte Ähnlichkeitsmaße.
"""
from __future__ import annotations

from .fuzzy import sequenz_ratio, token_alignment_ratio
from .koelner_phonetik import code as koelner_code
from .koelner_phonetik import phonetisch_gleich
from .normalisierung import (
    RECHTSFORMEN,
    TITEL,
    normalisiere,
    sortierte_tokens,
    tokenisiere,
)

__all__ = [
    "normalisiere",
    "tokenisiere",
    "sortierte_tokens",
    "RECHTSFORMEN",
    "TITEL",
    "koelner_code",
    "phonetisch_gleich",
    "sequenz_ratio",
    "token_alignment_ratio",
]
