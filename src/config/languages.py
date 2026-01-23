# Language mapping configuration
# Maps internal language codes to DeepL API codes
#
# Format: "internal_code": "deepl_code"
# Add new languages here as needed

LANGUAGE_MAP = {
    # Español
    "es": "ES",

    # Inglés
    "en": "EN-US",

    # Italiano
    "it": "IT",

    # Francés
    "fr": "FR",

    # Alemán
    "de": "DE",

    # Portugués (europeo)
    "pt": "PT-PT",

    # Brasileño (portugués brasileño)
    "pt_BR": "PT-BR",

    # Ruso
    "ru": "RU",

    # Holandés / Dutch
    "nl": "NL",

    # Chino Mandarín Simplificado
    "zh": "ZH-HANS",

    # Japonés
    "jp": "JA",

    # Polaco
    "pl": "PL",

    # Griego
    "gr": "EL",

    # Rumano
    "ro": "RO",

    # Catalán - NO SOPORTADO por DeepL, usar español como fallback
    "ca_ES": "ES",

    # Euskera - NO SOPORTADO por DeepL, usar español como fallback
    "eu": "ES",

    # Mexicano (español mexicano) - DeepL no distingue, usar español
    "mx": "ES",

    # Húngaro
    "hu": "HU",

    # Croata - NO SOPORTADO directamente, pero DeepL lo acepta como HR (experimental)
    "hr": "HR",

    # Serbio - NO SOPORTADO por DeepL
    "sr": "SR",

    # Bosnio - NO SOPORTADO por DeepL
    "bs": "BS",

    # Búlgaro
    "bg": "BG",

    # Montenegrino - NO SOPORTADO, muy similar a serbio
    "cnr": "SR",

    # Flamenco (holandés belga) - usar holandés
    "nl_be": "NL",

    # Turco
    "tr": "TR",

    # Eslovaco
    "sk": "SK",

    # Hindi - NO SOPORTADO por DeepL
    "hi": "HI",

    # Noruego
    "no": "NB",

    # Finlandés / Suomi
    "fi": "FI",

    # Danés
    "da": "DA",

    # Checo
    "cs": "CS",

    # Ucraniano
    "uk": "UK",
}

# Languages NOT fully supported by DeepL (will attempt but may fail)
UNSUPPORTED_LANGUAGES = {
    "ca_ES",  # Catalán
    "eu",     # Euskera
    "sr",     # Serbio
    "bs",     # Bosnio
    "cnr",    # Montenegrino
    "hi",     # Hindi
    "hr",     # Croata (experimental)
}


def get_deepl_code(internal_code: str) -> str | None:
    """
    Convert internal language code to DeepL API code.
    Returns None if language is not mapped.
    """
    return LANGUAGE_MAP.get(internal_code)


def get_internal_code(deepl_code: str) -> str | None:
    """
    Convert DeepL API code back to internal code.
    Returns the first matching internal code.
    """
    deepl_upper = deepl_code.upper()
    for internal, deepl in LANGUAGE_MAP.items():
        if deepl == deepl_upper:
            return internal
    return None


def is_supported(internal_code: str) -> bool:
    """Check if language is fully supported by DeepL."""
    return internal_code in LANGUAGE_MAP and internal_code not in UNSUPPORTED_LANGUAGES


def get_all_languages() -> list[dict]:
    """Get list of all configured languages."""
    return [
        {
            "code": code,
            "deepl_code": deepl_code,
            "supported": code not in UNSUPPORTED_LANGUAGES
        }
        for code, deepl_code in LANGUAGE_MAP.items()
    ]
