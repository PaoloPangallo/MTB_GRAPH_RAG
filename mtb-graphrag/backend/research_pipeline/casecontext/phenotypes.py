"""Literal phenotype typing, independent of gene and treatment identities.

MSI without a degree does not establish MSI-high.
Sources: https://www.cancer.gov/publications/dictionaries/cancer-terms/def/msi
https://www.cancer.gov/publications/dictionaries/cancer-terms/def/msi-h-cancer
"""
import re
import unicodedata


def _literal(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').casefold())
                   if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text))


_UNSPECIFIED_MSI = frozenset({
    'msi', 'microsatellite instability', 'microsatellite instability msi',
    'microsatelliti msi', 'instabilita dei microsatelliti',
    'instabilita dei microsatelliti msi',
})
_SPECIFIED_MSI = frozenset({'msi h', 'msi high', 'msi l', 'msi low', 'mss',
    'microsatellite instability high', 'microsatellite instability low', 'microsatellite stable'})


def is_unspecified_msi(value):
    return _literal(value) in _UNSPECIFIED_MSI


def is_molecular_phenotype(value):
    return _literal(value) in (_UNSPECIFIED_MSI | _SPECIFIED_MSI)


def microsatellite_value(value):
    literal = _literal(value)
    if literal in _UNSPECIFIED_MSI:
        return 'UNSPECIFIED'
    if literal in {'msi h', 'msi high', 'microsatellite instability high'}:
        return 'HIGH'
    if literal in {'msi l', 'msi low', 'microsatellite instability low'}:
        return 'LOW'
    if literal in {'mss', 'microsatellite stable'}:
        return 'STABLE'
    return None
