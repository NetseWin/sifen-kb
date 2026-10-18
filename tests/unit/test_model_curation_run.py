"""Pruebas del modelo de la bitácora (`CurationRun`) y de la procedencia explícita (`RunOutput`).

Contrato (docs/arquitectura.md §F, §J): los registros existentes —sin `source`— siguen siendo válidos
y se reescriben byte a byte iguales; `source: backfill` exige `reason` y `recorded_at`, y `reason` /
`recorded_at` no se admiten fuera de `backfill`. `extra="forbid"` se mantiene en todos los modelos.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sifen_kb.model import CurationRun, RunOutput
from sifen_kb.yamlio import dump_kb, load_kb_text

SHA = "a" * 64
RECORDED = datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC)
MOTIVO = "la sesión editó con herramientas MCP y el hook no registró la salida"


def entry(**extra: object) -> dict:
    return {"path": "kb/validations/DE/D208c.yaml", "sha256": SHA, **extra}


def legacy_run_text() -> str:
    """Una corrida de hook tal como existe hoy: `outputs` sin `source`, en orden canónico de campos."""
    return dump_kb(
        {
            "session_id": "s1",
            "started_at": "2026-10-17T19:30:45Z",
            "tool": "claude-code",
            "inputs": [{"path": "CLAUDE.md", "sha256": "b" * 64}],
            "outputs": [entry()],
        }
    )


# --- esquema ---------------------------------------------------------------------------------------
def test_legacy_entry_without_source_stays_valid():
    o = RunOutput.model_validate(entry())
    assert (o.path, o.sha256, o.source, o.reason, o.recorded_at) == (
        "kb/validations/DE/D208c.yaml",
        SHA,
        None,
        None,
        None,
    )


def test_legacy_run_file_still_validates():
    run = CurationRun.model_validate(load_kb_text(legacy_run_text()))
    assert [o.source for o in run.outputs] == [None]
    assert [i.path for i in run.inputs] == ["CLAUDE.md"]


def test_hook_entry_is_valid_without_reason():
    o = RunOutput.model_validate(entry(source="hook"))
    assert (o.source, o.reason, o.recorded_at) == ("hook", None, None)


@pytest.mark.parametrize(
    "extra",
    [
        {"source": "backfill"},
        {"source": "backfill", "reason": MOTIVO},
        {"source": "backfill", "recorded_at": RECORDED},
        {"source": "backfill", "reason": "", "recorded_at": RECORDED},
        {"source": "backfill", "reason": "   ", "recorded_at": RECORDED},
    ],
)
def test_backfill_needs_reason_and_recorded_at(extra):
    with pytest.raises(ValidationError):
        RunOutput.model_validate(entry(**extra))


def test_backfill_with_reason_and_recorded_at_is_valid():
    o = RunOutput.model_validate(entry(source="backfill", reason=MOTIVO, recorded_at=RECORDED))
    assert (o.source, o.reason, o.recorded_at) == ("backfill", MOTIVO, RECORDED)


@pytest.mark.parametrize(
    "extra",
    [
        {"reason": MOTIVO},
        {"recorded_at": RECORDED},
        {"source": "hook", "reason": MOTIVO},
        {"source": "hook", "recorded_at": RECORDED},
    ],
)
def test_reason_and_recorded_at_only_exist_with_backfill(extra):
    with pytest.raises(ValidationError):
        RunOutput.model_validate(entry(**extra))


@pytest.mark.parametrize("extra", [{"origen": "hook"}, {"source": "hook", "when": RECORDED}])
def test_unknown_keys_in_an_output_are_rejected(extra):
    with pytest.raises(ValidationError):
        RunOutput.model_validate(entry(**extra))


def test_unknown_keys_in_the_run_are_rejected():
    base = {"session_id": "s1", "started_at": "2026-10-17T19:30:45Z", "tool": "claude-code"}
    with pytest.raises(ValidationError):
        CurationRun.model_validate({**base, "outputs": [entry(motivo=MOTIVO)]})
    with pytest.raises(ValidationError):
        CurationRun.model_validate({**base, "outputs": [], "sesion": "s1"})


def test_mixed_outputs_validate():
    run = CurationRun.model_validate(
        {
            "session_id": "s1",
            "started_at": "2026-10-17T19:30:45Z",
            "tool": "claude-code",
            "outputs": [
                entry(),
                entry(path="kb/a.yaml", source="backfill", reason=MOTIVO, recorded_at=RECORDED),
            ],
        }
    )
    assert [o.source for o in run.outputs] == [None, "backfill"]


# --- serialización ---------------------------------------------------------------------------------
def test_legacy_run_rewrite_is_byte_identical():
    text = legacy_run_text()
    run = CurationRun.model_validate(load_kb_text(text))
    out = dump_kb(run.model_dump(mode="json", exclude_none=True))
    assert out == text
    assert "source" not in out and "recorded_at" not in out


def test_backfill_entry_round_trips_canonically():
    run = CurationRun.model_validate(
        {
            "session_id": "s1",
            "started_at": "2026-10-17T19:30:45Z",
            "tool": "claude-code",
            "outputs": [
                entry(),
                entry(path="kb/a.yaml", source="backfill", reason=MOTIVO, recorded_at=RECORDED),
            ],
        }
    )
    text = dump_kb(run.model_dump(mode="json", exclude_none=True))
    again = dump_kb(CurationRun.model_validate(load_kb_text(text)).model_dump(mode="json", exclude_none=True))
    assert again == text
    assert "source: backfill" in text
    assert "recorded_at: 2026-10-18T10:00:00Z" in text  # sin microsegundos
    assert MOTIVO in text
    run2 = CurationRun.model_validate(load_kb_text(text))
    assert run2.outputs[1].reason == MOTIVO
    assert run2.outputs[1].recorded_at == RECORDED


def test_explicit_hook_source_is_serialized():
    run = CurationRun.model_validate(
        {
            "session_id": "s1",
            "started_at": "2026-10-17T19:30:45Z",
            "tool": "claude-code",
            "outputs": [entry(source="hook")],
        }
    )
    text = dump_kb(run.model_dump(mode="json", exclude_none=True))
    assert "source: hook" in text
    assert "reason" not in text and "recorded_at" not in text
