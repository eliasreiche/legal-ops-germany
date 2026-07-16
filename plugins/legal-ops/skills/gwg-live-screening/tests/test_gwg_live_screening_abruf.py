"""Tests für core/adapters/sanktionslisten/abruf.py (P4) — OHNE Netzwerk.

Getestet werden nur das URL-Format der beiden offiziellen Quellen und das
lokale Schreiben/Mergen von abruf-meta.json (schreibe_meta). Der echte Abruf
(_lade / main mit Netzwerk) wird in CI bewusst NICHT ausgeführt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "adapters"))

from sanktionslisten import abruf  # noqa: E402


def test_quellen_urls_sind_wohlgeformt_https():
    for schluessel in ("eu", "un"):
        quelle = abruf.QUELLEN[schluessel]
        p = urlparse(quelle["url"])
        assert p.scheme == "https", quelle["url"]
        assert p.netloc, quelle["url"]
        assert quelle["dateiname"].endswith(".xml")


def test_offizielle_hosts():
    assert "webgate.ec.europa.eu" in abruf.QUELLEN["eu"]["url"]
    assert "scsanctions.un.org" in abruf.QUELLEN["un"]["url"]


def test_schreibe_meta_neu(tmp_path):
    meta_pfad = abruf.schreibe_meta(tmp_path, {
        "un-consolidated.xml": {"url": "https://x", "abgerufen_am": "2026-07-16"}})
    daten = json.loads(meta_pfad.read_text(encoding="utf-8"))
    assert daten["un-consolidated.xml"]["abgerufen_am"] == "2026-07-16"


def test_schreibe_meta_merge_erhaelt_andere_liste(tmp_path):
    abruf.schreibe_meta(tmp_path, {
        "eu-fsf.xml": {"url": "https://eu", "abgerufen_am": "2026-07-01"}})
    # Zweiter Teil-Abruf nur der UN-Liste darf die EU-Metadaten nicht verwerfen.
    meta_pfad = abruf.schreibe_meta(tmp_path, {
        "un-consolidated.xml": {"url": "https://un", "abgerufen_am": "2026-07-16"}})
    daten = json.loads(meta_pfad.read_text(encoding="utf-8"))
    assert set(daten) == {"eu-fsf.xml", "un-consolidated.xml"}
    assert daten["eu-fsf.xml"]["abgerufen_am"] == "2026-07-01"


def test_heute_iso_format():
    heute = abruf._heute_iso()
    assert len(heute) == 10 and heute[4] == "-" and heute[7] == "-"
