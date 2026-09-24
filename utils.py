"""입력식 파싱과 공통 수치 검증. Tkinter 독립."""
import ast
import math
from typing import Any, Callable, NamedTuple


class CalculationOutcome(NamedTuple):
    value: Any
    error: str | None
    unexpected: Exception | None = None


def _finite_numbers(value):
    """결과가 중첩된 dict/list여도 숫자 결과에 NaN·무한대가 없게 한다."""
    if isinstance(value, dict):
        return all(_finite_numbers(part) for part in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_numbers(part) for part in value)
    return not isinstance(value, (int, float)) or math.isfinite(value)


def calculate_safely(function: Callable, *args, **kwargs) -> CalculationOutcome:
    """순수 계산식의 예상 입력 오류와 내부 오류를 구분해 반환한다."""
    try:
        result = function(*args, **kwargs)
        if not _finite_numbers(result):
            raise ValueError("계산 결과가 유한한 숫자가 아닙니다. 입력값을 확인하세요.")
        return CalculationOutcome(result, None)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as error:
        return CalculationOutcome(None, f"입력값 오류: {error}")
    except Exception as error:
        return CalculationOutcome(None, "계산 중 내부 오류가 발생했습니다.", error)


def require_calculation(outcome: CalculationOutcome):
    """기존 Tkinter 화면의 오류 표시·로그 흐름에 결과를 연결한다."""
    if outcome.unexpected is not None:
        raise outcome.unexpected
    if outcome.error is not None:
        raise ValueError(outcome.error)
    return outcome.value

def clean_number_text(value):
    """기록 속 숫자를 읽기 좋은 한 가지 형식으로 통일합니다."""
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return text
    if not math.isfinite(number):
        return text
    return f"{number:.15g}"

def _evaluate_numeric_expression(node):
    """숫자 입력칸에서 허용한 사칙연산 AST만 안전하게 계산합니다."""
    if isinstance(node, ast.Expression):
        return _evaluate_numeric_expression(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_numeric_expression(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate_numeric_expression(node.left)
        right = _evaluate_numeric_expression(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            if abs(right) > 20:
                raise ValueError("지수의 절댓값은 20 이하만 사용할 수 있습니다.")
            return left ** right
    raise ValueError("숫자와 +, -, *, /, 괄호, 제곱(^)만 사용할 수 있습니다.")

def parse_number(raw, label):
    """숫자 또는 간단한 계산식을 안전하게 실수로 바꾸는 공통 함수.

    예: 2,400 / 50*1.1*6 / (1500+330)/2 / 3^2 를 입력할 수 있습니다.
    """
    if raw is None or isinstance(raw, bool):
        raise ValueError(f"'{label}'에 올바른 숫자를 입력해주세요.")
    text = str(raw).strip().replace(",", "").replace("×", "*").replace("÷", "/")
    text = text.replace("^", "**")
    if text == "":
        raise ValueError(f"'{label}' 값을 입력해주세요.")
    if len(text) > 200:
        raise ValueError(f"'{label}'의 입력식이 너무 깁니다.")
    try:
        tree = ast.parse(text, mode="eval")
        value = float(_evaluate_numeric_expression(tree))
    except ZeroDivisionError:
        raise ValueError(f"'{label}'의 계산식에서 0으로 나눌 수 없습니다.")
    except (SyntaxError, TypeError, OverflowError, ValueError) as error:
        if isinstance(error, ValueError) and str(error):
            raise ValueError(f"'{label}': {error}")
        raise ValueError(f"'{label}'에 올바른 숫자 또는 계산식을 입력해주세요.")
    if not math.isfinite(value):
        raise ValueError(f"'{label}'에는 유한한 숫자만 입력해주세요.")
    return value

def ensure_positive(value, label, allow_zero=False):
    """중량·시간·거리처럼 음수가 될 수 없는 입력값을 검사합니다."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"'{label}'은(는) 숫자여야 합니다.") from None
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError(f"'{label}'은(는) 유한한 숫자여야 합니다.")
    if number < 0 or (number == 0 and not allow_zero):
        condition = "0 이상" if allow_zero else "0보다 큰"
        raise ValueError(f"'{label}'은(는) {condition} 값이어야 합니다.")
