"""zuordnung — Dokument-Metadaten -> Mandats-Kandidaten (P3-Bibliothek).

Öffentliche API für die E-Mail-/Posteingang-Akten-Zuordnung, genutzt von
`plugins/legal-ops/skills/email-akten-zuordnung/executor.py` und künftig
von Skill #14 `posteingang-ocr-verteilung` (Welle 4). Reine
Standardbibliothek (nutzt intern `core/calc/matching`), kein
Netzwerkzugriff, keine Persistierung.

  - `az` — Aktenzeichen-Normalisierung und -Suche (Stufe Z0).
  - `parteisuche` — Parteiname-in-Text-Suche (Stufen Z1-Z4).
  - `zuordnung` — kombiniert beides zu `finde_kandidaten()`.
"""
from __future__ import annotations

from .az import az_gefunden_in_text, normalisiere_az
from .parteisuche import (
    SCHWELLE_MOEGLICH_DEFAULT,
    STUFE_MOEGLICH,
    STUFE_TREFFER,
    ParteiTreffer,
    suche_name_in_text,
)
from .zuordnung import (
    Dokument,
    Kandidat,
    Mandat,
    finde_kandidaten,
    vergleiche_dokument_mandat,
)

__all__ = [
    "normalisiere_az",
    "az_gefunden_in_text",
    "STUFE_TREFFER",
    "STUFE_MOEGLICH",
    "SCHWELLE_MOEGLICH_DEFAULT",
    "ParteiTreffer",
    "suche_name_in_text",
    "Dokument",
    "Mandat",
    "Kandidat",
    "finde_kandidaten",
    "vergleiche_dokument_mandat",
]
