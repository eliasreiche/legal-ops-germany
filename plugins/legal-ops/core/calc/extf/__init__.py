"""extf — DATEV-EXTF-Buchungsstapel (Kategorie 21, Format 700).

Export (JSON → EXTF): siehe executor.py.
Import (EXTF → strukturierte Werte): siehe parser.py (additiv, das Gegenstück
zum Writer — der Writer ist das Round-Trip-Orakel des Parsers).
"""

from .parser import (  # noqa: F401
    ExtfBuchung,
    ExtfParseFehler,
    ExtfStapel,
    parse_extf,
    parse_extf_datei,
)
