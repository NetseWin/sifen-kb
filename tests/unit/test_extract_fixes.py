"""Correcciones de extracción (`extraction/fixes.yaml`): `parse_fixes`, `load_fixes`, `apply_fixes` y
`RawRow.current`.

Sin PDF ni `raw/`: las filas se arman a mano con `Fila`/`Run` (las mismas estructuras que produce el
extractor), así que las pruebas son de milisegundos. El comportamiento afirmado es el real del código
(`extract_tables.apply_fixes`, `rawio.RawRow.current`); donde el contrato admite una lectura dudosa,
la prueba lo dice en su comentario.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sifen_kb.extract import FIXES_PATH, load_fixes
from sifen_kb.extract_tables import ExtractionError, Fila, Fix, apply_fixes, assign_occ, parse_fixes
from sifen_kb.normalize import normalize_text
from sifen_kb.pdf.ir import Change, Run
from sifen_kb.rawio import RawRow, row_from_dict

ROOT = Path(__file__).resolve().parents[2]
DOC = "NT_020"
SHA12 = "0d877d1fb16a"

# Campos obligatorios de una corrección (`occ` es opcional: 1 por defecto).
REQUIRED = ("id", "doc", "sha12", "page", "key", "attr", "original", "corrected", "motivo", "evidencia")


# --- ayudas ----------------------------------------------------------------------------------------


def fix_dict(**over: Any) -> dict[str, Any]:
    """Corrección válida (el ejemplo hipotético de extraction/fixes.yaml) con campos sobrescribibles."""
    base: dict[str, Any] = {
        "id": "FIX-0001",
        "doc": DOC,
        "sha12": SHA12,
        "page": 1,
        "key": "E82",
        "occ": 1,
        "attr": "id",
        "original": "E82",
        "corrected": "E827",
        "motivo": "el ID se imprime partido en dos renglones y el motor lo separa",
        "evidencia": "NT_020 pág. 1, imagen de la celda; ID consecutivo de E826",
    }
    base.update(over)
    return base


def fix(**over: Any) -> Fix:
    return Fix.model_validate(fix_dict(**over))


def fila(page: int, ident: str, **cells: str | list[Run]) -> Fila:
    """Fila de campos: `ident` es el texto de la celda ID (y, normalizado, la clave); el resto de las
    celdas son texto o una lista de `Run` (para resaltar parte del texto)."""
    runs: dict[str, list[Run]] = {"id": [Run(ident)]}
    for attr, value in cells.items():
        runs[attr] = [Run(value)] if isinstance(value, str) else list(value)
    return Fila("fields", page, normalize_text(ident), list(runs), runs, [page], (page, 0))


def filas(*items: Fila) -> list[Fila]:
    out = list(items)
    assign_occ(out)
    return out


def raw_row(
    cells: dict[str, str], raw_cells: dict[str, str], marks: list[dict[str, Any]], **kw: Any
) -> RawRow:
    return RawRow(
        doc=DOC,
        sha12=SHA12,
        page=1,
        key="X",
        occ=1,
        table="fields",
        header=[],
        cells=cells,
        raw_cells=raw_cells,
        marks=marks,
        **kw,
    )


def mark(raw: str, attr: str, change: str, text: str) -> dict[str, Any]:
    """Marca sobre `raw[attr]` en el offset de `text` (que debe aparecer una sola vez)."""
    assert raw.count(text) == 1, f"{text!r} debe aparecer una vez en {raw!r}"
    start = raw.index(text)
    return {"attr": attr, "change": change, "start": start, "end": start + len(text), "text": text}


# --- parse_fixes -----------------------------------------------------------------------------------


def test_parse_fixes_vacio() -> None:
    assert parse_fixes(None) == []
    assert parse_fixes([]) == []


def test_parse_fixes_lista_valida() -> None:
    fixes = parse_fixes([fix_dict(), fix_dict(id="FIX-0002", key="E83", occ=2, attr="description")])
    assert [f.id for f in fixes] == ["FIX-0001", "FIX-0002"]
    assert fixes[0] == Fix(**fix_dict())
    assert (fixes[1].key, fixes[1].occ, fixes[1].attr) == ("E83", 2, "description")


def test_parse_fixes_occ_es_opcional_y_vale_uno() -> None:
    data = fix_dict()
    del data["occ"]
    assert parse_fixes([data])[0].occ == 1


@pytest.mark.parametrize("bad", [{"id": "FIX-0001"}, "FIX-0001", 7])
def test_parse_fixes_exige_una_lista(bad: Any) -> None:
    # Un objeto suelto, un texto o un número NO son una lista de correcciones.
    with pytest.raises(ExtractionError, match="se esperaba una lista"):
        parse_fixes(bad)


@pytest.mark.parametrize("item", ["FIX-0001", 7, [fix_dict()], None])
def test_parse_fixes_rechaza_un_elemento_que_no_es_objeto(item: Any) -> None:
    with pytest.raises(ExtractionError, match=r"corrección n\.º 1 inválida"):
        parse_fixes([item])


@pytest.mark.parametrize("campo", REQUIRED)
def test_parse_fixes_campo_obligatorio_ausente(campo: str) -> None:
    data = fix_dict()
    del data[campo]
    with pytest.raises(
        ExtractionError, match=rf"(?s)corrección n\.º 1 inválida.*\n{campo}\n\s+Field required"
    ):
        parse_fixes([data])


@pytest.mark.parametrize(
    "over",
    [
        {"doc": "NT_24"},  # DocId mal formado
        {"doc": "nt_020"},
        {"sha12": "0D877D1FB16A"},  # sha12 en minúsculas
        {"sha12": "0d877d1fb16"},  # 11 caracteres
        {"sha12": "0d877d1fb16ab"},  # 13 caracteres
        {"page": "uno"},
        {"occ": "dos"},
        {"id": None},
        {"original": None},
        {"extra": "campo desconocido"},  # `extra="forbid"`: una clave desconocida es un error
    ],
    ids=lambda o: next(iter(o)) + "=" + str(next(iter(o.values()))),
)
def test_parse_fixes_valor_invalido(over: dict[str, Any]) -> None:
    with pytest.raises(ExtractionError, match=r"corrección n\.º 1 inválida"):
        parse_fixes([fix_dict(**over)])


def test_parse_fixes_numera_la_correccion_defectuosa_y_cita_la_fuente() -> None:
    bad = fix_dict(id="FIX-0002")
    del bad["evidencia"]
    with pytest.raises(ExtractionError, match=r"otro\.yaml: corrección n\.º 2 inválida"):
        parse_fixes([fix_dict(), bad], "otro.yaml")


def test_parse_fixes_ids_repetidos() -> None:
    with pytest.raises(ExtractionError, match="ids repetidos: FIX-0001"):
        parse_fixes([fix_dict(), fix_dict(key="E83"), fix_dict(id="FIX-0002")])


# --- load_fixes: YAML real (KBLoader: todo escalar es str) -----------------------------------------

YAML_VALIDO = """\
# extraction/fixes.yaml de prueba: admite comentarios (no es kb/)
- id: FIX-0001
  doc: NT_020
  sha12: 123456789012       # solo dígitos: con un YAML común sería un entero
  page: 1
  key: E82
  attr: id
  original: E82
  corrected: E827
  motivo: el ID se imprime partido en dos renglones
  evidencia: NT_020 pág. 1, imagen de la celda
- id: FIX-0002
  doc: NT_014
  sha12: 5320a52a9152
  page: 3
  key: 1400 / 1401
  occ: 2
  attr: code
  original: 1400 / 1401
  corrected: 1401
  motivo: códigos fusionados
  evidencia: NT_014 pág. 3
"""


def _write_fixes(root: Path, text: str) -> None:
    p = root / FIXES_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_load_fixes_sin_archivo_no_hay_correcciones(tmp_path: Path) -> None:
    assert load_fixes(tmp_path) == []


def test_load_fixes_yaml_valido_convierte_los_escalares(tmp_path: Path) -> None:
    _write_fixes(tmp_path, YAML_VALIDO)
    fixes = load_fixes(tmp_path)
    assert [(f.id, f.doc, f.sha12, f.page, f.occ) for f in fixes] == [
        ("FIX-0001", "NT_020", "123456789012", 1, 1),
        ("FIX-0002", "NT_014", "5320a52a9152", 3, 2),
    ]
    assert fixes[1].original == "1400 / 1401"


@pytest.mark.parametrize(
    ("text", "mensaje"),
    [
        ("{}\n", "se esperaba una lista"),  # un mapa suelto
        ("- id: [sin cerrar\n", "YAML inválido"),
        ("- id: FIX-0001\n  id: FIX-0002\n", "clave duplicada"),
        ("- &a {id: FIX-0001}\n- *a\n", "anchor no permitido|alias no permitido"),
        ("- id: FIX-0001\n", "corrección n.º 1 inválida"),  # faltan campos
    ],
)
def test_load_fixes_yaml_invalido_es_error_de_extraccion(tmp_path: Path, text: str, mensaje: str) -> None:
    _write_fixes(tmp_path, text)
    with pytest.raises(ExtractionError, match=mensaje):
        load_fixes(tmp_path)


def test_load_fixes_ids_repetidos_en_el_yaml(tmp_path: Path) -> None:
    _write_fixes(tmp_path, YAML_VALIDO.replace("FIX-0002", "FIX-0001"))
    with pytest.raises(ExtractionError, match="ids repetidos: FIX-0001"):
        load_fixes(tmp_path)


def test_el_fixes_yaml_del_repositorio_es_valido() -> None:
    # Hoy es `[]`; si alguien agrega correcciones, deben cumplir el esquema.
    fixes = load_fixes(ROOT)
    assert len({f.id for f in fixes}) == len(fixes)


# --- apply_fixes -----------------------------------------------------------------------------------


def test_apply_fixes_corrige_la_fila_indicada_y_solo_esa() -> None:
    a = fila(1, "E826", description="Descripción A")
    b = fila(1, "E82", description="Descripción B")
    c = fila(2, "E82", description="Descripción C")  # misma clave en otra página
    rows = filas(a, b, c)

    ids = apply_fixes(
        DOC, SHA12, rows, [fix(attr="description", original="Descripción B", corrected="Nueva B")]
    )

    assert ids == ["FIX-0001"]
    assert b.cells()["description"] == "Nueva B"
    assert b.fix_ids == ["FIX-0001"]
    assert a.cells()["description"] == "Descripción A" and a.fix_ids == []
    assert c.cells()["description"] == "Descripción C" and c.fix_ids == []
    # raw_cells conserva lo extraído; cells y to_dict() llevan lo corregido.
    assert b.raw_cells()["description"] == "Descripción B"
    d = b.to_dict()
    assert d["cells"]["description"] == "Nueva B"
    assert d["raw_cells"]["description"] == "Descripción B"
    assert d["fix_ids"] == ["FIX-0001"]
    assert d["marks"] == [] and d["changes"] == {}


def test_apply_fixes_compara_y_guarda_normalizado() -> None:
    row = fila(1, "E82", description="Primer renglón\nsegundo   renglón")
    rows = filas(row)
    apply_fixes(
        DOC,
        SHA12,
        rows,
        [
            fix(
                attr="description",
                original="  Primer renglón segundo renglón ",
                corrected="Texto\ncorregido ",
            )
        ],
    )
    assert row.cells()["description"] == "Texto corregido"
    assert row.raw_cells()["description"] == "Primer renglón\nsegundo   renglón"


def test_apply_fixes_varias_correcciones_en_orden_y_ids_en_la_fila() -> None:
    row = fila(1, "E82", description="uno", length="2")
    rows = filas(row)
    ids = apply_fixes(
        DOC,
        SHA12,
        rows,
        [
            fix(id="FIX-0001", attr="description", original="uno", corrected="UNO"),
            fix(id="FIX-0002", attr="length", original="2", corrected="3"),
        ],
    )
    assert ids == ["FIX-0001", "FIX-0002"]
    assert row.fix_ids == ["FIX-0001", "FIX-0002"]
    assert row.cells() == {"id": "E82", "description": "UNO", "length": "3"}


def test_apply_fixes_corregir_el_id_cambia_la_clave_y_renumera_occ() -> None:
    primera = fila(1, "E82", description="x")
    segunda = fila(1, "E82", description="y")
    rows = filas(primera, segunda)
    assert (primera.occ, segunda.occ) == (1, 2)

    # `occ` y `key` de la corrección son los de la extracción, ANTES de corregir.
    apply_fixes(DOC, SHA12, rows, [fix(occ=2)])

    assert segunda.key == "E827" and segunda.cells()["id"] == "E827"
    assert segunda.occ == 1
    assert primera.key == "E82" and primera.occ == 1
    assert segunda.to_dict()["key"] == "E827"


def test_apply_fixes_occ_elige_la_segunda_aparicion() -> None:
    primera = fila(1, "E82", description="x")
    segunda = fila(1, "E82", description="x")
    rows = filas(primera, segunda)
    apply_fixes(DOC, SHA12, rows, [fix(occ=2, attr="description", original="x", corrected="X")])
    assert primera.cells()["description"] == "x"
    assert segunda.cells()["description"] == "X"


@pytest.mark.parametrize("over", [{"doc": "NT_021"}, {"sha12": "ffffffffffff"}])
def test_apply_fixes_ignora_las_correcciones_de_otra_revision(over: dict[str, Any]) -> None:
    row = fila(1, "E82")
    # Ni siquiera se busca la fila: una corrección de otra revisión no es de este documento.
    assert apply_fixes(DOC, SHA12, filas(row), [fix(**over, key="NO-EXISTE")]) == []
    assert row.cells()["id"] == "E82" and row.fix_ids == []


@pytest.mark.parametrize(
    "over",
    [{"page": 2}, {"key": "E99"}, {"occ": 2}],
    ids=["otra-pagina", "otra-clave", "otra-aparicion"],
)
def test_apply_fixes_rechaza_la_fila_inexistente(over: dict[str, Any]) -> None:
    row = fila(1, "E82")
    with pytest.raises(ExtractionError, match="FIX-0001: no hay fila"):
        apply_fixes(DOC, SHA12, filas(row), [fix(**over)])
    assert row.fix_ids == []


def test_apply_fixes_rechaza_un_atributo_inexistente() -> None:
    row = fila(1, "E82")
    with pytest.raises(ExtractionError, match="la fila no tiene el atributo 'length'"):
        apply_fixes(DOC, SHA12, filas(row), [fix(attr="length", original="1", corrected="2")])


@pytest.mark.parametrize("original", ["E83", "E8", "e82", ""])
def test_apply_fixes_rechaza_un_original_que_no_encuentra(original: str) -> None:
    row = fila(1, "E82")
    with pytest.raises(ExtractionError, match="el original no coincide con lo extraído"):
        apply_fixes(DOC, SHA12, filas(row), [fix(original=original)])
    # No se aplica nada a ciegas.
    assert row.cells()["id"] == "E82" and row.fix_ids == [] and row.key == "E82"


def test_apply_fixes_una_correccion_vieja_no_se_aplica_dos_veces() -> None:
    # Tras aplicarse, la celda ya vale `corrected`: repetir la misma corrección (original ya no coincide) falla.
    row = fila(1, "E82", description="uno")
    rows = filas(row)
    una = fix(attr="description", original="uno", corrected="UNO")
    apply_fixes(DOC, SHA12, rows, [una])
    with pytest.raises(ExtractionError, match="el original no coincide"):
        apply_fixes(DOC, SHA12, rows, [una])


@pytest.mark.parametrize("change", [Change.ADDED, Change.MODIFIED, Change.DELETED])
def test_apply_fixes_rechaza_un_atributo_con_tramos_resaltados(change: Change) -> None:
    row = fila(1, "E82", description=[Run("texto "), Run("resaltado", change)])
    original = row.cells()["description"]
    with pytest.raises(ExtractionError, match="tiene tramos resaltados.*RawRow.current"):
        apply_fixes(DOC, SHA12, filas(row), [fix(attr="description", original=original, corrected="otro")])
    assert row.fix_ids == [] and row.cells()["description"] == original


def test_apply_fixes_el_resaltado_de_otro_atributo_no_bloquea() -> None:
    row = fila(1, "E82", description="uno", observations=[Run("agregado", Change.ADDED)])
    apply_fixes(DOC, SHA12, filas(row), [fix(attr="description", original="uno", corrected="UNO")])
    assert row.cells()["description"] == "UNO"
    assert row.marks()[0]["attr"] == "observations"


def test_apply_fixes_un_resaltado_solo_de_espacios_no_cuenta_como_tramo() -> None:
    # `Fila.marks()` ignora los tramos en blanco (igual que `changes()`): no hay nada que RawRow.current deba
    # quitar, así que la corrección se admite.
    row = fila(1, "E82", description=[Run("uno"), Run("  ", Change.DELETED)])
    apply_fixes(DOC, SHA12, filas(row), [fix(attr="description", original="uno", corrected="UNO")])
    assert row.cells()["description"] == "UNO"
    assert row.marks() == []


def test_apply_fixes_resultado_vacio_sin_correcciones() -> None:
    row = fila(1, "E82")
    assert apply_fixes(DOC, SHA12, filas(row), []) == []
    assert row.to_dict()["fix_ids"] == []


# --- RawRow.current --------------------------------------------------------------------------------


def test_current_sin_marcas_devuelve_la_celda() -> None:
    row = raw_row(
        cells={"description": "Ocurrencia 1-1"},
        raw_cells={"description": "Ocurrencia\n  1-1"},
        marks=[],
    )
    assert row.current("description") == "Ocurrencia 1-1"


def test_current_sin_marcas_devuelve_la_celda_corregida_no_el_texto_crudo() -> None:
    row = raw_row(cells={"id": "E827"}, raw_cells={"id": "E82"}, marks=[], fix_ids=["FIX-0001"])
    assert row.current("id") == "E827"


def test_current_quita_un_tramo_tachado_y_normaliza() -> None:
    raw = "Código 1400 y 1401"
    row = raw_row(
        cells={"observations": normalize_text(raw)},
        raw_cells={"observations": raw},
        marks=[mark(raw, "observations", "deleted", "1400 y")],
    )
    # El hueco que deja el tramo (dos espacios seguidos) se colapsa al normalizar.
    assert row.current("observations") == "Código 1401"
    assert row.cells["observations"] == "Código 1400 y 1401"  # cells conserva TODO el texto impreso


def test_current_varios_tramos_tachados_y_conserva_agregados_y_modificados() -> None:
    raw = "A BORRAR1 B NUEVO C MOD D BORRAR2 E"
    marks = [
        mark(raw, "observations", "deleted", "BORRAR1"),
        mark(raw, "observations", "added", "NUEVO"),
        mark(raw, "observations", "modified", "MOD"),
        mark(raw, "observations", "deleted", "BORRAR2"),
    ]
    row = raw_row(cells={"observations": normalize_text(raw)}, raw_cells={"observations": raw}, marks=marks)
    assert row.current("observations") == "A B NUEVO C MOD D E"


def test_current_no_depende_del_orden_de_las_marcas() -> None:
    raw = "uno DOS tres CUATRO cinco"
    marks = [mark(raw, "a", "deleted", "DOS"), mark(raw, "a", "deleted", "CUATRO")]
    cells = {"a": normalize_text(raw)}
    ascendente = raw_row(cells, {"a": raw}, marks)
    descendente = raw_row(cells, {"a": raw}, list(reversed(marks)))
    assert ascendente.current("a") == descendente.current("a") == "uno tres cinco"


def test_current_solo_agregados_devuelve_todo_el_texto() -> None:
    raw = "texto NUEVO fin"
    row = raw_row(cells={"a": raw}, raw_cells={"a": raw}, marks=[mark(raw, "a", "added", "NUEVO")])
    assert row.current("a") == "texto NUEVO fin"


def test_current_todo_tachado_queda_vacio() -> None:
    raw = "Eliminado"
    row = raw_row(cells={"a": raw}, raw_cells={"a": raw}, marks=[mark(raw, "a", "deleted", raw)])
    assert row.current("a") == ""


def test_current_las_marcas_de_otro_atributo_no_afectan() -> None:
    raw = "Hola mundo cruel"
    # Mismos offsets en `b` que en `a`: si `current` mezclara atributos, a perdería "mundo".
    row = raw_row(
        cells={"a": raw, "b": raw},
        raw_cells={"a": raw, "b": raw},
        marks=[mark(raw, "b", "deleted", "mundo")],
    )
    assert row.current("a") == "Hola mundo cruel"
    assert row.current("b") == "Hola cruel"


def test_current_quita_antes_de_normalizar_los_offsets_son_del_texto_crudo() -> None:
    # Los offsets de `marks` son sobre raw_cells (con saltos de línea), no sobre cells: quitar el tramo
    # y recién entonces normalizar une "abc-" con "def" sin espacio.
    raw = "abc-\nBORRADO\ndef"
    row = raw_row(
        cells={"a": normalize_text(raw)},
        raw_cells={"a": raw},
        marks=[mark(raw, "a", "deleted", "BORRADO")],
    )
    assert row.current("a") == "abc-def"
    assert row.cells["a"] == "abc-BORRADO def"


# --- RawRow.current sobre marcas reales de Fila.to_dict() ------------------------------------------


def test_current_ida_y_vuelta_con_las_marcas_que_escribe_el_extractor() -> None:
    row = fila(
        3,
        "D208c",
        message=[
            Run("Si el receptor es "),
            Run("innominado ", Change.DELETED),
            Run("y monto "),
            Run("≥ 7.000.000", Change.ADDED),
        ],
        code=[Run("1321")],
    )
    d = row.to_dict()
    raw = row_from_dict(DOC, SHA12, d)

    assert d["changes"] == {"message": "modified"}
    assert raw.cells["message"] == "Si el receptor es innominado y monto ≥ 7.000.000"
    assert raw.current("message") == "Si el receptor es y monto ≥ 7.000.000"
    assert raw.current("code") == "1321"
    assert raw.current("id") == "D208c"
