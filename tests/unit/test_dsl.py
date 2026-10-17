"""Tests del DSL de condiciones (docs/arquitectura.md §K.1, §K.6, §G.5)."""

import dataclasses
import itertools
from decimal import Decimal

import pytest
from pydantic import TypeAdapter

from sifen_kb.dsl import (
    SIFEN_ID_RE,
    And,
    Cmp,
    Const,
    DslError,
    Exists,
    FieldRef,
    In,
    Not,
    Or,
    constants,
    evaluate,
    fields,
    literal_contains_constant,
    parse,
    unparse,
)
from sifen_kb.model import SifenId

# Condición real de D208c (NT 24, 7.000.000), polaridad "se viola cuando" (§G.5).
D208C = (
    "(not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and "
    "((exists(F023) and F023 >= 7000000) or (exists(F014) and F014 >= 7000000))"
)
D208C_TYPES = {"D011": "N", "D208": "N", "F014": "N", "F023": "N"}


# --- Lista blanca ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("expr", "fragment"),
    [
        # vacío
        ("", "vacía"),
        ("   \n  ", "vacía"),
        # atributos, subíndices y llamadas
        ("D011.real == 1", "atributos"),
        ("D011[0] == 1", "subíndices"),
        ("__import__('os')", "`__import__`"),
        ("__import__('os').system('ls')", "atributos"),
        ("len(D011) > 1", "llamada a `len`"),
        ("D011 == abs(D012)", "llamada a `abs`"),
        ("exists(D011) == 1", "no puede compararse"),
        ("exec('x')", "llamada a `exec`"),
        # lambda, comprensiones, walrus, f-strings, condicionales
        ("lambda: D011", "lambdas"),
        ("[D011 for D011 in (1, 2)]", "comprensiones"),
        ("{D011 for D011 in (1, 2)}", "comprensiones"),
        ("{D011: D012 for D011 in (1, 2)}", "comprensiones"),
        ("(D011 for D011 in (1, 2))", "comprensiones"),
        ("(D011 := 5)", ":="),
        ("D011 == (D012 := 5)", ":="),
        ("D011 := 5", "sintaxis"),
        ("D011 == f'{D012}'", "f-strings"),
        ("D011 == 1 if D012 == 2 else D013 == 3", "condicionales"),
        # True / False / None
        ("True", "`True`, `False` ni `None`"),
        ("False", "`True`, `False` ni `None`"),
        ("None", "`True`, `False` ni `None`"),
        ("D011 == True", "`True`, `False` ni `None`"),
        ("D011 != None", "`True`, `False` ni `None`"),
        ("D011 in (None, 1)", "`True`, `False` ni `None`"),
        # aritmética y unarios
        ("D011 + 1 > 5", "aritméticos"),
        ("D011 * 2 == 4", "aritméticos"),
        ("D011 // 2 == 4", "aritméticos"),
        ("D011 ** 2 == 4", "aritméticos"),
        ("-D011 < 0", "unarios"),
        ("D011 == -1", "unarios"),
        ("~D011 == 1", "unarios"),
        # operadores en mayúsculas
        ("D011 == 1 AND D208 == 5", "use `and`"),
        ("D011 == 1 OR D208 == 5", "use `or`"),
        ("NOT exists(D011)", "use `not`"),
        ("D011 == 1 And D208 == 5", "use `and`"),
        # nombres que no son IDs de campo
        ("foo == 1", "no es un ID de campo"),
        ("d011 == 1", "no es un ID de campo"),
        ("D011 == bar", "no es un ID de campo"),
        ("D1234 == 1", "no es un ID de campo"),
        ("exists(foo)", "ID de campo"),
        ("foo", "no es un ID de campo"),
        ("D011", "no puede usarse solo"),
        ("5", "constante sola"),
        ("'PYG'", "constante sola"),
        # comparaciones
        ("1 < D011 < 5", "encadenadas"),
        ("D011 == D012 == D013", "encadenadas"),
        ("D011 < 5 in (1, 2)", "encadenadas"),
        ("D011 is 5", "`is`"),
        ("D011 is not 5", "`is`"),
        ("D011 == (D012 == 1)", "operandos de una comparación"),
        ("D011 == (not D012)", "operandos de una comparación"),
        ("(D011, D012) == 1", "tuplas"),
        # in / not in
        ("D011 in [5, 6]", "listas ni conjuntos"),
        ("D011 in {5, 6}", "listas ni conjuntos"),
        ("D011 in 5", "tupla de constantes"),
        ("D011 in D012", "tupla de constantes"),
        ("D011 in ()", "vacía"),
        ("D011 in (D012, 5)", "solo admite constantes"),
        ("5 in (5, 6)", "lado izquierdo"),
        ("D011 not in [5]", "listas ni conjuntos"),
        # exists
        ("exists()", "exactamente un argumento"),
        ("exists(D011, D012)", "exactamente un argumento"),
        ("exists(5)", "ID de campo"),
        ("exists('D011')", "ID de campo"),
        ("exists(D011.x)", "ID de campo"),
        ("exists(x=D011)", "argumentos con nombre"),
        # formas numéricas y tipos de constante
        ("D011 == 1e3", "forma numérica"),
        ("D011 == 1_000", "forma numérica"),
        ("D011 == 0x10", "forma numérica"),
        ("D011 == 1.", "forma numérica"),
        ("D011 == .5", "forma numérica"),
        ("D011 == 1j", "complejos"),
        ("D011 == b'x'", "no permitida"),
        ("D011 == ...", "no permitida"),
        # sintaxis rota y atajos de otros lenguajes
        ("D011 ==", "sintaxis inválida"),
        ("D011 = 5", "use `==`"),
        ("D011 == 1 && D012 == 2", "use `and` / `or` en lugar de `&&` / `||`"),
        ("D011 == 1 || D012 == 2", "use `and` / `or` en lugar de `&&` / `||`"),
        ("!exists(D011)", "use `not`"),
        ("D011 == 1; D012 == 2", "sintaxis inválida"),
        ("(D011 == 1", "sintaxis inválida"),
        ("D011 == 'abc", "sintaxis inválida"),
        ("D011 == 1\x00", "sintaxis inválida"),
        ("D011 == " + "9" * 5000, "sintaxis inválida"),  # entero fuera del límite de Python
    ],
)
def test_dsl_whitelist(expr: str, fragment: str) -> None:
    with pytest.raises(DslError) as info:
        parse(expr)
    assert fragment in str(info.value)


def test_dsl_whitelist_error_has_column() -> None:
    with pytest.raises(DslError) as info:
        parse("D011 == 1 and foo == 2")
    assert info.value.col == 15
    assert "(columna 15)" in str(info.value)
    # la columna cuenta caracteres, no bytes UTF-8 (la ñ ocupa dos bytes)
    with pytest.raises(DslError) as info:
        parse("D100 == 'ñ' and foo == 1")
    assert info.value.col == 17
    with pytest.raises(DslError) as info:
        parse("D100 == 'ñ' and D011 == 1 AND D012 == 2")
    assert info.value.col == 27
    assert DslError("sin posición").col is None


def test_dsl_whitelist_uppercase_inside_string_is_fine() -> None:
    assert parse("D100 == 'A OR B AND NOT C'") == Cmp("==", FieldRef("D100"), Const("A OR B AND NOT C"))


def test_dsl_whitelist_known_fields() -> None:
    known = {"D011", "D208"}
    assert fields(parse("D011 == 1 and exists(D208)", known_fields=known)) == known
    for expr in ("D999 == 1", "exists(D999)", "D011 in (1, 2) or D999 not in (1,)", "5 == D999"):
        with pytest.raises(DslError, match="D999.*campos conocidos"):
            parse(expr, known_fields=known)
    # sin known_fields, cualquier ID con el patrón es válido
    assert fields(parse("D999 == 1")) == {"D999"}


def test_dsl_whitelist_limits() -> None:
    with pytest.raises(DslError, match="demasiado larga"):
        parse("D011 == 1 and " * 2000 + "D011 == 1")
    with pytest.raises(DslError, match="anidada|no analizable"):
        parse("not " * 1500 + "exists(D011)")


@pytest.mark.parametrize(
    "expr",
    [
        "D011 == 13",
        "13 == D011",
        "D011 == D012",
        "D011 != 13",
        "D011 < 1 or D011 <= 2 or D011 > 3 or D011 >= 4",
        "exists(D011)",
        "not exists(D011)",
        "not (D011 == 1)",
        "C002 in (5, 6, 7)",
        "C002 not in (5, 6, 7)",
        "C002 in (5,)",
        "D100 in ('PYG', 'USD')",
        "D100 == 'PYG'",
        'D100 == "PYG"',
        "F014 >= 1.5",
        "F014 >= 7000000.00",
        "((D011 == 1))",
        "(D011 == 1) and (D012 == 2)",
        "D011 == 1 and (D012 == 2 and D013 == 3)",
        "  D011   ==   1  ",
        "D011 == 1\n  and D012 == 2",
        "(\n  D011 == 1\n  or\n  D012 == 2\n)",
        "D011 == 1\r\nand D012 == 2",
        "D208c == 1 and GENFE010 == 2 and ASch03 == 3",
        D208C,
    ],
)
def test_dsl_whitelist_accepts(expr: str) -> None:
    parse(expr)


def test_dsl_id_pattern_matches_model() -> None:
    """El patrón local de IDs debe coincidir con `model.SifenId`."""
    adapter = TypeAdapter(SifenId)
    candidates = [
        "D011",
        "F014",
        "C002",
        "D208c",
        "GENFE010",
        "ASch03",
        "A1",
        "AAAAAAA999z",
        "d011",
        "D",
        "D1234",
        "D011C",
        "D011cc",
        "ABCDEFGH01",
        "1D01",
        "D_01",
        "D01 ",
        "",
    ]
    for candidate in candidates:
        try:
            adapter.validate_python(candidate)
            valid = True
        except ValueError:
            valid = False
        assert bool(SIFEN_ID_RE.fullmatch(candidate)) is valid, candidate


# --- IR inmutable, fields y constants ----------------------------------------------------------
def test_dsl_ir_shape_and_immutability() -> None:
    node = parse("exists(D011) and D011 != 13")
    assert node == And((Exists(FieldRef("D011")), Cmp("!=", FieldRef("D011"), Const(Decimal(13)))))
    assert parse("C002 not in (5, 'x')") == In(
        FieldRef("C002"), (Const(Decimal(5)), Const("x")), negated=True
    )
    assert parse("not exists(D011)") == Not(Exists(FieldRef("D011")))
    assert isinstance(parse("D011 == 1 or D012 == 2"), Or)
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.operands = ()  # type: ignore[misc]
    assert hash(parse(D208C)) == hash(parse(D208C))
    # un decimal conserva su precisión (sin pasar por float)
    assert parse("D011 == 0.1").right == Const(Decimal("0.1"))  # type: ignore[union-attr]


def test_dsl_and_or_are_flattened() -> None:
    assert parse("D011 == 1 and (D012 == 2 and D013 == 3)") == parse("D011 == 1 and D012 == 2 and D013 == 3")
    assert parse("(D011 == 1 or D012 == 2) or D013 == 3") == parse("D011 == 1 or D012 == 2 or D013 == 3")
    # pero and dentro de or (y viceversa) conservan su estructura
    node = parse("(D011 == 1 and D012 == 2) or D013 == 3")
    assert isinstance(node, Or)
    assert isinstance(node.operands[0], And)


def test_dsl_fields() -> None:
    assert fields(parse(D208C)) == {"D011", "D208", "F014", "F023"}
    assert fields(parse("C002 in (5, 6)")) == {"C002"}
    assert fields(parse("exists(D011) or D012 == D013")) == {"D011", "D012", "D013"}
    assert fields(parse("D100 == 'D999'")) == {"D100"}


def test_dsl_constants() -> None:
    assert constants(parse(D208C)) == [Decimal(13), Decimal(5), Decimal(7000000)]
    assert constants(parse("C002 in (5, 6, 7) and D100 == 'PYG' and F014 >= 1.5")) == [
        Decimal(5),
        Decimal(6),
        Decimal(7),
        "PYG",
        Decimal("1.5"),
    ]
    assert constants(parse("exists(D011)")) == []
    assert constants(parse("D011 == D012")) == []
    # un string numérico no se confunde con el número
    assert constants(parse("D011 == '5' or D011 == 5")) == ["5", Decimal(5)]


# --- unparse: texto canónico y round trip ------------------------------------------------------
ROUND_TRIP_EXPRS = [
    "D011 == 13",
    "13 == D011",
    "not exists(D011)",
    "not not exists(D011)",
    "not (D011 == 1)",
    "not (D011 == 1 and D012 == 2)",
    "not (D011 == 1 or exists(D012))",
    "not (D011 in (1, 2))",
    "C002 in (5, 6, 7)",
    "C002 not in (5,)",
    "D100 in ('PYG', 'USD') or D100 == 'EUR'",
    'D100 == "it\'s"',
    "D100 == 'say \"hi\"'",
    "D100 == 'ñandú ≥ 7'",
    "F014 >= 1.5",
    "F014 >= 1.50",
    "F014 >= 7000000",
    "(D011 == 1 or D012 == 2) and D013 == 3",
    "D011 == 1 or D012 == 2 and D013 == 3",
    "D011 == 1 and (D012 == 2 or D013 == 3)",
    "(D011 == 1 and D012 == 2) or (D013 == 3 and D014 == 4)",
    "((not exists(D011)))",
    D208C,
]


@pytest.mark.parametrize("expr", ROUND_TRIP_EXPRS)
def test_dsl_unparse_round_trip(expr: str) -> None:
    node = parse(expr)
    text = unparse(node)
    assert parse(text) == node
    assert unparse(parse(text)) == text  # idempotente


def test_dsl_unparse_canonical_text() -> None:
    assert unparse(parse(D208C)) == D208C  # la expresión real de §G.5 ya es canónica
    assert unparse(parse("  not   exists( D011 )  ")) == "not exists(D011)"
    assert unparse(parse("((D011==1))")) == "D011 == 1"
    assert (
        unparse(parse("D011 == 1 and (D012 == 2 and D013 == 3)")) == "D011 == 1 and D012 == 2 and D013 == 3"
    )
    assert unparse(parse("D011 == 1 or D012 == 2 and D013 == 3")) == "D011 == 1 or (D012 == 2 and D013 == 3)"
    assert unparse(parse("not D011 == 1")) == "not (D011 == 1)"
    assert unparse(parse("D011 == 1\n and\n D012 == 2")) == "D011 == 1 and D012 == 2"
    assert unparse(parse("C002 in (5,)")) == "C002 in (5,)"
    assert unparse(parse('D100 == "PYG"')) == "D100 == 'PYG'"


# --- Evaluación trivalente (Kleene) ------------------------------------------------------------
T, F, U = True, False, None
_ATOM_VALUES: dict[bool | None, str | None] = {T: "1", F: "2", U: None}
_RANK = {F: 0, U: 1, T: 2}  # Kleene: and = mínimo, or = máximo, not = inversión del orden F < U < T
_FROM_RANK = {0: F, 1: U, 2: T}


def _atoms(*states: bool | None) -> dict[str, str | None]:
    """Valores del XML para que `D00k == 1` valga el k-ésimo estado (T: "1", F: "2", U: ausente)."""
    return {f"D00{k}": _ATOM_VALUES[state] for k, state in enumerate(states, start=1)}


def _operands(n: int) -> list[str]:
    return [f"D00{k} == 1" for k in range(1, n + 1)]


def test_dsl_kleene() -> None:
    # Átomos: T = "D001 == 1" con D001="1"; F = con D001="2"; U = con D001 ausente.
    for state, expected in ((T, T), (F, F), (U, U)):
        assert evaluate(parse("D001 == 1"), _atoms(state)) is expected

    # NOT
    for state, expected in ((T, F), (F, T), (U, U)):
        assert evaluate(parse("not D001 == 1"), _atoms(state)) is expected

    # AND y OR: tablas de verdad completas (a, b) -> resultado
    and_table = {
        (T, T): T, (T, F): F, (T, U): U,
        (F, T): F, (F, F): F, (F, U): F,
        (U, T): U, (U, F): F, (U, U): U,
    }  # fmt: skip
    or_table = {
        (T, T): T, (T, F): T, (T, U): T,
        (F, T): T, (F, F): F, (F, U): U,
        (U, T): T, (U, F): U, (U, U): U,
    }  # fmt: skip
    for (a, b), expected in and_table.items():
        assert evaluate(parse("D001 == 1 and D002 == 1"), _atoms(a, b)) is expected, (a, b)
    for (a, b), expected in or_table.items():
        assert evaluate(parse("D001 == 1 or D002 == 1"), _atoms(a, b)) is expected, (a, b)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_dsl_kleene_matches_reference_and_ignores_order(n: int) -> None:
    """Contra un oráculo independiente (mínimo/máximo sobre F < U < T) y para todo orden de operandos."""
    atoms = _operands(n)
    for states in itertools.product((T, F, U), repeat=n):
        values = _atoms(*states)
        and_expected = _FROM_RANK[min(_RANK[s] for s in states)]
        or_expected = _FROM_RANK[max(_RANK[s] for s in states)]
        for order in itertools.permutations(atoms):
            assert evaluate(parse(" and ".join(order)), values) is and_expected, (states, order)
            assert evaluate(parse(" or ".join(order)), values) is or_expected, (states, order)
            assert evaluate(parse("not (" + " and ".join(order) + ")"), values) is _kleene_not_ref(
                and_expected
            )


def _kleene_not_ref(state: bool | None) -> bool | None:
    return _FROM_RANK[2 - _RANK[state]]


def test_dsl_kleene_nested_and_de_morgan() -> None:
    for a, b, c in itertools.product((T, F, U), repeat=3):
        values = _atoms(a, b, c)
        x, y, z = (_RANK[s] for s in (a, b, c))
        nested = evaluate(parse("(D001 == 1 or D002 == 1) and not D003 == 1"), values)
        assert nested is _FROM_RANK[min(max(x, y), 2 - z)]
        # De Morgan se cumple en lógica trivalente
        left = evaluate(parse("not (D001 == 1 and D002 == 1)"), values)
        right = evaluate(parse("not D001 == 1 or not D002 == 1"), values)
        assert left is right


def test_dsl_unguarded_absent_field_is_unknown_regardless_of_order() -> None:
    # Lectura sin guarda de un campo ausente: UNKNOWN, y el orden no cambia el resultado.
    values: dict[str, str | None] = {"D208": None, "F014": "8000000"}
    assert evaluate(parse("D208 == 5 and F014 >= 7000000"), values) is None
    assert evaluate(parse("F014 >= 7000000 and D208 == 5"), values) is None
    assert evaluate(parse("D208 == 5 or F014 >= 7000000"), values) is True
    assert evaluate(parse("F014 >= 7000000 or D208 == 5"), values) is True
    # Con un operando falso, `and` es False en cualquier orden aunque el otro sea UNKNOWN.
    values["F014"] = "1"
    assert evaluate(parse("D208 == 5 and F014 >= 7000000"), values) is False
    assert evaluate(parse("F014 >= 7000000 and D208 == 5"), values) is False
    # Un campo ausente que no está en el diccionario es igual que uno con valor None.
    assert evaluate(parse("D208 == 5"), {}) is None
    assert evaluate(parse("D208 == D209"), {"D209": "5"}) is None
    assert evaluate(parse("D208 in (5, 6)"), {}) is None
    assert evaluate(parse("D208 not in (5, 6)"), {}) is None


def test_dsl_exists_never_unknown() -> None:
    node = parse("exists(D011)")
    assert evaluate(node, {"D011": "1"}) is True
    assert evaluate(node, {"D011": ""}) is True  # presente aunque vacío
    assert evaluate(node, {"D011": None}) is False
    assert evaluate(node, {}) is False
    assert evaluate(parse("not exists(D011)"), {}) is True
    assert evaluate(parse("exists(D208) and D208 == 5"), {}) is False  # la guarda evita el UNKNOWN


# --- Comparaciones: números y strings ----------------------------------------------------------
def test_dsl_numeric_vs_string_comparison() -> None:
    gt9 = parse("D001 > 9")
    assert evaluate(gt9, {"D001": "10"}) is True  # numérico, no lexicográfico ("10" < "9")
    assert evaluate(gt9, {"D001": "9"}) is False
    assert evaluate(gt9, {"D001": "10"}, {"D001": "N"}) is True
    assert evaluate(parse("D001 == 5"), {"D001": "05"}) is True
    assert evaluate(parse("D001 == 5"), {"D001": "5.0"}) is True
    assert evaluate(parse("D001 == 1.5"), {"D001": "1.50"}) is True
    assert evaluate(parse("D001 >= 7000000"), {"D001": "7000000.0000"}) is True
    assert evaluate(parse("D001 < 0"), {"D001": "-3"}) is True
    # strings cuando no son números
    pyg = parse("D100 == 'PYG'")
    assert evaluate(pyg, {"D100": "PYG"}) is True
    assert evaluate(pyg, {"D100": "USD"}) is False
    assert evaluate(parse("D100 != 'PYG'"), {"D100": "USD"}) is True
    assert evaluate(parse("D100 == 'pyg'"), {"D100": "PYG"}) is False  # sin plegar mayúsculas
    assert evaluate(parse("D100 < 'B'"), {"D100": "A"}) is True
    assert evaluate(parse("D100 == D101"), {"D100": "PYG", "D101": "PYG"}) is True
    assert evaluate(parse("D100 == D101"), {"D100": "PYG", "D101": "USD"}) is False
    assert evaluate(parse("D100 == D101"), {"D100": "10", "D101": "10.0"}) is True
    # un número contra un texto que no lo es: se comparan como strings (== es False, != es True)
    assert evaluate(parse("D100 == 5"), {"D100": "abc"}) is False
    assert evaluate(parse("D100 != 5"), {"D100": "abc"}) is True
    # constante contra constante
    assert evaluate(parse("5 == 5"), {}) is True
    assert evaluate(parse("5 == 6"), {}) is False


def test_dsl_type_n_forces_numeric() -> None:
    node = parse("D001 >= 7000000")
    types = {"D001": "N"}
    assert evaluate(node, {"D001": "8000000"}, types) is True
    assert evaluate(node, {"D001": "abc"}, types) is None  # no numérico en un campo N: UNKNOWN
    assert evaluate(node, {"D001": ""}, types) is None
    # tipo no N: un valor no numérico se compara como string (aquí "abc" > "7000000" lexicográficamente)
    assert evaluate(node, {"D001": "abc"}, {"D001": "A"}) is True
    assert evaluate(parse("D001 == 7000000"), {"D001": "abc"}, {"D001": "A"}) is False
    assert evaluate(parse("D001 == 'x'"), {"D001": "x"}, types) is None  # constante no numérica
    # un tipo desconocido o ausente equivale a "no N"
    assert evaluate(node, {"D001": "8000000"}, {"D002": "N"}) is True
    assert evaluate(node, {"D001": "8000000"}, None) is True


def test_dsl_in_semantics() -> None:
    node = parse("C002 in (5, 6, 7)")
    assert evaluate(node, {"C002": "6"}) is True
    assert evaluate(node, {"C002": "8"}) is False
    assert evaluate(node, {"C002": None}) is None
    assert evaluate(node, {"C002": "06"}) is True
    assert evaluate(node, {"C002": "6"}, {"C002": "N"}) is True
    not_in = parse("C002 not in (5, 6, 7)")
    assert evaluate(not_in, {"C002": "6"}) is False
    assert evaluate(not_in, {"C002": "8"}) is True
    assert evaluate(not_in, {"C002": None}) is None
    assert evaluate(parse("D100 in ('PYG', 'USD')"), {"D100": "USD"}) is True
    assert evaluate(parse("D100 in ('PYG', 'USD')"), {"D100": "EUR"}) is False
    # UNKNOWN dentro de `in` (campo N no numérico): True si otra opción coincide no aplica; todo UNKNOWN
    assert evaluate(node, {"C002": "abc"}, {"C002": "N"}) is None
    # combinado: not in con guarda
    guarded = parse("exists(C002) and C002 not in (5, 6, 7)")
    assert evaluate(guarded, {}) is False
    assert evaluate(guarded, {"C002": "8"}) is True


def test_dsl_evaluate_rejects_foreign_nodes() -> None:
    with pytest.raises(TypeError):
        evaluate(FieldRef("D011"), {"D011": "1"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        unparse("D011 == 1")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        fields("D011 == 1")  # type: ignore[arg-type]


# --- Expresión real de D208c (§G.5, §K.6) ------------------------------------------------------
D208C_CASES = [
    # (descripción, valores del XML, resultado esperado: True = SIFEN devolvería 1321)
    ("innominado PYG en el umbral", {"D011": "1", "D208": "5", "F014": "7000000"}, True),
    ("innominado PYG sobre el umbral", {"D011": "1", "D208": "5", "F014": "12000000"}, True),
    ("innominado PYG bajo el umbral", {"D011": "1", "D208": "5", "F014": "6999999"}, False),
    ("D208 ausente (la guarda exists lo evita)", {"F014": "8000000"}, False),
    ("D208 ausente y D011 ausente", {"F014": "8000000"}, False),
    ("D208 distinto de 5", {"D011": "1", "D208": "1", "F014": "8000000"}, False),
    ("D011 = 13", {"D011": "13", "D208": "5", "F014": "8000000"}, False),
    ("D011 = 13 con F023", {"D011": "13", "D208": "5", "F023": "8000000"}, False),
    ("moneda extranjera sobre el umbral", {"D011": "1", "D208": "5", "F023": "8000000"}, True),
    ("moneda extranjera bajo el umbral", {"D011": "1", "D208": "5", "F023": "6999999"}, False),
    (
        "F014 >= 7M y F023 < 7M (según el paréntesis)",
        {"D011": "1", "D208": "5", "F014": "8000000", "F023": "100"},
        True,
    ),
    (
        "F023 >= 7M y F014 < 7M",
        {"D011": "1", "D208": "5", "F014": "100", "F023": "8000000"},
        True,
    ),
    ("F014 y F023 bajo el umbral", {"D011": "1", "D208": "5", "F014": "100", "F023": "100"}, False),
    ("D011 ausente con el resto violando", {"D208": "5", "F014": "7000000"}, True),
    ("D011 ausente y moneda extranjera", {"D208": "5", "F023": "9000000"}, True),
    ("ni F014 ni F023", {"D011": "1", "D208": "5"}, False),
    ("F014 con decimales de XML", {"D011": "1", "D208": "5", "F014": "7000000.0000"}, True),
    ("D208 con cero a la izquierda", {"D011": "1", "D208": "05", "F014": "7000000"}, True),
]


@pytest.mark.parametrize("typed", [False, True], ids=["sin_tipos", "con_tipos_N"])
@pytest.mark.parametrize(("name", "values", "expected"), D208C_CASES, ids=[c[0] for c in D208C_CASES])
def test_dsl_d208c(name: str, values: dict[str, str | None], expected: bool, typed: bool) -> None:
    node = parse(D208C)
    assert evaluate(node, values, D208C_TYPES if typed else None) is expected


def test_dsl_d208c_never_unknown_with_guards() -> None:
    """Con las guardas `exists()`, ninguna combinación de presencia da UNKNOWN."""
    node = parse(D208C)
    options = {
        "D011": (None, "1", "13"),
        "D208": (None, "1", "5"),
        "F014": (None, "100", "7000000"),
        "F023": (None, "100", "7000000"),
    }
    for combo in itertools.product(*options.values()):
        values = dict(zip(options, combo, strict=True))
        assert evaluate(node, values, D208C_TYPES) in (True, False), values


def test_dsl_d208c_constants_against_official_literals() -> None:
    node = parse(D208C)
    umbrales = {
        "MT v150": "60.000.000",
        "NT 21": "35.000.000",
        "NT 24": "7.000.000",
    }
    consts = constants(node)
    assert Decimal(7000000) in consts
    # solo la constante del umbral decide cuál texto oficial corresponde a la expresión
    for version, umbral in umbrales.items():
        literal = f"Si (D011≠13) y D208=5 y (F023 ≥ {umbral} o F014 ≥ {umbral}), rechazar"
        assert all(literal_contains_constant(literal, c) for c in consts) is (version == "NT 24")


# --- literal_contains_constant -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("literal", "const", "expected"),
    [
        # separadores de miles con punto, espacio o sin separador
        ("Monto mayor o igual a Gs. 7.000.000", Decimal(7000000), True),
        ("Monto mayor o igual a Gs.7.000.000.", Decimal(7000000), True),
        ("≥7.000.000", Decimal(7000000), True),
        ("7 000 000 guaraníes", Decimal(7000000), True),
        ("7\xa0000\xa0000", Decimal(7000000), True),
        ("7\N{NARROW NO-BREAK SPACE}000\N{NARROW NO-BREAK SPACE}000", Decimal(7000000), True),
        ("monto 7000000", Decimal(7000000), True),
        ("7.000.000,00", Decimal(7000000), True),
        ("35.000.000", Decimal(35000000), True),
        ("60.000.000", Decimal(60000000), True),
        # 70.000.000 NO es 7.000.000
        ("70.000.000", Decimal(7000000), False),
        ("170.000.000", Decimal(7000000), False),
        ("7.000.000", Decimal(70000000), False),
        ("7.000", Decimal(7000000), False),
        ("35.000.000", Decimal(7000000), False),
        ("60.000.000", Decimal(7000000), False),
        ("0.000.000", Decimal(7000000), False),
        ("Gs. 70.000.000 o Gs. 7.000.000", Decimal(7000000), True),
        ("monto 7000000A", Decimal(7000000), False),
        # decimales: coma o punto; un punto con 3 dígitos es de miles
        ("1,5 veces", Decimal("1.5"), True),
        ("1.5 veces", Decimal("1.5"), True),
        ("1,50", Decimal("1.5"), True),
        ("1.500", Decimal("1.5"), False),
        ("1.500", Decimal(1500), True),
        ("1.500,75", Decimal("1500.75"), True),
        ("15", Decimal("1.5"), False),
        # enteros pequeños y IDs: los dígitos de un ID no cuentan
        ("(D011≠13)", Decimal(13), True),
        ("(D011≠13)", Decimal(11), False),
        ("(D011≠13)", Decimal(1), False),
        ("D208c; D208=5", Decimal(208), False),
        ("D208c; D208=5", Decimal(5), True),
        ("D208=5 y F014≥7.000.000", Decimal(5), True),
        ("D208=5 y F014≥7.000.000", Decimal(14), False),
        # strings
        ("moneda PYG o USD", "PYG", True),
        ("moneda  PYG\n o USD", "PYG USD", False),
        ("moneda PYG\n o USD", "PYG o USD", True),
        ("moneda PYG", "EUR", False),
        ("moneda PYG", "pyg", False),
    ],
)
def test_literal_contains_constant(literal: str, const: Decimal | str, expected: bool) -> None:
    assert literal_contains_constant(literal, const) is expected
