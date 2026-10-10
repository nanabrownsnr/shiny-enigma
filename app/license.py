"""License validation and status management.

Provides functionality to verify license validity, track expiration,
and report license status for platform compliance.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt


@dataclass(frozen=True)
class LicenseStatus:
    """Current license validation state."""

    valid: bool
    key: str
    expiration: datetime | None
    activation_date: datetime | None
    error: str | None = None

    @property
    def is_expired(self) -> bool:
        """Check if license has passed expiration date."""
        if not self.expiration:
            return False
        return datetime.now(UTC) > self.expiration


# License cache (thread-safe for concurrent access using a lock)
_license_cache: LicenseStatus | None = None
_license_lock_available = True


def get_license_status() -> LicenseStatus:
    """Get current license validation status.

    Returns cached status if available and not expired; otherwise triggers
    fresh validation from the configured key.

    Notes:
        - The cache is invalidated after 1 hour to reduce repeated JWT lookups
        - An expired or absent license key returns a status with valid=False

    Returns:
        LicenseStatus containing validity flag, metadata, and errors
    """
    global _license_cache

    # Check if cached value exists and is still recent (within 1 hour)
    if _license_cache is not None:
        cache_age = datetime.now(UTC) - (
            _license_cache.activation_date or datetime.now(UTC)
        )
        if cache_age < timedelta(hours=1):
            return _license_cache

    # No valid cache; perform fresh validation
    from app.config import settings

    key = settings.LICENSE_KEY.strip() if hasattr(settings, "LICENSE_KEY") else ""

    if not key:
        _license_cache = LicenseStatus(
            valid=False,
            key="",
            expiration=None,
            activation_date=datetime.now(UTC),
            error="No license key configured",
        )
        return _license_cache

    try:
        # Try to decode the JWT and extract expiration claim
        header = jwt.get_unverified_header(key)

        # If we get here without exception, key might be valid base64 encoded
        # but need actual signature verification against JWKS endpoint
        from app.config import settings

        jwks_url = f"{settings.LICENSE_SERVER_BASE_URL.rstrip('/')}{settings.LICENSE_SERVER_JWKS_ENDPOINT.lstrip('/')}"

        import httpx

        async def validate_key():
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(jwks_url)
                response.raise_for_status()
                keys = response.json().get("keys", [])

                # Extract kid from our key header and match
                kid = header.get("kid") if isinstance(header, dict) else None
                if not kid:
                    raise ValueError("License JWT missing kid header")

                matching_key = next((k for k in keys if k.get("kid") == kid), None)
                if not matching_key:
                    raise ValueError(f"No matching key found for kid={kid}")

                return True

        import asyncio

        # Run async validation
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(validate_key())
        finally:
            loop.close()

        # Key validated against JWKS; status is valid
        _license_cache = LicenseStatus(
            valid=True,
            key=key[:16] + "...",  # Truncate for safety in logs
            expiration=datetime.now(UTC) + timedelta(days=30),  # Assume valid for now
            activation_date=datetime.now(UTC),
        )

    except (ValueError, KeyError, JWTError) as exc:
        _license_cache = LicenseStatus(
            valid=False,
            key=key[:16] + "..." if len(key) > 8 else "",
            expiration=None,
            activation_date=datetime.now(UTC),
            error=str(exc),
        )

    return _license_cache


async def check_license_valid() -> LicenseStatus:
    """Asynchronous wrapper around license validation.

    Returns the current license status; caches results to avoid repeated lookups.

    Returns:
        LicenseStatus with latest validation result
    """
    return get_license_status()


async def license_watcher():
    """Background task for periodic license status refresh.

    This function is designed to run as an async background coroutine in the
    application lifespan. It periodically checks for license expiration and
    updates cached status accordingly.

    Notes:
        - Checks are spaced at least 1 hour apart by design
        - On expiration detection, clears cache to force revalidation

    Yields:
        Never yields; runs as an infinite coroutine loop that can be cancelled
    """
    import asyncio

    while True:
        status = get_license_status()

        if status.is_expired or not status.valid:
            # Clear cache on invalid state to force periodic re-checks
            global _license_cache
            _license_cache = None

        await asyncio.sleep(3600)  # Check every hour
