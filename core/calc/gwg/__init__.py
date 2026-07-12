"""gwg — regelbasiertes GwG-Risikoscoring (Anlagen 1/2 GwG), P3.

Öffentliche API:

    from gwg.rechner import (
        klassifiziere,        # Mandat-Dict -> Report-Rumpf (ohne meta)
        GwGEingabeFehler,     # ungültige Eingabe
        lade_kataloge,        # (anlage1, anlage2, hochrisiko_drittstaaten)
        FRAGEBOGEN_FELDER,    # zulässige Eingabefelder (Kontrakt)
        KLASSIFIKATIONEN,     # ('nicht_verpflichtet','unvollstaendig','niedrig','mittel','hoch')
    )

Deterministisch, offline, nur Standardbibliothek. Der zugehörige CLI-Executor
liegt bei plugins/compliance/skills/gwg-risiko-check/executor.py. Das Modell
rechnet nie selbst — es liest ausschließlich den erzeugten Report (P3).
"""
