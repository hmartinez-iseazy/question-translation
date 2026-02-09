"""
Document translation service using DeepL Document API.

This service handles translation of complete documents (PDF, DOCX, PPTX, etc.)
preserving their original structure and formatting.
"""

import io
import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import deepl
from deepl import DeepLException

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Thread pool for running blocking DeepL calls
_executor = ThreadPoolExecutor(max_workers=2)

# Supported file extensions for document translation
SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".xlf": "application/xliff+xml",
    ".xliff": "application/xliff+xml",
    ".srt": "application/x-subrip",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class DocumentTranslatorService:
    """Service for translating documents using DeepL Document API."""

    def __init__(self):
        self.settings = get_settings()
        self.translator = deepl.Translator(self.settings.deepl_api_key)

    def _get_file_extension(self, filename: str) -> str:
        """Extract file extension from filename."""
        return Path(filename).suffix.lower()

    def _is_supported_format(self, filename: str) -> bool:
        """Check if the file format is supported for document translation."""
        ext = self._get_file_extension(filename)
        return ext in SUPPORTED_EXTENSIONS

    def _get_content_type(self, filename: str) -> str:
        """Get the content type for the file based on extension."""
        ext = self._get_file_extension(filename)
        return SUPPORTED_EXTENSIONS.get(ext, "application/octet-stream")

    def _translate_document_sync(
        self,
        input_document: io.BytesIO,
        output_document: io.BytesIO,
        target_lang: str,
        filename: str,
    ) -> deepl.DocumentStatus:
        """
        Synchronous document translation (runs in thread pool).

        DeepL's translate_document handles the full flow:
        1. Upload document
        2. Poll for completion
        3. Download translated document
        """
        t0 = time.perf_counter()

        # Reset stream position
        input_document.seek(0)

        # DeepL SDK handles upload, wait, and download automatically
        result = self.translator.translate_document(
            input_document=input_document,
            output_document=output_document,
            target_lang=target_lang,
            filename=filename,
        )

        logger.info(
            f"[TIMING] deepl_document_translation: {time.perf_counter() - t0:.3f}s "
            f"(file={filename}, target={target_lang}, billed={result.billed_characters})"
        )

        return result

    async def translate_document(
        self,
        file_content: bytes,
        filename: str,
        target_lang: str,
    ) -> tuple[bytes, deepl.DocumentStatus]:
        """
        Translate a document to the target language.

        Args:
            file_content: Raw bytes of the document
            filename: Original filename (used for format detection)
            target_lang: DeepL target language code

        Returns:
            Tuple of (translated document bytes, DocumentStatus with metadata)

        Raises:
            ValueError: If file format is not supported
            DeepLException: If translation fails
        """
        if not self._is_supported_format(filename):
            ext = self._get_file_extension(filename)
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
            raise ValueError(
                f"Unsupported file format: '{ext}'. "
                f"Supported formats: {supported}"
            )

        input_buffer = io.BytesIO(file_content)
        input_buffer.name = filename  # Required for DeepL to detect file type
        output_buffer = io.BytesIO()

        loop = asyncio.get_event_loop()

        try:
            status = await loop.run_in_executor(
                _executor,
                lambda: self._translate_document_sync(
                    input_buffer,
                    output_buffer,
                    target_lang,
                    filename,
                ),
            )

            output_buffer.seek(0)
            translated_bytes = output_buffer.read()

            return translated_bytes, status

        except DeepLException as e:
            error_str = str(e).lower()

            if "quota" in error_str:
                logger.error(f"DeepL quota exceeded: {e}")
                raise ValueError("DeepL API quota exceeded. Please try again later.")
            elif "document" in error_str and "not supported" in error_str:
                raise ValueError(f"Document format not supported by DeepL: {e}")
            else:
                logger.error(f"DeepL document translation failed: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error during document translation: {e}")
            raise


def get_document_translator_service() -> DocumentTranslatorService:
    """Factory function for DocumentTranslatorService."""
    return DocumentTranslatorService()
