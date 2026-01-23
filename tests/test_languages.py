import pytest
from src.config.languages import (
    LANGUAGE_MAP,
    get_deepl_code,
    get_internal_code,
    is_supported,
    get_all_languages,
    UNSUPPORTED_LANGUAGES,
)


class TestLanguageMapping:
    """Test language code mapping functions."""

    def test_get_deepl_code_valid(self):
        """Test getting DeepL code for valid internal codes."""
        assert get_deepl_code("en") == "EN-US"
        assert get_deepl_code("es") == "ES"
        assert get_deepl_code("fr") == "FR"
        assert get_deepl_code("pt_BR") == "PT-BR"
        assert get_deepl_code("de") == "DE"

    def test_get_deepl_code_invalid(self):
        """Test getting DeepL code for invalid codes."""
        assert get_deepl_code("invalid") is None
        assert get_deepl_code("") is None
        assert get_deepl_code("xyz") is None

    def test_is_supported(self):
        """Test checking if language is fully supported."""
        # Supported languages
        assert is_supported("en") is True
        assert is_supported("es") is True
        assert is_supported("fr") is True

        # Unsupported languages
        assert is_supported("ca_ES") is False  # Catalan
        assert is_supported("eu") is False  # Euskera

    def test_get_all_languages(self):
        """Test getting all languages list."""
        languages = get_all_languages()

        assert len(languages) > 0
        assert all("code" in lang for lang in languages)
        assert all("deepl_code" in lang for lang in languages)
        assert all("supported" in lang for lang in languages)

    def test_language_map_completeness(self):
        """Test that all expected languages are in the map."""
        expected_languages = [
            "es", "en", "it", "fr", "de", "pt", "pt_BR",
            "ru", "nl", "zh", "pl", "tr", "hu", "bg",
        ]

        for lang in expected_languages:
            assert lang in LANGUAGE_MAP, f"Missing language: {lang}"

    def test_unsupported_languages_are_in_map(self):
        """Test that unsupported languages are still in the map."""
        for lang in UNSUPPORTED_LANGUAGES:
            assert lang in LANGUAGE_MAP, f"Unsupported lang {lang} not in map"
