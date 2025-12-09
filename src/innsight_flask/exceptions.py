"""Common exception classes for the innsight application."""


class InnsightError(Exception):
    """Base exception for all innsight-related errors."""
    pass


class ConfigurationError(InnsightError):
    """Raised when there's an issue with application configuration."""
    pass


class NetworkError(InnsightError):
    """Raised when there's a network-related error."""
    pass


class APIError(InnsightError):
    """Raised when an external API returns an error."""
    
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class ParseError(InnsightError):
    """Raised when parsing fails due to missing required information."""
    pass


class DaysOutOfRangeError(ParseError):
    """Raised when extracted days exceed the valid range."""
    pass


class ParseConflictError(ParseError):
    """Raised when there are conflicting specifications in the same text."""
    pass


class GeocodeError(InnsightError):
    """Raised when geocoding fails."""
    pass


class IsochroneError(InnsightError):
    """Raised when isochrone request fails and no cache is available."""
    pass


class TierError(InnsightError):
    """Raised during tier assignment process."""
    pass


class NoAccommodationError(InnsightError):
    """Raised when no accommodations match the specified criteria."""
    pass


class ServiceUnavailableError(InnsightError):
    """Raised when external dependencies are not available."""
    pass