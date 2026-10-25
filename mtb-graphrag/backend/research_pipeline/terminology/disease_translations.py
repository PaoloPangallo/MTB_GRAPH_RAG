"""Small, explicit application translations; not additions to the pinned registry.

Targets preserve histology. Retrieval of an ontology ancestor is a separate rule,
never an alias or a claim of clinical equivalence. Unlisted words remain opaque.
"""
VERSION = 'disease-translations/1.2'
ALIASES = {
    'carcinoma squamoso del polmone': {'canonical': 'Lung Squamous Cell Carcinoma', 'source': 'https://media.aiom.it/userfiles/files/doc/LG/2016_LG_AIOM_Polmone.pdf'},
    'adenocarcinoma polmonare': {'canonical': 'Lung Adenocarcinoma', 'source': 'https://www.aiom.it/genomic-profiling-of-lung-adenocarcinoma-in-never-smokers/'},
    'carcinoma polmonare': {'canonical': 'Lung Carcinoma', 'source': 'https://media.aiom.it/userfiles/files/doc/LG/2016_LG_AIOM_Polmone.pdf'},
    'carcinoma colorettale': {'canonical': 'Colorectal Carcinoma', 'source': 'https://www.epicentro.iss.it/ben/2025/2/screening-carcinoma-colon-retto-umbria'},
    'carcinoma del colon-retto': {'canonical': 'Colorectal Carcinoma', 'source': 'https://www.epicentro.iss.it/ben/2025/2/screening-carcinoma-colon-retto-umbria'},
    'carcinoma mammario': {'canonical': 'Breast Carcinoma', 'source': 'https://pubmed.ncbi.nlm.nih.gov/2057605/'},
    'carcinoma ovarico': {'canonical': 'Ovarian Carcinoma', 'source': 'https://pubmed.ncbi.nlm.nih.gov/3505909/'},
    'carcinoma tiroideo': {'canonical': 'Thyroid Carcinoma', 'source': 'https://www.aiom.it/linee-guida-aiom-2021-tumori-della-tiroide/'},
    'colangiocarcinoma': {'canonical': 'Cholangiocarcinoma', 'source': 'https://www.aiom.it/wp-content/uploads/2019/10/2019_LG_AIOM_Vie_biliari.pdf'},
    'tumore stromale gastrointestinale': {'canonical': 'Gastrointestinal Stromal Tumor', 'source': 'https://www.aiom.it/eventi-aiom/nuove-frontiere-nel-trattamento-del-gist/'},
    'leucemia mieloide cronica': {'canonical': 'Chronic Myeloid Leukemia', 'source': 'https://www.issalute.it/index.php/la-salute-dalla-a-alla-z-menu/l/leucemia-mieloide-cronica-lmc'},
}
CONTEXT_PHRASES = {
    'non resecabile': 'unresectable',
    'non resecabili': 'unresectable',
}
CONTEXT_WORDS = {
    'metastatico': 'metastatic', 'metastatica': 'metastatic',
    'recidivato': 'recurrent', 'recidivata': 'recurrent', 'recidivante': 'recurrent',
    'avanzato': 'advanced', 'avanzata': 'advanced', 'localmente': 'locally',
    'resecato': 'resected', 'resecata': 'resected', 'stadio': 'stage',
}
KNOWN_CONTEXT_WORDS = frozenset({
    'metastatic', 'recurrent', 'advanced', 'locally', 'resected', 'unresectable',
    'stage', 'i', 'ii', 'iii', 'iv', '1', '2', '3', '4',
})
