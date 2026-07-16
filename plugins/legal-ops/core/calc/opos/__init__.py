"""opos — Auswertung offener Posten (Honorar-Mahnwesen, P3, deterministisch).

Nimmt offene Posten aus zwei Datei-Quellen (OPOS-CSV oder EXTF-Buchungsstapel
über core/calc/extf/parser.py), berechnet je Posten offenen Restbetrag und
Tage seit Fälligkeit, ordnet konfigurierbare Mahnstufen zu und priorisiert
(Betrag × Alter). Kein Verzugszins, keine rechtliche Verzugsfeststellung —
das bleibt Kanzleisache (siehe rechner.py). Siehe skills/honorar-mahnwesen.
"""

from .rechner import (  # noqa: F401
    MAHNSTUFEN_DEFAULT,
    OposEingabeFehler,
    Posten,
    bewerte,
    lade_mahnstufen_config,
    lade_opos_csv,
    stapel_zu_posten,
)
