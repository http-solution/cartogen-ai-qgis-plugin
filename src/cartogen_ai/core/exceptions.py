# -*- coding: utf-8 -*-
"""
Core Exception Hierarchy for Cartogen AI.

Establishes a standardized exception hierarchy for spatial operations,
API provider failures, validation errors, and sandbox violations.
"""


class CartogenError(Exception):
    """Base exception for all Cartogen AI operational errors."""

    def __init__(self, message: str, user_message: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.user_message = user_message or message
        self.details = details or {}

    def to_dict(self) -> dict:
        """Returns a standardized dictionary for tool return envelopes."""
        res = {"error": self.user_message}
        if self.details:
            res["details"] = self.details
        return res


class ApiError(CartogenError):
    """Raised when external LLM providers or remote spatial APIs return unrecoverable errors."""

    def __init__(self, message: str, provider: str = None, status_code: int = None, user_message: str = None):
        details = {}
        if provider:
            details["provider"] = provider
        if status_code is not None:
            details["status_code"] = status_code
        super().__init__(message, user_message=user_message or f"API Error: {message}", details=details)
        self.provider = provider
        self.status_code = status_code


class SpatialValidationError(CartogenError):
    """Raised when layer geometry, CRS, fields, or parameters fail spatial validation."""

    def __init__(self, message: str, layer_name: str = None, field_name: str = None, user_message: str = None):
        details = {}
        if layer_name:
            details["layer_name"] = layer_name
        if field_name:
            details["field_name"] = field_name
        super().__init__(message, user_message=user_message or f"Spatial Validation Error: {message}", details=details)
        self.layer_name = layer_name
        self.field_name = field_name


class SecuritySandboxError(CartogenError):
    """Raised when user-supplied or LLM-generated code violates AST or security sandbox boundaries."""

    def __init__(self, message: str, blocked_ident: str = None):
        details = {"blocked_identifier": blocked_ident} if blocked_ident else {}
        super().__init__(
            message,
            user_message=f"Script rejected for safety: {message}",
            details=details,
        )
        self.blocked_ident = blocked_ident


class TaskExecutionError(CartogenError):
    """Raised when a background spatial task or analysis workflow fails execution."""
    pass
