# Schema — kontext-sync

Dieser Skill definiert kein eigenes neues Datenschema — er orchestriert zwei
bestehende Kontrakte des Kontext-Layers:

- **`kontext/`-Ordner-Format** (Kanzlei-Profil, Mandate, Kontakte):
  [`core/context/README.md`](../../../core/context/README.md), Beispiel:
  [`core/context/beispiel-kontext/`](../../../core/context/beispiel-kontext/).
- **Adapter-Vertrag** (Mapping, Manifest, Konflikt-Handling):
  [`core/adapters/README.md`](../../../core/adapters/README.md),
  Referenz-Implementierung:
  [`core/adapters/filesystem/README.md`](../../../core/adapters/filesystem/README.md).

## Smoke-Test-Fixture (`smoke/`)

Ausschließlich für den Install-Smoke-Test (`tests/test_install_smoke.py`, der
den `filesystem`-Adapter aus dem reinen Plugin-Cache heraus laufen lässt):

- [`smoke/quelle/mandate-akte.md`](smoke/quelle/mandate-akte.md) — fiktive
  externe Quelldatei.
- [`smoke/mapping.json`](smoke/mapping.json) — Mapping auf
  `mandate/smoke-akte.md` im (zur Laufzeit frisch angelegten) Ziel-Ordner.

`--kontext`- und `--manifest`-Ziel werden vom Adapter beim `pull`-Lauf frisch
angelegt, liegen also nicht im Repo.
