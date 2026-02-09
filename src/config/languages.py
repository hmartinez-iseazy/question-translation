# Language mapping configuration
# Maps internal language codes to DeepL API codes
#
# Format: "internal_code": "deepl_code"
# Add new languages here as needed

from enum import Enum


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

    # Catalán
    "ca_ES": "CA",

    # Euskera
    "eu": "EU",

    # Mexicano (español mexicano) - DeepL no tiene es-MX, usar latinoamericano
    "mx": "ES-419",

    # Húngaro
    "hu": "HU",

    # Croata
    "hr": "HR",

    # Serbio
    "sr": "SR",

    # Bosnio
    "bs": "BS",

    # Búlgaro
    "bg": "BG",

    # Montenegrino - DeepL no lo tiene, usar bosnio (más cercano, alfabeto latino)
    "cnr": "BS",

    # Flamenco (holandés belga) - usar holandés
    "nl_be": "NL",

    # Turco
    "tr": "TR",

    # Eslovaco
    "sk": "SK",

    # Hindi
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

# Languages NOT directly supported by DeepL (mapped to closest alternative)
UNSUPPORTED_LANGUAGES = {
    "cnr",    # Montenegrino -> Bosnio (BS)
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


# Enum for Swagger dropdown - only fully supported languages
class TargetLanguage(str, Enum):
    """Supported target languages for translation (Swagger dropdown)."""

    # Español
    ES = "es"
    # English (US)
    EN = "en"
    # Italiano
    IT = "it"
    # Français
    FR = "fr"
    # Deutsch
    DE = "de"
    # Português (Portugal)
    PT = "pt"
    # Português (Brasil)
    PT_BR = "pt_BR"
    # Русский
    RU = "ru"
    # Nederlands
    NL = "nl"
    # 中文 (简体)
    ZH = "zh"
    # 日本語
    JP = "jp"
    # Polski
    PL = "pl"
    # Ελληνικά
    GR = "gr"
    # Română
    RO = "ro"
    # Magyar
    HU = "hu"
    # Български
    BG = "bg"
    # Türkçe
    TR = "tr"
    # Slovenčina
    SK = "sk"
    # Norsk
    NO = "no"
    # Suomi
    FI = "fi"
    # Dansk
    DA = "da"
    # Čeština
    CS = "cs"
    # Українська
    UK = "uk"
    # Nederlands (België)
    NL_BE = "nl_be"
    # Español (México) - uses ES-419 (Latin American Spanish)
    MX = "mx"
    # Català
    CA_ES = "ca_ES"
    # Euskara
    EU = "eu"
    # Hrvatski
    HR = "hr"
    # Srpski
    SR = "sr"
    # Bosanski
    BS = "bs"
    # Crnogorski - uses BS (Bosnian)
    CNR = "cnr"

    @classmethod
    def get_deepl_code(cls, value: str) -> str | None:
        """Get the DeepL API code for this language."""
        return LANGUAGE_MAP.get(value)
