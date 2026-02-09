import logging
import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import deepl
from deepl import DeepLException

from src.config.settings import get_settings

# Batch limits to avoid 413 errors
MAX_CHARS_PER_BATCH = 100000  # ~100KB character limit
MAX_TEXTS_PER_BATCH = 200  # Max texts per request

# Languages that require model_type="quality_optimized" (beta/next-gen in DeepL)
QUALITY_OPTIMIZED_LANGS = {"ES-419", "CA", "EU"}

logger = logging.getLogger(__name__)

# Thread pool for running blocking DeepL calls
_executor = ThreadPoolExecutor(max_workers=4)


def _create_batches(indexed_texts: List[tuple[int, str]]) -> List[List[tuple[int, str]]]:
    """Split texts into batches respecting character and count limits."""
    batches = []
    current_batch = []
    current_chars = 0

    for item in indexed_texts:
        text_len = len(item[1])

        if current_batch and (
            current_chars + text_len > MAX_CHARS_PER_BATCH
            or len(current_batch) >= MAX_TEXTS_PER_BATCH
        ):
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(item)
        current_chars += text_len

    if current_batch:
        batches.append(current_batch)

    return batches


class TranslatorService:
    def __init__(self):
        self.settings = get_settings()
        self.translator = deepl.Translator(self.settings.deepl_api_key)
        self.max_retries = self.settings.deepl_max_retries
        self.timeout = self.settings.deepl_timeout

    def _translate_sync(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str | None = None,
        glossary_id: str | None = None,
    ) -> List:
        """Synchronous translation call (runs in thread pool)."""
        t0 = time.perf_counter()
        total_chars = sum(len(t) for t in texts)
        kwargs = {
            "text": texts,
            "target_lang": target_lang,
            "source_lang": source_lang.upper() if source_lang else None,
        }
        if target_lang.upper() in QUALITY_OPTIMIZED_LANGS:
            kwargs["model_type"] = "quality_optimized"
        if glossary_id:
            kwargs["glossary"] = glossary_id
            logger.debug(f"Using glossary: {glossary_id}")
        result = self.translator.translate_text(**kwargs)
        logger.info(f"[TIMING] deepl_api_call: {time.perf_counter() - t0:.3f}s ({len(texts)} texts, {total_chars} chars, target={target_lang})")
        return result

    async def _translate_with_retry(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str | None = None,
        glossary_id: str | None = None,
    ) -> List:
        """
        Translate with exponential backoff retry on failure.

        Retries on:
        - Rate limit errors (429)
        - Server errors (5xx)
        - Connection errors
        """
        loop = asyncio.get_event_loop()
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        lambda t=texts, g=glossary_id: self._translate_sync(
                            t, target_lang, source_lang, g
                        ),
                    ),
                    timeout=self.timeout,
                )
                return result

            except asyncio.TimeoutError:
                last_exception = TimeoutError(
                    f"DeepL request timed out after {self.timeout}s"
                )
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.max_retries + 1}"
                )

            except DeepLException as e:
                last_exception = e
                error_str = str(e).lower()

                # Don't retry on client errors (except rate limit)
                if "quota" in error_str or "limit" in error_str:
                    logger.warning(f"Rate limit hit, attempt {attempt + 1}")
                elif "400" in error_str or "401" in error_str or "403" in error_str:
                    # Client error, don't retry
                    raise

                logger.warning(
                    f"DeepL error on attempt {attempt + 1}/{self.max_retries + 1}: {e}"
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Unexpected error on attempt {attempt + 1}/{self.max_retries + 1}: {e}"
                )

            # Exponential backoff with jitter
            if attempt < self.max_retries:
                base_delay = 2**attempt
                jitter = random.uniform(0, 1)
                delay = base_delay + jitter
                logger.info(f"Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_exception or Exception("Translation failed after all retries")

    async def translate_text(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
        glossary_id: str | None = None,
    ) -> str:
        """Translate a single text string."""
        if not text or not text.strip():
            return text

        result = await self._translate_with_retry(
            [text], target_lang, source_lang, glossary_id
        )
        return result[0].text if isinstance(result, list) else result.text

    async def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str | None = None,
        glossary_id: str | None = None,
    ) -> List[str]:
        """Translate multiple texts in batches with retry support."""
        if not texts:
            return []

        # Filter out empty strings but keep track of their positions
        indexed_texts = [(i, t) for i, t in enumerate(texts) if t and t.strip()]

        if not indexed_texts:
            return texts

        # Create smart batches based on character count
        batches = _create_batches(indexed_texts)
        total_batches = len(batches)

        if glossary_id:
            logger.info(
                f"Translating {len(indexed_texts)} texts in {total_batches} batch(es) with glossary {glossary_id}"
            )
        else:
            logger.info(f"Translating {len(indexed_texts)} texts in {total_batches} batch(es)")

        # Prepare result list
        translated = list(texts)

        t_batch_total = time.perf_counter()

        for batch_num, batch in enumerate(batches, 1):
            texts_to_translate = [t for _, t in batch]

            logger.info(
                f"Batch {batch_num}/{total_batches}: {len(texts_to_translate)} texts"
            )

            # Use retry-enabled translation
            t0 = time.perf_counter()
            results = await self._translate_with_retry(
                texts_to_translate, target_lang, source_lang, glossary_id
            )
            logger.info(f"[TIMING] batch_{batch_num}_with_retry: {time.perf_counter() - t0:.3f}s")

            # Handle single result
            if not isinstance(results, list):
                results = [results]

            # Map translated texts back to original positions
            for (original_idx, _), result in zip(batch, results):
                translated[original_idx] = result.text

            logger.info(f"Batch {batch_num}/{total_batches} completed")

        logger.info(f"[TIMING] translate_batch TOTAL: {time.perf_counter() - t_batch_total:.3f}s ({len(indexed_texts)} texts, {total_batches} batches, target={target_lang})")
        return translated

    def get_usage(self) -> dict:
        """Get current API usage statistics."""
        usage = self.translator.get_usage()
        return {
            "character_count": usage.character.count if usage.character else 0,
            "character_limit": usage.character.limit if usage.character else 0,
        }

    def check_connection(self) -> bool:
        """Check if DeepL API is reachable."""
        try:
            self.translator.get_usage()
            return True
        except Exception as e:
            logger.error(f"DeepL connection check failed: {e}")
            return False


def get_translator_service() -> TranslatorService:
    return TranslatorService()
