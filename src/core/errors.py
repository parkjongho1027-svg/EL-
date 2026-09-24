"""계산 경계에서 UI에 그대로 표시할 수 있는 입력 오류."""


class CalculationInputError(ValueError):
    """입력 형식, 물리적 범위 또는 단위가 유효하지 않음."""


class SimulationLimitError(CalculationInputError):
    """시뮬레이션 길이가 메모리/응답성 제한을 초과함."""
