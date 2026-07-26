"""
Referências geográficas oficiais compartilhadas pelo ETL.
Fonte: IBGE (malha municipal e estimativas populacionais).
"""

CAPITAIS = {
    "AC": "Rio Branco",     "AL": "Maceió",        "AM": "Manaus",
    "AP": "Macapá",         "BA": "Salvador",      "CE": "Fortaleza",
    "DF": "Brasília",       "ES": "Vitória",       "GO": "Goiânia",
    "MA": "São Luís",       "MG": "Belo Horizonte","MS": "Campo Grande",
    "MT": "Cuiabá",         "PA": "Belém",         "PB": "João Pessoa",
    "PE": "Recife",         "PI": "Teresina",      "PR": "Curitiba",
    "RJ": "Rio de Janeiro", "RN": "Natal",         "RO": "Porto Velho",
    "RR": "Boa Vista",      "RS": "Porto Alegre",  "SC": "Florianópolis",
    "SE": "Aracaju",        "SP": "São Paulo",     "TO": "Palmas",
}

# Municípios por UF (IBGE) — soma = 5570
MUN_TOTAL_UF = {
    "AC": 22,  "AL": 102, "AM": 62,  "AP": 16,  "BA": 417, "CE": 184,
    "DF": 1,   "ES": 78,  "GO": 246, "MA": 217, "MG": 853, "MS": 79,
    "MT": 141, "PA": 144, "PB": 223, "PE": 185, "PI": 224, "PR": 399,
    "RJ": 92,  "RN": 167, "RO": 52,  "RR": 15,  "RS": 497, "SC": 295,
    "SE": 75,  "SP": 645, "TO": 139,
}

NOME_UF = {
    "AC": "Acre",      "AL": "Alagoas",       "AM": "Amazonas",
    "AP": "Amapá",     "BA": "Bahia",         "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão",  "MG": "Minas Gerais",  "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará",        "PB": "Paraíba",
    "PE": "Pernambuco","PI": "Piauí",         "PR": "Paraná",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima",   "RS": "Rio Grande do Sul", "SC": "Santa Catarina",
    "SE": "Sergipe",   "SP": "São Paulo",     "TO": "Tocantins",
}

REGIAO_UF = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

# População residente estimada por UF — IBGE, estimativas 2024
POPULACAO_UF = {
    "AC": 880631,    "AL": 3220104,   "AM": 4281209,   "AP": 802837,
    "BA": 14850513,  "CE": 9233656,   "DF": 2982818,   "ES": 4102129,
    "GO": 7350483,   "MA": 6800605,   "MG": 21322691,  "MS": 2833742,
    "MT": 3836399,   "PA": 8664306,   "PB": 4030961,   "PE": 9539029,
    "PI": 3375646,   "PR": 11824665,  "RJ": 17219679,  "RN": 3446071,
    "RO": 1746227,   "RR": 716793,    "RS": 10882965,  "SC": 8058441,
    "SE": 2291077,   "SP": 45973194,  "TO": 1607363,
}


def normalizar_nome(nome):
    """Uppercase sem acentos — para casar nomes de município entre fontes."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(nome).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def slug_municipio(nome):
    """Nome de município → slug seguro para nome de arquivo/URL."""
    base = normalizar_nome(nome)
    return "".join(c if c.isalnum() else "_" for c in base).strip("_")
