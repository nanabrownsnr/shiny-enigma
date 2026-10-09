"""Encrypted MongoDB persistence for connection credentials.

Stores one encrypted credential set per exact (user_id, persona_id) pair.
"""

import contextlib
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pymongo import ASCENDING

_active_store: "ConnectionStore | None" = None


def set_active_store(store: "ConnectionStore | None") -> None:
    """Set the process-scoped store created/closed by the ASGI lifespan."""
    global _active_store
    _active_store = store


def get_active_store() -> "ConnectionStore | None":
    """Get the currently active connection store."""
    return _active_store


class ConnectionStore:
    """Store encrypted credentials per (user_id, persona_id) pair."""

    def __init__(self, collection: Any, encryption_key: str):
        """Initialize with MongoDB collection and Fernet key.

        Args:
            collection: MongoDB collection for storing connections
            encryption_key: Fernet encryption key byte string
        """
        self.collection = collection
        self.cipher = Fernet(encryption_key.encode("ascii"))

    async def setup(self) -> None:
        """Create compound uniqueness constraint on startup."""
        await self.collection.create_index(
            [("user_id", ASCENDING), ("persona_id", ASCENDING)], unique=True
        )

    async def save(
        self,
        user_id: str,
        persona_id: str,
        values: dict[str, str],
    ) -> str:
        """Encrypt credential values and upsert for exact identity pair.

        Args:
            user_id: Verified user identifier fromJWT claims
            persona_id: Persona/project identifier from request header
            values: Credential dictionary with string values to encrypt

        Returns:
            MongoDB document ID or 'updated' if existing record
        """
        now = datetime.now(UTC)
        encrypted = {
            key: self.cipher.encrypt(value.encode("utf-8")).decode("ascii")
            for key, value in values.items()
        }
        result = await self.collection.update_one(
            {"user_id": user_id, "persona_id": persona_id},
            {
                "$set": {"values": encrypted, "modified": now},
                "$setOnInsert": {"created": now},
            },
            upsert=True,
        )
        return str(result.upserted_id) if result.upserted_id else "updated"

    async def get(self, user_id: str, persona_id: str) -> dict[str, Any] | None:
        """Decrypt and return credentials for exact identity pair.

        Args:
            user_id: Verified user identifier from JWT claims
            persona_id: Persona/project identifier from request header

        Returns:
            Decrypted credential dictionary or None if not found

        Raises:
            RuntimeError: If decryption fails (check ENCRYPTION_KEY)
        """
        document = await self.collection.find_one(
            {"user_id": user_id, "persona_id": persona_id}
        )
        if not document:
            return None

        try:
            values = {
                key: self.cipher.decrypt(value.encode("ascii")).decode("utf-8")
                for key, value in document["values"].items()
            }
            return {"id": str(document["_id"]), **values}
        except (InvalidToken, KeyError, TypeError) as exc:
            raise RuntimeError(
                "Stored connection could not be decrypted; check ENCRYPTION_KEY"
            ) from exc

    async def public_metadata(
        self, user_id: str, persona_id: str
    ) -> dict[str, Any] | None:
        """Return safe display fields excluding all credentials.

        Args:
            user_id: Verified user identifier from JWT claims
            persona_id: Persona/project identifier from request header

        Returns:
            Safe metadata dictionary with only display fields
        """
        document = await self.collection.find_one(
            {"user_id": user_id, "persona_id": persona_id},
            {"values.name": 1, "values.created": 1, "modified": 1},
        )
        if not document:
            return None

        values = document.get("values", {})
        safe = {}

        # Decrypt only display fields
        for key in ("name",):
            encrypted_value = values.get(key)
            if encrypted_value:
                with contextlib.suppress(InvalidToken):
                    safe[key] = self.cipher.decrypt(
                        encrypted_value.encode("ascii")
                    ).decode("utf-8")

        return {"id": str(document["_id"]), **safe}

    async def delete(self, user_id: str, persona_id: str) -> bool:
        """Delete credential set for identity pair.

        Args:
            user_id: Verified user identifier from JWT claims
            persona_id: Persona/project identifier from request header

        Returns:
            True if record was deleted, False if no matching record exists
        """
        result = await self.collection.delete_one(
            {"user_id": user_id, "persona_id": persona_id}
        )
        return result.deleted_count > 0

    async def exists(self, user_id: str, persona_id: str) -> bool:
        """Check if credential set exists for identity pair.

        Args:
            user_id: Verified user identifier from JWT claims
            persona_id: Persona/project identifier from request header

        Returns:
            True if credentials exist, False otherwise
        """
        document = await self.collection.find_one(
            {"user_id": user_id, "persona_id": persona_id}
        )
        return bool(document)
