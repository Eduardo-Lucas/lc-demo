import pytest

from lc_demo.tools import get_cnpj_status, is_valid_cnpj


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
def test_valid_cnpj(cnpj):
    assert is_valid_cnpj(cnpj)


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-82", "00.000.000/0000-00", "123"])
def test_invalid_cnpj(cnpj):
    assert not is_valid_cnpj(cnpj)


def test_tool_schema_comes_from_signature():
    assert get_cnpj_status.name == "get_cnpj_status"
    assert "cnpj" in get_cnpj_status.args


def test_tool_invoke():
    assert "ATIVA" in get_cnpj_status.invoke({"cnpj": "11.222.333/0001-81"})
