import httpx
import pytest

from lc_demo import tools
from lc_demo.tools import get_cnpj_status, is_valid_cnpj

# Trimmed from a real BrasilAPI response.
COMPANY = {
    "cnpj": "11222333000181",
    "razao_social": "CAIXA ESCOLAR DA ESCOLA ESTADUAL JOSEFINA JACQUES NORONHA",
    "nome_fantasia": "",
    "descricao_situacao_cadastral": "BAIXADA",
    "descricao_motivo_situacao_cadastral": "EXTINCAO POR ENCERRAMENTO LIQUIDACAO VOLUNTARIA",
    "data_situacao_cadastral": "2021-03-10",
    "descricao_identificador_matriz_filial": "MATRIZ",
    "data_inicio_atividade": "2009-09-02",
    "natureza_juridica": "Associação Privada",
    "porte": "DEMAIS",
    "cnae_fiscal": 8550301,
    "cnae_fiscal_descricao": "Administração de caixas escolares",
    "municipio": "SAO SEBASTIAO DO CAI",
    "uf": "RS",
    "opcao_pelo_simples": None,
    "opcao_pelo_mei": False,
    "qsa": [{"nome_socio": "FULANA DE TAL"}],
}


@pytest.fixture
def registry(monkeypatch):
    """Replace the HTTP call; set .status / .error to simulate the API's answers."""

    class Fake:
        def __init__(self):
            self.status, self.error, self.calls = 200, None, []

        def get(self, url, timeout):
            self.calls.append(url)
            if self.error:
                raise self.error
            return httpx.Response(self.status, json=COMPANY if self.status == 200 else {"message": "x"})

    fake = Fake()
    monkeypatch.setattr(tools.httpx, "get", fake.get)
    return fake


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
def test_valid_cnpj(cnpj):
    assert is_valid_cnpj(cnpj)


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-82", "00.000.000/0000-00", "123"])
def test_invalid_cnpj(cnpj):
    assert not is_valid_cnpj(cnpj)


def test_tool_schema_comes_from_signature():
    assert get_cnpj_status.name == "get_cnpj_status"
    assert "cnpj" in get_cnpj_status.args


def test_lookup_reports_the_registry_data(registry):
    result = get_cnpj_status.invoke({"cnpj": "11.222.333/0001-81"})
    assert registry.calls == ["https://brasilapi.com.br/api/cnpj/v1/11222333000181"]
    assert "Registration status: BAIXADA (reason: EXTINCAO POR ENCERRAMENTO" in result
    assert "since 2021-03-10" in result and "CNAE 8550301" in result and "SAO SEBASTIAO DO CAI/RS" in result
    assert "Simples Nacional: unknown" in result and "MEI: no" in result
    assert "FULANA" not in result  # partners are personal data and aren't passed on


def test_invalid_cnpj_is_not_looked_up(registry):
    assert "not a valid CNPJ" in get_cnpj_status.invoke({"cnpj": "11.222.333/0001-82"})
    assert registry.calls == []


def test_unknown_cnpj(registry):
    registry.status = 404
    assert "not in the Receita Federal registry" in get_cnpj_status.invoke({"cnpj": "11222333000181"})


@pytest.mark.parametrize(("status", "error"), [(503, None), (429, None), (200, httpx.ConnectTimeout("slow"))])
def test_lookup_failure_never_claims_a_status(registry, status, error):
    registry.status, registry.error = status, error
    result = get_cnpj_status.invoke({"cnpj": "11222333000181"})
    assert "status is unknown" in result and "ATIVA" not in result and "BAIXADA" not in result
