"""Step 4: local tools. Docstrings + type hints become the schema the model sees."""

import httpx
from langchain.tools import tool

from lc_demo.config import CNPJ_API_URL

_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _check_digit(digits: list[int], weights: tuple[int, ...]) -> int:
    remainder = sum(d * w for d, w in zip(digits, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(cnpj: str) -> bool:
    """Validate a CNPJ's check digits (format only, no registry lookup)."""
    digits = [int(c) for c in cnpj if c.isdigit()]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    first = _check_digit(digits[:12], _WEIGHTS)
    second = _check_digit([*digits[:12], first], (6, *_WEIGHTS))
    return digits[12:] == [first, second]


def _yes_no(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def _summary(company: dict) -> str:
    """The registry fields a fiscal question needs; partners (QSA) are left out, they're personal data."""
    status = company.get("descricao_situacao_cadastral") or "unknown"
    reason = company.get("descricao_motivo_situacao_cadastral")
    if reason and reason != "SEM MOTIVO":
        status += f" (reason: {reason})"
    lines = [
        f"Legal name: {company.get('razao_social')}",
        f"Trade name: {company.get('nome_fantasia') or '-'}",
        f"Registration status: {status}, since {company.get('data_situacao_cadastral') or 'unknown'}",
        f"Establishment: {company.get('descricao_identificador_matriz_filial') or 'unknown'}",
        f"Opened: {company.get('data_inicio_atividade') or 'unknown'}",
        f"Legal nature: {company.get('natureza_juridica') or 'unknown'}",
        f"Size: {company.get('porte') or 'unknown'}",
        f"Main activity (CNAE {company.get('cnae_fiscal')}): {company.get('cnae_fiscal_descricao')}",
        f"Location: {company.get('municipio')}/{company.get('uf')}",
        f"Simples Nacional: {_yes_no(company.get('opcao_pelo_simples'))}",
        f"MEI: {_yes_no(company.get('opcao_pelo_mei'))}",
    ]
    return "\n".join(lines)


@tool
def get_cnpj_status(cnpj: str) -> str:
    """Check a Brazilian CNPJ: validates the check digits and looks it up in the Receita Federal registry
    (legal name, registration status, main activity, location, Simples/MEI)."""
    if not is_valid_cnpj(cnpj):
        return f"{cnpj} is not a valid CNPJ (check digits do not match)."
    digits = "".join(c for c in cnpj if c.isdigit())
    try:
        response = httpx.get(f"{CNPJ_API_URL}/{digits}", timeout=10)
    except httpx.HTTPError:
        response = None
    if response is not None and response.status_code == 404:
        return f"{cnpj} has valid check digits but is not in the Receita Federal registry."
    if response is None or response.status_code != 200:
        # Never let the model fill in a status it didn't get.
        return f"{cnpj} has valid check digits, but the registry lookup failed; its status is unknown. Try again later."
    return (
        f"CNPJ {cnpj}\n{_summary(response.json())}\n"
        "Source: Receita Federal public registry via BrasilAPI (may lag the Receita's own site by a few days)."
    )
