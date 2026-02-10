"""
Glossary management service for DeepL API.
Handles creation, storage, and retrieval of client-specific glossaries.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import deepl

from src.config.settings import get_settings
from src.config.languages import LANGUAGE_MAP, get_deepl_code

logger = logging.getLogger(__name__)

# Base directory for glossary storage
GLOSSARIES_DIR = Path(__file__).parent.parent.parent / "data" / "glossaries"


class GlossaryService:
    """Service for managing DeepL glossaries per client."""

    def __init__(self):
        settings = get_settings()
        self.translator = deepl.Translator(settings.deepl_api_key)
        GLOSSARIES_DIR.mkdir(parents=True, exist_ok=True)

    def _get_client_dir(self, client_id: str) -> Path:
        """Get the directory for a client's glossaries."""
        client_dir = GLOSSARIES_DIR / client_id
        client_dir.mkdir(parents=True, exist_ok=True)
        return client_dir

    def _get_glossary_path(self, client_id: str, source_lang: str, target_lang: str) -> Path:
        """Get the path to a glossary JSON file."""
        return self._get_client_dir(client_id) / f"{source_lang}_{target_lang}.json"

    def _load_glossary(self, client_id: str, source_lang: str, target_lang: str) -> Optional[dict]:
        """Load a glossary from JSON file."""
        path = self._get_glossary_path(client_id, source_lang, target_lang)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_glossary(self, client_id: str, source_lang: str, target_lang: str, data: dict):
        """Save a glossary to JSON file."""
        path = self._get_glossary_path(client_id, source_lang, target_lang)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved glossary for {client_id}: {source_lang} -> {target_lang}")

    def _delete_glossary_file(self, client_id: str, source_lang: str, target_lang: str) -> bool:
        """Delete a glossary JSON file."""
        path = self._get_glossary_path(client_id, source_lang, target_lang)
        if path.exists():
            path.unlink()
            return True
        return False

    async def create_or_update_glossary(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str,
        entries: dict[str, str],
        name: Optional[str] = None
    ) -> dict:
        """
        Create or update a glossary for a client.

        If glossary exists, deletes old one in DeepL and creates new one.
        """
        # Convert to DeepL language codes
        deepl_source = get_deepl_code(source_lang)
        deepl_target = get_deepl_code(target_lang)

        if not deepl_source or not deepl_target:
            raise ValueError(f"Invalid language codes: {source_lang} or {target_lang}")

        # Check if glossary already exists
        existing = self._load_glossary(client_id, source_lang, target_lang)

        # If exists, delete old glossary from DeepL first
        if existing and existing.get("deepl_glossary_id"):
            try:
                self.translator.delete_glossary(existing["deepl_glossary_id"])
                logger.info(f"Deleted old DeepL glossary: {existing['deepl_glossary_id']}")
            except deepl.DeepLException as e:
                logger.warning(f"Could not delete old glossary: {e}")

        # Create new glossary in DeepL
        glossary_name = name or f"{client_id}_{source_lang}_{target_lang}"

        try:
            # DeepL requires base language codes for glossaries in most cases,
            # but ES-419 is a valid distinct code (not same as ES)
            deepl_source_base = deepl_source if deepl_source == "ES-419" else deepl_source.split("-")[0]

            # For target, some languages need base code for glossaries
            deepl_target_glossary = deepl_target
            if deepl_target in ["EN-US", "EN-GB"]:
                deepl_target_glossary = "EN"
            elif deepl_target in ["PT-PT", "PT-BR"]:
                deepl_target_glossary = "PT"

            glossary = self.translator.create_glossary(
                name=glossary_name,
                source_lang=deepl_source_base,
                target_lang=deepl_target_glossary,
                entries=entries
            )

            logger.info(f"Created DeepL glossary: {glossary.glossary_id}")

        except deepl.DeepLException as e:
            logger.error(f"Failed to create glossary in DeepL: {e}")
            raise ValueError(f"DeepL error: {str(e)}")

        # Save to JSON
        now = datetime.utcnow().isoformat() + "Z"
        glossary_data = {
            "client_id": client_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "deepl_glossary_id": glossary.glossary_id,
            "deepl_source_lang": deepl_source_base,
            "deepl_target_lang": deepl_target_glossary,
            "name": glossary_name,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
            "entry_count": len(entries),
            "entries": entries
        }

        self._save_glossary(client_id, source_lang, target_lang, glossary_data)

        return glossary_data

    async def get_glossary(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str
    ) -> Optional[dict]:
        """Get a specific glossary for a client."""
        return self._load_glossary(client_id, source_lang, target_lang)

    async def get_glossary_id(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str
    ) -> Optional[str]:
        """Get the DeepL glossary ID for a client's language pair."""
        glossary = self._load_glossary(client_id, source_lang, target_lang)
        if glossary:
            return glossary.get("deepl_glossary_id")
        return None

    async def list_client_glossaries(self, client_id: str) -> list[dict]:
        """List all glossaries for a client."""
        client_dir = self._get_client_dir(client_id)
        glossaries = []

        for path in client_dir.glob("*.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Return summary without full entries
                glossaries.append({
                    "client_id": data["client_id"],
                    "source_lang": data["source_lang"],
                    "target_lang": data["target_lang"],
                    "deepl_glossary_id": data["deepl_glossary_id"],
                    "name": data["name"],
                    "entry_count": data["entry_count"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"]
                })

        return glossaries

    async def list_all_clients(self) -> list[str]:
        """List all clients that have glossaries."""
        clients = []
        for path in GLOSSARIES_DIR.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                clients.append(path.name)
        return sorted(clients)

    async def delete_glossary(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str
    ) -> bool:
        """Delete a glossary from both DeepL and local storage."""
        glossary = self._load_glossary(client_id, source_lang, target_lang)

        if not glossary:
            return False

        # Delete from DeepL
        if glossary.get("deepl_glossary_id"):
            try:
                self.translator.delete_glossary(glossary["deepl_glossary_id"])
                logger.info(f"Deleted DeepL glossary: {glossary['deepl_glossary_id']}")
            except deepl.DeepLException as e:
                logger.warning(f"Could not delete glossary from DeepL: {e}")

        # Delete local file
        self._delete_glossary_file(client_id, source_lang, target_lang)

        return True

    async def add_entries(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str,
        new_entries: dict[str, str]
    ) -> dict:
        """
        Add entries to an existing glossary.
        Creates new glossary if none exists.
        """
        existing = self._load_glossary(client_id, source_lang, target_lang)

        if existing:
            # Merge entries
            entries = existing.get("entries", {})
            entries.update(new_entries)
        else:
            entries = new_entries

        # Create/update glossary with merged entries
        return await self.create_or_update_glossary(
            client_id=client_id,
            source_lang=source_lang,
            target_lang=target_lang,
            entries=entries
        )

    async def remove_entries(
        self,
        client_id: str,
        source_lang: str,
        target_lang: str,
        terms_to_remove: list[str]
    ) -> Optional[dict]:
        """Remove specific entries from a glossary."""
        existing = self._load_glossary(client_id, source_lang, target_lang)

        if not existing:
            return None

        # Remove entries
        entries = existing.get("entries", {})
        for term in terms_to_remove:
            entries.pop(term, None)

        if not entries:
            # No entries left, delete the glossary
            await self.delete_glossary(client_id, source_lang, target_lang)
            return None

        # Recreate glossary with remaining entries
        return await self.create_or_update_glossary(
            client_id=client_id,
            source_lang=source_lang,
            target_lang=target_lang,
            entries=entries
        )


# Singleton instance
glossary_service = GlossaryService()
