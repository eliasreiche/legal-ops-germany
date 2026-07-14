"""core/calc/zeit — Dauer-Berechnung und Aggregation für Zeitwerte (P3).

Öffentliche API:

    from zeit.rechner import (
        dauer_minuten,          # start+ende ODER minuten -> Minuten (int)
        runde_auf_takt,         # Minuten -> auf Abrechnungstakt aufgerundet
        ZeitEintrag,            # (az, datum, minuten) für die Aggregation
        summe_je_az,            # Summen je Aktenzeichen
        summe_je_az_und_datum,  # Summen je (Aktenzeichen, Datum)
        ZeitEingabeFehler,      # ungültige Eingabe
    )

Reine Funktionen, nur Standardbibliothek, kein Datei-I/O. Genutzt vom
CLI-Executor plugins/legal-ops/skills/taetigkeitstext-rvg/executor.py; für
`passive-zeiterfassung` (dieselbe Welle) mit derselben API vorgesehen.
"""
from .rechner import (  # noqa: F401
    ZeitEingabeFehler,
    ZeitEintrag,
    dauer_minuten,
    runde_auf_takt,
    summe_je_az,
    summe_je_az_und_datum,
)
