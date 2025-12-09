"""Utility functions for the innsight application."""

from typing import List


def combine_tokens(tokens: List[str]) -> str:
    """Safely combine tokens into a single string."""
    try:
        return ''.join(str(token) for token in tokens if token is not None)
    except (TypeError, AttributeError):
        return ''