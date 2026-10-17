"""DSL de condiciones de las reglas de validación: parser con lista blanca y evaluador trivalente.

Referencia de diseño: docs/arquitectura.md §C.1 ("Condición como texto"), §F.1 (`Formalization`),
§G.5 (expresión real de D208c) y §K.1 (`test_dsl_whitelist`, `test_dsl_kleene`).

POLARIDAD (FIJA, la misma de `model.Formalization`): una condición evaluada a ``True`` significa
que la validación se VIOLA, es decir, SIFEN devolvería el código de rechazo. ``False`` = la
validación se cumple; ``None`` = no se puede decidir con los datos disponibles (UNKNOWN).

Sintaxis: subconjunto de expresiones Python, analizado con ``ast.parse`` (solo análisis sintáctico:
el texto del usuario NUNCA se evalúa, ni se ejecuta ni se compila) y traducido a un IR propio con
una lista blanca estricta:

- ``and``, ``or``, ``not`` y paréntesis libres (en minúsculas; ``AND`` se rechaza).
- Comparaciones BINARIAS ``==  !=  <  <=  >  >=`` (las encadenadas ``a < b < c`` se rechazan).
- ``X in (c1, c2, ...)`` y ``X not in (...)`` contra una tupla de constantes.
- Operandos: IDs de campo SIFEN (patrón de ``SifenId``: ``D011``, ``F014``, ``D208c``...), enteros,
  decimales con punto (``1.5``) y strings.
- ``exists(ID)``: el campo está presente en el XML (nunca es UNKNOWN).

Todo lo demás se rechaza con ``DslError`` (atributos, subíndices, otras llamadas, lambdas,
comprensiones, ``True``/``False``/``None``, aritmética, f-strings, walrus, nombres que no son IDs).

Semántica de ``evaluate`` (lógica trivalente de Kleene; el resultado no depende del orden de los
operandos):

- Comparar contra un campo ausente (``None``) da UNKNOWN; por eso las lecturas se protegen con
  ``exists()``: ``exists(D208) and D208 == 5`` es ``False`` si D208 falta.
- ``and``: False si algún operando es False; si no, None si alguno es None; si no, True.
- ``or``: True si algún operando es True; si no, None si alguno es None; si no, False.
- ``not None`` = None.

El IR (dataclasses inmutables) se deriva siempre del texto: nunca se edita a mano ni se versiona.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, NoReturn

__all__ = [
    "MAX_EXPR_LEN",
    "SIFEN_ID_RE",
    "And",
    "Cmp",
    "Cond",
    "Const",
    "DslError",
    "Exists",
    "FieldRef",
    "In",
    "Node",
    "Not",
    "Operand",
    "Or",
    "constants",
    "evaluate",
    "fields",
    "literal_contains_constant",
    "parse",
    "unparse",
]

SIFEN_ID_RE = re.compile(r"^[A-Z][A-Za-z]{0,6}\d{1,3}[a-z]?$")
"""Mismo patrón que `model.SifenId` (un test verifica que coinciden)."""

MAX_EXPR_LEN = 10_000
"""Tope de longitud de una expresión (defensa ante entradas patológicas)."""

CmpOp = Literal["==", "!=", "<", "<=", ">", ">="]


class DslError(ValueError):
    """Expresión fuera del DSL: sintaxis inválida o construcción no permitida."""

    def __init__(self, message: str, col: int | None = None) -> None:
        super().__init__(message if col is None else f"{message} (columna {col})")
        self.message = message
        self.col = col


# --- IR inmutable ----------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FieldRef:
    """Valor de un campo SIFEN, identificado por su ID (`D011`)."""

    name: str


@dataclass(frozen=True, slots=True)
class Const:
    """Constante: número (Decimal, sin pérdida de precisión) o string."""

    value: Decimal | str


@dataclass(frozen=True, slots=True)
class Exists:
    """`exists(ID)`: el campo está presente. Siempre True/False, nunca UNKNOWN."""

    field: FieldRef


@dataclass(frozen=True, slots=True)
class Cmp:
    """Comparación binaria entre campos y/o constantes."""

    op: CmpOp
    left: Operand
    right: Operand


@dataclass(frozen=True, slots=True)
class In:
    """`X in (c1, ...)` (o `not in` si `negated`): pertenencia a una tupla de constantes."""

    field: FieldRef
    values: tuple[Const, ...]
    negated: bool = False


@dataclass(frozen=True, slots=True)
class And:
    """Conjunción n-aria (los `and` anidados se aplanan al analizar; es asociativa)."""

    operands: tuple[Cond, ...]


@dataclass(frozen=True, slots=True)
class Or:
    """Disyunción n-aria (los `or` anidados se aplanan al analizar; es asociativa)."""

    operands: tuple[Cond, ...]


@dataclass(frozen=True, slots=True)
class Not:
    """Negación (`not None` = None)."""

    operand: Cond


Operand = FieldRef | Const
"""Lo que puede compararse: un campo o una constante."""

Cond = And | Or | Not | Cmp | In | Exists
"""Nodos que representan una condición (lo que devuelve `parse`)."""

Node = Cond | Operand
"""Cualquier nodo del IR."""


# --- Análisis sintáctico (ast → IR) ----------------------------------------------------------
_STRING_RE = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")
_UPPER_OP_RE = re.compile(r"\b(?:and|or|not)\b", re.IGNORECASE)
_NUM_LITERAL_RE = re.compile(r"\d+(?:\.\d+)?")
_CMP_SYMBOLS: dict[type[ast.cmpop], CmpOp] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}
_ID_HINT = "p. ej. D011, F014, D208c"


def _blank_strings(src: str) -> str:
    """Reemplaza los literales de texto por espacios (para buscar operadores fuera de ellos)."""
    return _STRING_RE.sub(lambda m: " " * len(m.group()), src)


def _check_keyword_case(src: str) -> None:
    for m in _UPPER_OP_RE.finditer(_blank_strings(src)):
        word = m.group()
        if word != word.lower():
            raise DslError(
                f"`{word}` no es un operador del DSL: use `{word.lower()}` en minúsculas "
                "(`and`, `or`, `not`)",
                col=m.start() + 1,
            )


def _syntax_hint(src: str) -> str:
    plain = _blank_strings(src)
    if "&&" in plain or "||" in plain:
        return ": use `and` / `or` en lugar de `&&` / `||`"
    if re.search(r"!(?!=)", plain):
        return ": use `not` en lugar de `!`"
    if re.search(r"(?<![=!<>])=(?!=)", plain):
        return ": use `==` para comparar (`=` es una asignación)"
    return ""


class _Builder:
    """Traduce el `ast` de Python al IR aplicando la lista blanca; todo lo demás es `DslError`."""

    def __init__(self, src: str, known_fields: frozenset[str] | None) -> None:
        self.src = src
        self.known = known_fields

    # -- errores --
    def err(self, node: ast.AST, message: str) -> DslError:
        off = getattr(node, "col_offset", None)
        col = None if off is None else len(self.src.encode()[:off].decode(errors="ignore")) + 1
        return DslError(message, col=col)

    def unsupported(self, node: ast.AST) -> NoReturn:
        """Rechazo con un mensaje específico según el tipo de construcción."""
        match node:
            case ast.Attribute():
                msg = "no se permiten atributos (`a.b`): solo IDs de campo, constantes y `exists(ID)`"
            case ast.Subscript():
                msg = "no se permiten subíndices (`a[0]`)"
            case ast.Call():
                raise self.call_error(node)
            case ast.Lambda():
                msg = "no se permiten lambdas"
            case ast.ListComp() | ast.SetComp() | ast.DictComp() | ast.GeneratorExp():
                msg = "no se permiten comprensiones ni generadores"
            case ast.NamedExpr():
                msg = "no se permite el operador `:=` (walrus)"
            case ast.JoinedStr() | ast.FormattedValue():
                msg = "no se permiten f-strings"
            case ast.BinOp():
                msg = "no se permiten operadores aritméticos ni de bits (`+`, `-`, `*`, `/`, `%`, ...)"
            case ast.UnaryOp():
                msg = (
                    "no se permiten operadores unarios aritméticos (`-`, `+`, `~`); tampoco números negativos"
                )
            case ast.IfExp():
                msg = "no se permiten expresiones condicionales (`a if c else b`)"
            case ast.List() | ast.Set() | ast.Dict():
                msg = "no se permiten listas, conjuntos ni diccionarios; use una tupla solo con `in`"
            case ast.Tuple():
                msg = "las tuplas solo se permiten a la derecha de `in` / `not in`"
            case _:
                msg = f"construcción no permitida en el DSL ({type(node).__name__})"
        raise self.err(node, msg)

    def call_error(self, node: ast.Call) -> DslError:
        func = node.func
        if isinstance(func, ast.Name):
            return self.err(
                node, f"llamada a `{func.id}` no permitida: la única función admitida es `exists(ID)`"
            )
        if isinstance(func, ast.Attribute):
            return self.err(node, "no se permiten atributos ni llamadas a métodos (`a.b()`)")
        return self.err(node, "llamada no permitida: la única función admitida es `exists(ID)`")

    # -- condiciones --
    def cond(self, node: ast.AST) -> Cond:
        match node:
            case ast.BoolOp(op=op, values=values):
                cls = And if isinstance(op, ast.And) else Or
                flat: list[Cond] = []
                for value in values:
                    child = self.cond(value)
                    if type(child) is cls:  # asociatividad: a and (b and c) == a and b and c
                        flat.extend(child.operands)  # type: ignore[union-attr]
                    else:
                        flat.append(child)
                return cls(tuple(flat))
            case ast.UnaryOp(op=ast.Not(), operand=inner):
                return Not(self.cond(inner))
            case ast.Compare():
                return self.compare(node)
            case ast.Call():
                return self.exists(node)
            case ast.Name(id=name):
                if SIFEN_ID_RE.fullmatch(name):
                    raise self.err(
                        node,
                        f"el campo `{name}` no puede usarse solo como condición: "
                        f"use una comparación o `exists({name})`",
                    )
                raise self.err(node, self.not_an_id(name))
            case ast.Constant(value=value):
                if value is None or isinstance(value, bool):
                    raise self.err(node, self.bool_none_message())
                raise self.err(node, "una constante sola no es una condición: compárela con un campo")
            case _:
                self.unsupported(node)

    def compare(self, node: ast.Compare) -> Cmp | In:
        if len(node.ops) != 1:
            raise self.err(
                node,
                "no se permiten comparaciones encadenadas (`a < b < c`): use `and` (`a < b and b < c`)",
            )
        op = node.ops[0]
        right = node.comparators[0]
        if isinstance(op, ast.In | ast.NotIn):
            return self.membership(node.left, right, negated=isinstance(op, ast.NotIn))
        if isinstance(op, ast.Is | ast.IsNot):
            raise self.err(node, "no se permiten `is` / `is not`: use `==` / `!=`")
        return Cmp(_CMP_SYMBOLS[type(op)], self.operand(node.left), self.operand(right))

    def membership(self, left_node: ast.AST, right: ast.AST, *, negated: bool) -> In:
        left = self.operand(left_node)
        if not isinstance(left, FieldRef):
            raise self.err(left_node, "el lado izquierdo de `in` / `not in` debe ser un ID de campo")
        hint = "`in` / `not in` exigen una tupla de constantes, p. ej. `C002 in (5, 6, 7)`"
        if isinstance(right, ast.List | ast.Set):
            raise self.err(right, f"{hint}; no se admiten listas ni conjuntos")
        if not isinstance(right, ast.Tuple):
            raise self.err(right, hint)
        if not right.elts:
            raise self.err(right, "la tupla de `in` / `not in` no puede estar vacía")
        values: list[Const] = []
        for elt in right.elts:
            if not isinstance(elt, ast.Constant):
                raise self.err(elt, "la tupla de `in` / `not in` solo admite constantes (números o strings)")
            values.append(self.const(elt))
        return In(left, tuple(values), negated)

    def exists(self, node: ast.Call) -> Exists:
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "exists"):
            raise self.call_error(node)
        if node.keywords:
            raise self.err(node, "`exists()` no admite argumentos con nombre")
        if len(node.args) != 1:
            raise self.err(node, "`exists()` recibe exactamente un argumento: un ID de campo")
        arg = node.args[0]
        if not isinstance(arg, ast.Name):
            raise self.err(arg, f"`exists()` exige un ID de campo como argumento ({_ID_HINT})")
        return Exists(self.field(arg))

    # -- operandos --
    def operand(self, node: ast.AST) -> Operand:
        match node:
            case ast.Name():
                return self.field(node)
            case ast.Constant():
                return self.const(node)
            case ast.Call(func=ast.Name(id="exists")):
                raise self.err(node, "`exists(...)` es una condición, no un valor: no puede compararse")
            case ast.BoolOp() | ast.Compare() | ast.UnaryOp(op=ast.Not()):
                raise self.err(
                    node, "los operandos de una comparación deben ser un ID de campo o una constante"
                )
            case _:
                self.unsupported(node)

    def not_an_id(self, name: str) -> str:
        return (
            f"`{name}` no es un ID de campo SIFEN ({_ID_HINT}): solo se admiten IDs de campo, "
            "constantes y `exists(ID)`"
        )

    def field(self, node: ast.Name) -> FieldRef:
        name = node.id
        if not SIFEN_ID_RE.fullmatch(name):
            raise self.err(node, self.not_an_id(name))
        if self.known is not None and name not in self.known:
            raise self.err(node, f"el campo `{name}` no está entre los campos conocidos")
        return FieldRef(name)

    def bool_none_message(self) -> str:
        return (
            "no se permiten `True`, `False` ni `None`: use `exists(ID)` para la presencia "
            "y comparaciones para los valores"
        )

    def const(self, node: ast.Constant) -> Const:
        value = node.value
        if value is None or isinstance(value, bool):
            raise self.err(node, self.bool_none_message())
        if isinstance(value, str):
            return Const(value)
        if isinstance(value, complex):
            raise self.err(node, "no se permiten números complejos")
        if isinstance(value, int | float):
            segment = ast.get_source_segment(self.src, node)
            if segment is None or not _NUM_LITERAL_RE.fullmatch(segment):
                raise self.err(
                    node,
                    "forma numérica no admitida: use enteros o decimales con punto, sin separadores "
                    "de miles ni notación científica (p. ej. 7000000 o 1.5)",
                )
            return Const(Decimal(segment))
        raise self.err(
            node, f"constante de tipo `{type(value).__name__}` no permitida (solo números y strings)"
        )


def parse(expr: str, known_fields: Collection[str] | None = None) -> Cond:
    """Analiza `expr` y devuelve el IR inmutable; `DslError` si algo está fuera de la lista blanca.

    Polaridad: la condición describe cuándo la validación se VIOLA (True ⇒ SIFEN devolvería el código).
    Los saltos de línea se tratan como espacios (las condiciones largas se escriben en varias líneas).
    Si se pasa `known_fields`, un ID fuera del conjunto es un error.
    """
    src = expr.replace("\r", " ").replace("\n", " ").strip()
    if not src:
        raise DslError("la expresión está vacía")
    if len(src) > MAX_EXPR_LEN:
        raise DslError(f"la expresión es demasiado larga (máximo {MAX_EXPR_LEN} caracteres)")
    _check_keyword_case(src)
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as exc:  # incluye IndentationError y TabError
        raise DslError(f"sintaxis inválida{_syntax_hint(src)}", col=exc.offset or None) from None
    except ValueError, MemoryError, RecursionError:  # bytes nulos, enteros enormes, anidación
        raise DslError(
            "expresión no analizable (bytes nulos, números enormes o anidación excesiva)"
        ) from None
    known = None if known_fields is None else frozenset(known_fields)
    try:
        return _Builder(src, known).cond(tree.body)
    except RecursionError:
        raise DslError("la expresión está demasiado anidada") from None


# --- Recorridos ------------------------------------------------------------------------------
def _walk(node: Node) -> Iterator[Node]:
    """Recorre el IR en orden de aparición (de izquierda a derecha)."""
    yield node
    match node:
        case And(operands=ops) | Or(operands=ops):
            for op in ops:
                yield from _walk(op)
        case Not(operand=inner):
            yield from _walk(inner)
        case Cmp(left=left, right=right):
            yield from _walk(left)
            yield from _walk(right)
        case In(field=field, values=values):
            yield from _walk(field)
            for value in values:
                yield from _walk(value)
        case Exists(field=field):
            yield from _walk(field)
        case FieldRef() | Const():
            pass
        case _:
            raise TypeError(f"nodo del DSL no soportado: {node!r}")


def fields(node: Node) -> set[str]:
    """IDs de campo que la condición lee (en comparaciones, `in` o `exists()`)."""
    return {n.name for n in _walk(node) if isinstance(n, FieldRef)}


def constants(node: Node) -> list[Decimal | str]:
    """Constantes de la condición, sin repetidos y en orden de aparición.

    Un test exige que cada una aparezca en el literal oficial (`literal_contains_constant`).
    """
    seen: list[Decimal | str] = []
    for n in _walk(node):
        if isinstance(n, Const) and n.value not in seen:
            seen.append(n.value)
    return seen


# --- Texto canónico --------------------------------------------------------------------------
def _const_text(const: Const) -> str:
    return repr(const.value) if isinstance(const.value, str) else format(const.value, "f")


def _operand_text(operand: Operand) -> str:
    return operand.name if isinstance(operand, FieldRef) else _const_text(operand)


def _wrap(child: Cond, *, bare: tuple[type, ...]) -> str:
    text = unparse(child)
    return text if isinstance(child, bare) else f"({text})"


def unparse(node: Node) -> str:
    """Texto canónico del IR: `parse(unparse(parse(x))) == parse(x)` y es idempotente.

    Siempre parentesiza `and` dentro de `or` y la comparación dentro de `not`, para que se lea
    sin conocer la precedencia.
    """
    match node:
        case FieldRef() | Const():
            return _operand_text(node)
        case Exists(field=field):
            return f"exists({field.name})"
        case Cmp(op=op, left=left, right=right):
            return f"{_operand_text(left)} {op} {_operand_text(right)}"
        case In(field=field, values=values, negated=negated):
            items = ", ".join(_const_text(v) for v in values)
            if len(values) == 1:
                items += ","
            return f"{field.name} {'not in' if negated else 'in'} ({items})"
        case Not(operand=inner):
            return f"not {_wrap(inner, bare=(Not, Exists))}"
        case And(operands=ops):
            return " and ".join(_wrap(op, bare=(Not, Cmp, In, Exists)) for op in ops)
        case Or(operands=ops):
            return " or ".join(_wrap(op, bare=(Not, Cmp, In, Exists)) for op in ops)
        case _:
            raise TypeError(f"nodo del DSL no soportado: {node!r}")


# --- Literal oficial vs constantes -----------------------------------------------------------
def _number_re(separators: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z\d])(?<!\d[.,])"  # no pegado a un ID (D011) ni a mitad de otro número
        rf"(?P<int>\d{{1,3}}(?:{separators}\d{{3}})+(?!\d)|\d+)"  # entero con miles agrupados
        r"(?:[,.](?P<dec>\d+))?"  # decimales (coma en es-PY; punto si no es de miles)
        r"(?![A-Za-z\d])"
    )


_SEPARATORS = r"[. \xa0\N{NARROW NO-BREAK SPACE}]"  # punto, espacio, espacio duro y espacio fino
_NUMBER_REGEXES = (_number_re(r"\."), _number_re(_SEPARATORS))
_THOUSANDS_RE = re.compile(_SEPARATORS)


def _numbers_in(text: str) -> set[Decimal]:
    """Números del texto con la convención es-PY: `.`/espacio = miles, `,` = decimal.

    Un punto seguido de un número de dígitos distinto de 3 se lee como decimal (`1.5`), así que
    `7.000.000`, `7 000 000` y `7000000` son el mismo número y `70.000.000` es otro.
    """
    found: set[Decimal] = set()
    for regex in _NUMBER_REGEXES:
        for m in regex.finditer(text):
            digits = _THOUSANDS_RE.sub("", m.group("int"))
            dec = m.group("dec")
            found.add(Decimal(f"{digits}.{dec}" if dec else digits))
    return found


def literal_contains_constant(literal: str, const: Decimal | str) -> bool:
    """¿La constante del DSL aparece en el literal oficial de la NT?

    Números: se comparan por valor ignorando separadores de miles (`.` y espacios): 7000000 ↔
    "7.000.000"; decimales con coma ↔ punto (1.5 ↔ "1,5"). Los dígitos de un ID (D011) no cuentan.
    Strings: subcadena exacta tras colapsar espacios.
    """
    if isinstance(const, Decimal):
        return const in _numbers_in(literal)
    return " ".join(const.split()) in " ".join(literal.split())


# --- Evaluación trivalente (Kleene) ----------------------------------------------------------
_OPS: dict[str, Callable[[object, object], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_NUMERIC_TEXT_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def _kleene_and(results: Iterable[bool | None]) -> bool | None:
    items = list(results)
    if any(r is False for r in items):
        return False
    if any(r is None for r in items):
        return None
    return True


def _kleene_or(results: Iterable[bool | None]) -> bool | None:
    items = list(results)
    if any(r is True for r in items):
        return True
    if any(r is None for r in items):
        return None
    return False


def _kleene_not(result: bool | None) -> bool | None:
    return None if result is None else not result


def _as_number(value: Decimal | str) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = value.strip()
    return Decimal(text) if _NUMERIC_TEXT_RE.fullmatch(text) else None


def _as_text(value: Decimal | str) -> str:
    return format(value, "f") if isinstance(value, Decimal) else value


def _resolve(
    operand: Operand, values: Mapping[str, str | None], types: Mapping[str, str]
) -> tuple[Decimal | str | None, bool]:
    """Valor del operando (None si el campo falta) y si su tipo declarado fuerza comparación numérica."""
    if isinstance(operand, Const):
        return operand.value, False
    raw = values.get(operand.name)
    return (None if raw is None else str(raw)), types.get(operand.name) == "N"


def _compare(
    op: str,
    left: Operand,
    right: Operand,
    values: Mapping[str, str | None],
    types: Mapping[str, str],
) -> bool | None:
    lv, ln = _resolve(left, values, types)
    rv, rn = _resolve(right, values, types)
    if lv is None or rv is None:
        return None  # un campo ausente deja la comparación sin decidir
    a, b = _as_number(lv), _as_number(rv)
    if ln or rn:  # tipo "N": solo tiene sentido numéricamente
        return None if a is None or b is None else _OPS[op](a, b)
    if a is not None and b is not None:  # ambos lados parecen números
        return _OPS[op](a, b)
    return _OPS[op](_as_text(lv), _as_text(rv))


def _evaluate(node: Cond, values: Mapping[str, str | None], types: Mapping[str, str]) -> bool | None:
    match node:
        case And(operands=ops):
            return _kleene_and(_evaluate(op, values, types) for op in ops)
        case Or(operands=ops):
            return _kleene_or(_evaluate(op, values, types) for op in ops)
        case Not(operand=inner):
            return _kleene_not(_evaluate(inner, values, types))
        case Exists(field=field):
            return values.get(field.name) is not None
        case Cmp(op=op, left=left, right=right):
            return _compare(op, left, right, values, types)
        case In(field=field, values=options, negated=negated):
            found = _kleene_or(_compare("==", field, option, values, types) for option in options)
            return _kleene_not(found) if negated else found
        case _:
            raise TypeError(f"nodo del DSL no evaluable: {node!r}")


def evaluate(
    node: Cond,
    values: Mapping[str, str | None],
    types: Mapping[str, str] | None = None,
) -> bool | None:
    """Evalúa la condición con lógica trivalente de Kleene.

    Polaridad: True ⇒ la validación se VIOLA (SIFEN devolvería el código); False ⇒ se cumple;
    None ⇒ UNKNOWN (falta un dato que la decide).

    - `values`: ID → texto del XML; `None` (o ausencia de la clave) = el elemento no existe. Una
      cadena, incluso vacía, cuenta como presente para `exists()`.
    - `types`: ID → tipo SIFEN. "N" compara como `Decimal` (un valor no numérico es UNKNOWN). Con
      otro tipo o sin tipo, si ambos lados parecen números se comparan como números y si no, como
      strings.
    - Comparar con un campo ausente da None; `exists()` nunca da None.
    - `and`/`or`/`not` siguen las tablas de Kleene y no dependen del orden de los operandos.
    """
    return _evaluate(node, values, types or {})
