class ScreenerError(Exception):
    """Base error for the screener."""


class ConfigError(ScreenerError):
    pass


class SourceNotReady(ScreenerError):
    """Official source partition is incomplete; do not score."""


class PointInTimeLeak(ScreenerError):
    """A row with available_date after as_of/cutoff was selected."""


class PublishBlocked(ScreenerError):
    """Run must not update latest_success."""


class MappingError(ScreenerError):
    pass


class HashMismatch(ScreenerError):
    pass
