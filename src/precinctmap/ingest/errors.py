"""Ingest errors. Each names the file problem precisely; none is ever swallowed."""


class IngestError(Exception):
    """Base class for ingest failures."""


class UnknownLayoutError(IngestError):
    """No adapter recognizes the file. Write a new adapter from a real sample (rule 7)."""


class AmbiguousLayoutError(IngestError):
    """More than one adapter claims the file; detection rules must be tightened."""


class LayoutError(IngestError):
    """The file matched an adapter but violates that layout (bad cell, missing total row, ...)."""


class StagingError(IngestError):
    """A staging batch is missing, malformed, or not committable."""
