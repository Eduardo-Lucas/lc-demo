"""Step 4: local tools. Docstrings + type hints become the schema the model sees."""

from langchain.tools import tool

_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _check_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    remainder = sum(d * w for d, w in zip(digits, weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(cnpj: str) -> bool:
    """Validate a CNPJ's check digits (format only, no registry lookup)."""
    digits = [int(c) for c in cnpj if c.isdigit()]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    first = _check_digit(digits[:12], _WEIGHTS)
    second = _check_digit([*digits[:12], first], (6, *_WEIGHTS))
    return digits[12:] == [first, second]


@tool
def get_cnpj_status(cnpj: str) -> str:
    """Check a Brazilian CNPJ: validates the check digits and returns its registration status."""
    if not is_valid_cnpj(cnpj):
        return f"{cnpj} is not a valid CNPJ (check digits do not match)."
    # Replace with a real registry/API call in production.
    return f"{cnpj} is valid. Registration status: ATIVA (mock)."
