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


# Glossary schemas
class GlossaryEntryCreate(BaseModel):
    """Request to create or update a glossary."""
    source_lang: str = Field(
        ...,
        description="Source language code (internal format)",
        examples=["es"]
    )
    target_lang: str = Field(
        ...,
        description="Target language code (internal format)",
        examples=["en", "it", "fr"]
    )
    entries: dict[str, str] = Field(
        ...,
        description="Dictionary of source terms to target translations",
        examples=[{"Carcasa": "Case", "Metacrilato": "Acrylic"}]
    )
    name: str | None = Field(
        None,
        description="Optional custom name for the glossary"
    )


class GlossaryAddEntries(BaseModel):
    """Request to add entries to an existing glossary."""
    entries: dict[str, str] = Field(
        ...,
        description="New entries to add to the glossary"
    )


class GlossaryRemoveEntries(BaseModel):
    """Request to remove entries from a glossary."""
    terms: list[str] = Field(
        ...,
        description="Source terms to remove from the glossary"
    )


class GlossarySummary(BaseModel):
    """Summary information about a glossary."""
    client_id: str
    source_lang: str
    target_lang: str
    deepl_glossary_id: str | None = None
    name: str
    entry_count: int
    created_at: str
    updated_at: str


class GlossaryDetail(GlossarySummary):
    """Full glossary information including entries."""
    entries: dict[str, str]
    deepl_source_lang: str
    deepl_target_lang: str


class GlossaryListResponse(BaseModel):
    """Response with list of glossaries."""
    client_id: str
    glossaries: list[GlossarySummary]
    total: int


class ClientListResponse(BaseModel):
    """Response with list of clients that have glossaries."""
    clients: list[str]
    total: int


# Document translation schemas
class DocumentTranslationResponse(BaseModel):
    """Response metadata for document translation."""
    success: bool
    message: str
    original_filename: str
    translated_filename: str
    target_language: str
    detected_source_language: str | None = None
    document_type: str
    billed_characters: int | None = None
