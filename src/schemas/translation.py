from pydantic import BaseModel, Field


class TranslationRequest(BaseModel):
    target_language: str = Field(
        ...,
        description="Target language code (internal format)",
        examples=["en", "fr", "de", "it", "pt_BR"]
    )


class TranslationResponse(BaseModel):
    success: bool
    message: str
    source_language: str | None = None
    target_language: str | None = None
    rows_translated: int = 0
    filename: str | None = None


class BatchTranslationResult(BaseModel):
    language: str
    success: bool
    filename: str | None = None
    rows_translated: int = 0
    error: str | None = None


class BatchTranslationResponse(BaseModel):
    success: bool
    message: str
    source_language: str | None = None
    total_languages: int
    successful_translations: int
    results: list[BatchTranslationResult]


class LanguageInfo(BaseModel):
    code: str
    deepl_code: str
    supported: bool


class SupportedLanguagesResponse(BaseModel):
    languages: list[LanguageInfo]
    total: int
    unsupported_warning: str = "Languages marked as unsupported may not translate correctly"
