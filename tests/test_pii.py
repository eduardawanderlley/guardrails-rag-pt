import pytest

from guardrails_rag.guardrails.pii import PIIDetector, is_valid_cnpj, is_valid_cpf


@pytest.mark.parametrize(
    "value, expected",
    [
        ("111.444.777-35", True),
        ("11144477735", True),
        ("529.982.247-25", True),
        ("123.456.789-00", False),  # dígito verificador errado
        ("111.111.111-11", False),  # sequência repetida
        ("1234567890", False),  # tamanho errado
    ],
)
def test_cpf_check_digit(value, expected):
    assert is_valid_cpf(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("11.222.333/0001-81", True),
        ("11.444.777/0001-61", True),
        ("11.222.333/0001-82", False),
        ("00.000.000/0000-00", False),
    ],
)
def test_cnpj_check_digit(value, expected):
    assert is_valid_cnpj(value) is expected


def test_detects_brazilian_identifiers():
    text = "Meu CPF é 111.444.777-35 e o telefone é (11) 98765-4321."
    entities = {match.entity for match in PIIDetector().find(text)}
    assert entities == {"CPF", "TELEFONE"}


def test_ignores_numbers_that_fail_check_digit():
    text = "O protocolo 123.456.789-00 não é um CPF válido."
    assert PIIDetector().find(text) == []


def test_mask_replaces_values_with_entity_labels():
    masked, matches = PIIDetector().mask("Contato: maria.souza@exemplo.com.br, CNPJ 11.222.333/0001-81.")
    assert "maria.souza@exemplo.com.br" not in masked
    assert "11.222.333/0001-81" not in masked
    assert "[EMAIL]" in masked and "[CNPJ]" in masked
    assert len(matches) == 2


def test_rg_requires_label():
    detector = PIIDetector()
    assert [m.entity for m in detector.find("Documento: RG 12.345.678-9")] == ["RG"]
    assert detector.find("Código 12.345.678-9 do pedido") == []
