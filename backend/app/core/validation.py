"""Shared input validation utilities and FastAPI dependencies."""

from uuid import UUID

from fastapi import HTTPException


def validated_uuid(value: str, param_name: str) -> str:
    """Validate that *value* is a well-formed UUID, raise 400 otherwise."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}: must be a valid UUID",
        )
    return value
