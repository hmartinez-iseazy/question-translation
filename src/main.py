import io
import asyncio
import zipfile
import time
import uuid
from time import perf_counter
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config.settings import get_settings
from src.config.logging import setup_logging, get_logger
from src.config.languages import (
    LANGUAGE_MAP,
    get_deepl_code,
    get_all_languages,
    is_supported,
)
from src.schemas.translation import (
    TranslationResponse,
    SupportedLanguagesResponse,
    LanguageInfo,
    BatchTranslationResponse,
    BatchTranslationResult,
    GlossaryEntryCreate,
    GlossaryAddEntries,
    GlossaryRemoveEntries,
    GlossarySummary,
    GlossaryDetail,
    GlossaryListResponse,
    ClientListResponse,
)
from src.services.translator import get_translator_service
from src.services.excel_processor import get_excel_processor
from src.services.glossary import glossary_service
from src.middleware.auth import verify_api_key
from src.middleware.rate_limit import check_rate_limit

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Starting Question Translation Service")

    if not settings.deepl_api_key or settings.deepl_api_key == "your_deepl_api_key_here":
        logger.warning("DeepL API key not configured")

    if not settings.api_key:
        logger.warning("API authentication disabled (no API_KEY configured)")

    # Verify DeepL connection
    try:
        translator = get_translator_service()
        if translator.check_connection():
            logger.info("DeepL API connection verified")
        else:
            logger.error("DeepL API connection failed")
    except Exception as e:
        logger.error(f"DeepL initialization error: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Question Translation Service")


app = FastAPI(
    title="Questions Translation Service",
    description="""
    Microservice for translating question Excel files using DeepL API.

    ## Authentication
    All endpoints (except health checks) require an API key in the `X-API-Key` header.

    ## Rate Limiting
    Requests are rate limited per client. Check response headers for limit info.

    ## Endpoints
    - `POST /translate` - Translate to a single language, returns Excel
    - `POST /translate/batch` - Translate to multiple languages, returns ZIP

    ## Excel Format
    - Sheet name: `Questions`
    - Translates columns D, E, F, G, H (starting row 7)
    - Updates language code in cell C3
    """,
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Add request_id to state for use in handlers
    request.state.request_id = request_id

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else "unknown",
        },
    )

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id

    return response


# ============== Health Endpoints ==============


@app.get("/", tags=["Health"])
async def root():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "question-translation", "version": "2.0.0"}


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check with dependency status."""
    health = {
        "status": "healthy",
        "service": "question-translation",
        "version": "2.0.0",
        "checks": {},
    }

    # Check DeepL connection
    try:
        translator = get_translator_service()
        deepl_ok = translator.check_connection()
        health["checks"]["deepl"] = {
            "status": "healthy" if deepl_ok else "unhealthy",
            "message": "Connected" if deepl_ok else "Connection failed",
        }
        if not deepl_ok:
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["deepl"] = {"status": "unhealthy", "message": str(e)}
        health["status"] = "degraded"

    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Kubernetes readiness probe."""
    try:
        translator = get_translator_service()
        if translator.check_connection():
            return {"status": "ready"}
        raise HTTPException(status_code=503, detail="DeepL not ready")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/live", tags=["Health"])
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


# ============== Info Endpoints ==============


@app.get("/languages", response_model=SupportedLanguagesResponse, tags=["Info"])
async def get_supported_languages():
    """Get list of supported target languages with their DeepL mappings."""
    languages = [LanguageInfo(**lang) for lang in get_all_languages()]
    return SupportedLanguagesResponse(languages=languages, total=len(languages))


@app.get("/usage", tags=["Info"], dependencies=[Depends(verify_api_key)])
async def get_api_usage(rate_limit: dict = Depends(check_rate_limit)):
    """Get current DeepL API usage statistics."""
    try:
        translator = get_translator_service()
        usage = translator.get_usage()
        return {
            "status": "ok",
            "usage": usage,
            "remaining_characters": usage["character_limit"] - usage["character_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage: {str(e)}")


# ============== Glossary Endpoints ==============


@app.get("/glossaries/clients", response_model=ClientListResponse, tags=["Glossaries"])
async def list_clients_with_glossaries(
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """List all clients that have glossaries configured."""
    clients = await glossary_service.list_all_clients()
    return ClientListResponse(clients=clients, total=len(clients))


@app.get("/glossaries/{client_id}", response_model=GlossaryListResponse, tags=["Glossaries"])
async def list_client_glossaries(
    client_id: str,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """List all glossaries for a specific client."""
    glossaries = await glossary_service.list_client_glossaries(client_id)
    return GlossaryListResponse(
        client_id=client_id,
        glossaries=[GlossarySummary(**g) for g in glossaries],
        total=len(glossaries),
    )


@app.get(
    "/glossaries/{client_id}/{source_lang}/{target_lang}",
    response_model=GlossaryDetail,
    tags=["Glossaries"],
)
async def get_glossary(
    client_id: str,
    source_lang: str,
    target_lang: str,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """Get a specific glossary with all entries."""
    glossary = await glossary_service.get_glossary(client_id, source_lang, target_lang)
    if not glossary:
        raise HTTPException(
            status_code=404,
            detail=f"Glossary not found: {client_id}/{source_lang}/{target_lang}",
        )
    return GlossaryDetail(**glossary)


@app.post(
    "/glossaries/{client_id}",
    response_model=GlossaryDetail,
    tags=["Glossaries"],
    status_code=201,
)
async def create_or_update_glossary(
    client_id: str,
    glossary_data: GlossaryEntryCreate,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """
    Create or update a glossary for a client.

    If glossary already exists for the language pair, it will be replaced.
    DeepL glossaries are immutable, so updates require recreating the glossary.
    """
    try:
        result = await glossary_service.create_or_update_glossary(
            client_id=client_id,
            source_lang=glossary_data.source_lang,
            target_lang=glossary_data.target_lang,
            entries=glossary_data.entries,
            name=glossary_data.name,
        )
        return GlossaryDetail(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create glossary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create glossary: {str(e)}")


@app.post(
    "/glossaries/{client_id}/{source_lang}/{target_lang}/entries",
    response_model=GlossaryDetail,
    tags=["Glossaries"],
)
async def add_glossary_entries(
    client_id: str,
    source_lang: str,
    target_lang: str,
    data: GlossaryAddEntries,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """
    Add entries to an existing glossary.

    If glossary doesn't exist, creates a new one.
    Existing entries with the same source term will be overwritten.
    """
    try:
        result = await glossary_service.add_entries(
            client_id=client_id,
            source_lang=source_lang,
            target_lang=target_lang,
            new_entries=data.entries,
        )
        return GlossaryDetail(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add entries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add entries: {str(e)}")


@app.delete(
    "/glossaries/{client_id}/{source_lang}/{target_lang}/entries",
    response_model=GlossaryDetail | dict,
    tags=["Glossaries"],
)
async def remove_glossary_entries(
    client_id: str,
    source_lang: str,
    target_lang: str,
    data: GlossaryRemoveEntries,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """
    Remove specific entries from a glossary.

    If all entries are removed, the glossary is deleted.
    """
    try:
        result = await glossary_service.remove_entries(
            client_id=client_id,
            source_lang=source_lang,
            target_lang=target_lang,
            terms_to_remove=data.terms,
        )
        if result is None:
            return {"message": "Glossary deleted (no entries remaining)"}
        return GlossaryDetail(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to remove entries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove entries: {str(e)}")


@app.delete("/glossaries/{client_id}/{source_lang}/{target_lang}", tags=["Glossaries"])
async def delete_glossary(
    client_id: str,
    source_lang: str,
    target_lang: str,
    rate_limit: dict = Depends(check_rate_limit),
    _: str = Depends(verify_api_key),
):
    """Delete a glossary completely from both DeepL and local storage."""
    deleted = await glossary_service.delete_glossary(client_id, source_lang, target_lang)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Glossary not found: {client_id}/{source_lang}/{target_lang}",
        )
    return {"message": "Glossary deleted successfully"}


# ============== Translation Endpoints ==============


async def validate_file(file: UploadFile) -> bytes:
    """Validate uploaded file."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx)",
        )

    content = await file.read()
    max_size = settings.max_file_size_mb * 1024 * 1024

    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size_mb}MB",
        )

    return content


@app.post(
    "/translate",
    response_class=StreamingResponse,
    tags=["Translation"],
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {
            "description": "Translated Excel file",
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
        },
        400: {"description": "Invalid request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Translation error"},
    },
)
async def translate_excel(
    request: Request,
    file: UploadFile = File(..., description="Excel file to translate (.xlsx)"),
    target_language: str = Form(
        ...,
        description="Target language code (e.g., 'en', 'fr', 'de', 'pt_BR')",
    ),
    client_id: str | None = Form(
        None,
        description="Optional client ID to use client-specific glossary for translation",
    ),
    rate_limit: dict = Depends(check_rate_limit),
):
    """
    Translate an Excel file with questions to a single language.

    - **file**: Excel file (.xlsx) with sheet 'Questions'
    - **target_language**: Target language code (see /languages for options)
    - **client_id**: Optional client ID to use their glossary (if configured)

    Returns the translated Excel file.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log = get_logger(__name__, request_id=request_id)

    # Validate language code
    deepl_code = get_deepl_code(target_language)
    if not deepl_code:
        available = list(LANGUAGE_MAP.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown language code: '{target_language}'. Available: {available}",
        )

    if not is_supported(target_language):
        log.warning(f"Language '{target_language}' may not be fully supported by DeepL")

    try:
        content = await validate_file(file)
        file_stream = io.BytesIO(content)

        translator = get_translator_service()
        processor = get_excel_processor(translator)

        # Look up glossary if client_id provided
        glossary_id = None
        if client_id:
            # We need to determine source language first to look up glossary
            # For now, assume source is 'es' (Spanish) - could be enhanced to detect
            glossary_id = await glossary_service.get_glossary_id(
                client_id, "es", target_language
            )
            if glossary_id:
                log.info(f"Using glossary {glossary_id} for client {client_id}")
            else:
                log.info(f"No glossary found for client {client_id} (es -> {target_language})")

        log.info(f"Starting translation to {target_language}")

        translated_bytes, source_lang, rows_count = await processor.process_excel(
            file_stream,
            target_lang_internal=target_language,
            target_lang_deepl=deepl_code,
            glossary_id=glossary_id,
        )

        log.info(f"Translation completed: {rows_count} rows translated")

        original_name = file.filename.rsplit(".", 1)[0]
        output_filename = f"{original_name}_{target_language}.xlsx"

        headers = {
            "Content-Disposition": f'attachment; filename="{output_filename}"',
            "X-Source-Language": source_lang or "unknown",
            "X-Target-Language": target_language,
            "X-Rows-Translated": str(rows_count),
            "X-RateLimit-Limit": str(rate_limit["limit"]),
            "X-RateLimit-Remaining": str(rate_limit["remaining"]),
        }
        if client_id:
            headers["X-Client-ID"] = client_id
        if glossary_id:
            headers["X-Glossary-Used"] = "true"

        response = StreamingResponse(
            io.BytesIO(translated_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@app.post(
    "/translate/batch",
    response_class=StreamingResponse,
    tags=["Translation"],
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {
            "description": "ZIP file containing all translated Excel files",
            "content": {"application/zip": {}},
        },
        400: {"description": "Invalid request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Translation error"},
    },
)
async def translate_excel_batch(
    request: Request,
    file: UploadFile = File(..., description="Excel file to translate (.xlsx)"),
    target_languages: str = Form(
        ...,
        description="Comma-separated list of target language codes (e.g., 'en,fr,de,it')",
    ),
    client_id: str | None = Form(
        None,
        description="Optional client ID to use client-specific glossaries for translation",
    ),
    rate_limit: dict = Depends(check_rate_limit),
):
    """
    Translate an Excel file to multiple languages at once.

    - **file**: Excel file (.xlsx) with sheet 'Questions'
    - **target_languages**: Comma-separated language codes (e.g., 'en,fr,de,it')
    - **client_id**: Optional client ID to use their glossaries (if configured)

    Returns a ZIP file containing all translated Excel files.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log = get_logger(__name__, request_id=request_id)

    # Parse and validate language codes
    languages = [lang.strip() for lang in target_languages.split(",") if lang.strip()]

    if not languages:
        raise HTTPException(
            status_code=400,
            detail="No target languages provided. Use comma-separated codes (e.g., 'en,fr,de')",
        )

    if len(languages) > settings.max_languages_per_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Too many languages. Maximum is {settings.max_languages_per_batch}",
        )

    # Validate all language codes
    invalid_languages = []
    language_mappings = []

    for lang in languages:
        deepl_code = get_deepl_code(lang)
        if not deepl_code:
            invalid_languages.append(lang)
        else:
            language_mappings.append((lang, deepl_code))

    if invalid_languages:
        available = list(LANGUAGE_MAP.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown language codes: {invalid_languages}. Available: {available}",
        )

    try:
        content = await validate_file(file)
        original_name = file.filename.rsplit(".", 1)[0]

        translator = get_translator_service()
        processor = get_excel_processor(translator)

        # Look up glossaries for each language if client_id provided
        glossary_map = {}
        if client_id:
            for internal_code, _ in language_mappings:
                gid = await glossary_service.get_glossary_id(client_id, "es", internal_code)
                if gid:
                    glossary_map[internal_code] = gid
                    log.info(f"Found glossary for {client_id}: es -> {internal_code}")

        log.info(f"Starting batch translation to {len(languages)} languages")

        async def translate_single(
            internal_code: str, deepl_code: str
        ) -> tuple[str, bytes, int]:
            t0 = perf_counter()
            file_stream = io.BytesIO(content)
            glossary_id = glossary_map.get(internal_code)
            translated_bytes, _, rows_count = await processor.process_excel(
                file_stream,
                target_lang_internal=internal_code,
                target_lang_deepl=deepl_code,
                glossary_id=glossary_id,
            )
            log.info(f"[TIMING] translate_single({internal_code}): {perf_counter() - t0:.3f}s")
            return internal_code, translated_bytes, rows_count

        t_gather = perf_counter()
        tasks = [
            translate_single(internal_code, deepl_code)
            for internal_code, deepl_code in language_mappings
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.info(f"[TIMING] asyncio.gather ({len(languages)} langs): {perf_counter() - t_gather:.3f}s")

        # Create ZIP file
        t_zip = perf_counter()
        zip_buffer = io.BytesIO()
        successful = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for result in results:
                if isinstance(result, Exception):
                    log.error(f"Translation error: {result}")
                    continue

                lang_code, translated_bytes, _ = result
                filename = f"{original_name}_{lang_code}.xlsx"
                zip_file.writestr(filename, translated_bytes)
                successful += 1

        zip_buffer.seek(0)
        log.info(f"[TIMING] zip_creation: {perf_counter() - t_zip:.3f}s")

        log.info(f"Batch translation completed: {successful}/{len(languages)} successful")

        zip_filename = f"{original_name}_translations.zip"

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"',
                "X-Languages-Requested": ",".join(languages),
                "X-Files-Generated": str(successful),
                "X-RateLimit-Limit": str(rate_limit["limit"]),
                "X-RateLimit-Remaining": str(rate_limit["remaining"]),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Batch translation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch translation failed: {str(e)}")


@app.post(
    "/translate/batch/info",
    response_model=BatchTranslationResponse,
    tags=["Translation"],
    dependencies=[Depends(verify_api_key)],
)
async def translate_excel_batch_info(
    request: Request,
    file: UploadFile = File(..., description="Excel file to translate (.xlsx)"),
    target_languages: str = Form(..., description="Comma-separated language codes"),
    rate_limit: dict = Depends(check_rate_limit),
):
    """Translate to multiple languages and return metadata."""
    languages = [lang.strip() for lang in target_languages.split(",") if lang.strip()]

    if not languages:
        raise HTTPException(status_code=400, detail="No target languages provided")

    if len(languages) > settings.max_languages_per_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Too many languages. Maximum is {settings.max_languages_per_batch}",
        )

    invalid_languages = []
    language_mappings = []

    for lang in languages:
        deepl_code = get_deepl_code(lang)
        if not deepl_code:
            invalid_languages.append(lang)
        else:
            language_mappings.append((lang, deepl_code))

    if invalid_languages:
        available = list(LANGUAGE_MAP.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown language codes: {invalid_languages}. Available: {available}",
        )

    try:
        content = await validate_file(file)
        original_name = file.filename.rsplit(".", 1)[0]

        translator = get_translator_service()
        processor = get_excel_processor(translator)

        async def translate_single(internal_code: str, deepl_code: str):
            file_stream = io.BytesIO(content)
            _, source_lang, rows_count = await processor.process_excel(
                file_stream,
                target_lang_internal=internal_code,
                target_lang_deepl=deepl_code,
            )
            return internal_code, source_lang, rows_count

        tasks = [
            translate_single(internal_code, deepl_code)
            for internal_code, deepl_code in language_mappings
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        translation_results = []
        source_lang = None

        for result in results:
            if isinstance(result, Exception):
                translation_results.append(
                    BatchTranslationResult(
                        language="error",
                        success=False,
                        error=str(result),
                    )
                )
            else:
                lang_code, src_lang, rows = result
                source_lang = src_lang or source_lang
                translation_results.append(
                    BatchTranslationResult(
                        language=lang_code,
                        success=True,
                        filename=f"{original_name}_{lang_code}.xlsx",
                        rows_translated=rows,
                    )
                )

        successful = len([r for r in translation_results if r.success])

        return BatchTranslationResponse(
            success=successful > 0,
            message=f"Translated to {successful}/{len(languages)} languages",
            source_language=source_lang,
            total_languages=len(languages),
            successful_translations=successful,
            results=translation_results,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch translation failed: {str(e)}")


@app.post(
    "/translate/info",
    response_model=TranslationResponse,
    tags=["Translation"],
    dependencies=[Depends(verify_api_key)],
)
async def translate_excel_info(
    file: UploadFile = File(..., description="Excel file to translate (.xlsx)"),
    target_language: str = Form(..., description="Target language code"),
    rate_limit: dict = Depends(check_rate_limit),
):
    """Translate and return metadata (without file download)."""
    deepl_code = get_deepl_code(target_language)
    if not deepl_code:
        available = list(LANGUAGE_MAP.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown language code: '{target_language}'. Available: {available}",
        )

    try:
        content = await validate_file(file)
        file_stream = io.BytesIO(content)

        translator = get_translator_service()
        processor = get_excel_processor(translator)

        _, source_lang, rows_count = await processor.process_excel(
            file_stream,
            target_lang_internal=target_language,
            target_lang_deepl=deepl_code,
        )

        original_name = file.filename.rsplit(".", 1)[0]
        output_filename = f"{original_name}_{target_language}.xlsx"

        return TranslationResponse(
            success=True,
            message="Translation completed successfully",
            source_language=source_lang,
            target_language=target_language,
            rows_translated=rows_count,
            filename=output_filename,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
