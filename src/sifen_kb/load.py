"""Carga de `kb/` y del manifiesto, con índices derivados (nada de esto se almacena).

`load_kb(root)` nunca aborta al primer error: acumula los errores de carga en `KB.errors`
(ruta: mensaje) para que `sifen check` los muestre todos juntos.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from sifen_kb.model import (
    DocumentSource,
    Effect,
    Field,
    Issue,
    KBMeta,
    SourceRevision,
    SourcesManifest,
    Validation,
)
from sifen_kb.rawio import RawStore
from sifen_kb.yamlio import KBYamlError, load_kb_file

Entity = Field | Validation


def find_root(start: Path | None = None) -> Path:
    """Sube desde `start` (o el cwd) hasta encontrar `pyproject.toml` + `kb/` o `sources.manifest.yaml`."""
    p = (start or Path.cwd()).resolve()
    for c in (p, *p.parents):
        if (c / "pyproject.toml").exists() and (
            (c / "kb").is_dir() or (c / "sources.manifest.yaml").exists()
        ):
            return c
    return p


@dataclass
class KB:
    root: Path
    meta: KBMeta | None = None
    documents: dict[str, DocumentSource] = field(default_factory=dict)
    fields: dict[str, Field] = field(default_factory=dict)
    validations: dict[str, Validation] = field(default_factory=dict)
    issues: dict[str, Issue] = field(default_factory=dict)
    manifest: SourcesManifest = field(default_factory=SourcesManifest)
    errors: list[str] = field(default_factory=list)
    paths: dict[str, Path] = field(default_factory=dict)
    """clave de entidad / DocId / IssueId -> archivo de origen."""

    _effects: dict[str, tuple[DocumentSource, Effect]] = field(default_factory=dict)
    _raw: RawStore | None = None

    def reindex(self) -> KB:
        """Reconstruye el índice de efectos desde `documents` (tras armar o modificar una KB en memoria)."""
        self._effects = {e.id: (d, e) for d in self.documents.values() for e in d.effects}
        return self

    # --- acceso -----------------------------------------------------------------------------
    @property
    def raw(self) -> RawStore:
        if self._raw is None:
            self._raw = RawStore(self.root)
        return self._raw

    def entity(self, key: str) -> Entity | None:
        return self.fields.get(key) or self.validations.get(key)

    def entities(self) -> dict[str, Entity]:
        return {**self.fields, **self.validations}

    def is_curated(self, key: str) -> bool:
        return self.entity(key) is not None

    def effect(self, effect_id: str) -> Effect:
        return self._effects[effect_id][1]

    def has_effect(self, effect_id: str) -> bool:
        return effect_id in self._effects

    def doc_of(self, effect_id: str) -> DocumentSource:
        return self._effects[effect_id][0]

    def all_effects(self) -> list[Effect]:
        return [e for _, e in self._effects.values()]

    def effects_targeting(self, key: str) -> list[Effect]:
        return [e for _, e in self._effects.values() if e.target == key]

    # --- índices derivados ----------------------------------------------------------------
    def code_index(self) -> dict[str, list[tuple[str, int]]]:
        """código -> [(clave de validación, índice de versión)], incluidas lápidas."""
        idx: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for key, v in self.validations.items():
            for i, ver in enumerate(v.versions):
                if ver.code:
                    idx[ver.code].append((key, i))
        return dict(idx)

    def id_index(self) -> dict[str, list[str]]:
        """ID SIFEN (p. ej. D208) -> claves de entidad (campo y/o validación)."""
        idx: dict[str, list[str]] = defaultdict(list)
        for key, e in self.entities().items():
            idx[e.id].append(key)
        return dict(idx)

    def xml_name_index(self) -> dict[str, list[str]]:
        idx: dict[str, list[str]] = defaultdict(list)
        for key, f in self.fields.items():
            for ver in f.versions:
                if ver.xml_name and key not in idx[ver.xml_name]:
                    idx[ver.xml_name].append(key)
        return dict(idx)

    # --- manifiesto ---------------------------------------------------------------------------
    def revisions_of(self, doc_id: str) -> list[SourceRevision]:
        return sorted((r for r in self.manifest.revisions if r.doc == doc_id), key=lambda r: r.retrieved_at)

    def latest_revision(self, doc_id: str) -> SourceRevision | None:
        revs = self.revisions_of(doc_id)
        return revs[-1] if revs else None

    def revision(self, doc_id: str, sha256: str) -> SourceRevision | None:
        return next((r for r in self.manifest.revisions if r.doc == doc_id and r.sha256 == sha256), None)

    def horizon(self) -> date | None:
        """Fecha del último `source check` limpio (sin URLs sin registrar)."""
        clean = [c.at.date() for c in self.manifest.checks if not c.unregistered]
        return max(clean) if clean else None


def _load_one[T](kb: KB, path: Path, model: type[T]) -> T | None:
    try:
        data = load_kb_file(path)
        return model.model_validate(data)  # type: ignore[attr-defined]
    except (KBYamlError, ValidationError, OSError) as e:
        kb.errors.append(f"{path.relative_to(kb.root)}: {e}")
        return None


def load_manifest(root: Path) -> SourcesManifest:
    p = root / "sources.manifest.yaml"
    if not p.exists():
        return SourcesManifest()
    return SourcesManifest.model_validate(load_kb_file(p) or {})


def load_kb(root: Path | None = None) -> KB:
    root = find_root(root)
    kb = KB(root=root)
    try:
        kb.manifest = load_manifest(root)
    except (KBYamlError, ValidationError) as e:
        kb.errors.append(f"sources.manifest.yaml: {e}")

    kbdir = root / "kb"
    meta_p = kbdir / "_meta.yaml"
    if meta_p.exists():
        kb.meta = _load_one(kb, meta_p, KBMeta)

    for p in sorted((kbdir / "documents").glob("*.yaml")):
        d = _load_one(kb, p, DocumentSource)
        if d is None:
            continue
        if d.id in kb.documents:
            kb.errors.append(f"{p.relative_to(root)}: documento {d.id} duplicado")
            continue
        kb.documents[d.id] = d
        kb.paths[d.id] = p
        for e in d.effects:
            kb._effects[e.id] = (d, e)

    for sub, model, target in (("fields", Field, kb.fields), ("validations", Validation, kb.validations)):
        for p in sorted((kbdir / sub).glob("*/*.yaml")):
            ent = _load_one(kb, p, model)
            if ent is None:
                continue
            if ent.key in target:  # type: ignore[attr-defined]
                kb.errors.append(f"{p.relative_to(root)}: entidad {ent.key} duplicada")  # type: ignore[attr-defined]
                continue
            target[ent.key] = ent  # type: ignore[attr-defined,index]
            kb.paths[ent.key] = p  # type: ignore[attr-defined]

    for p in sorted((kbdir / "issues").glob("*.yaml")):
        iss = _load_one(kb, p, Issue)
        if iss is not None:
            kb.issues[iss.id] = iss
            kb.paths[iss.id] = p
    return kb
