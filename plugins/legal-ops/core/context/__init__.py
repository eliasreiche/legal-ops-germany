"""core/context — Schema und Prüf-Logik des `kontext/`-Ordners (D11, D19).

Öffentliche API: siehe schema.py; CLI: validator.py.
"""
from .schema import (  # noqa: F401
    ABSCHNITTE_MANDAT,
    ISO_DATUM_RE,
    KONTEXT_BEREICHE,
    PFLICHTFELDER_MANDAT,
    STATUS_WERTE,
    lade_frontmatter,
    lese_mandate,
    pruefe_kanzlei_datei,
    pruefe_kontext_verzeichnis,
    pruefe_mandat_datei,
    pruefe_mandat_text,
)
