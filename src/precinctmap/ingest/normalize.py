"""Text and precinct-name normalization. Every change is recorded in a NormalizationLog."""

import re

from precinctmap.ingest.model import NormalizationLog

_MOJIBAKE_MARKERS = ("Â", "Ã", "â€")
_WARD_UNPADDED = re.compile(r"(?<= )(\d)(?=-[A-Z]{1,2}$)")


def repair_mojibake(text: str) -> str:
    """Undo UTF-8 text that was decoded as cp1252 (e.g. 'GeraldÂ\\xa0Dixon').

    Returns `text` unchanged when it has no mojibake markers or the round trip fails.
    """
    if not any(m in text for m in _MOJIBAKE_MARKERS):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def clean_text(text: str, location: str, log: NormalizationLog) -> str:
    """Strip BOMs, repair mojibake, turn NBSP into spaces, collapse whitespace, trim.

    Logs one entry per kind of change so the review report can count them.
    """
    out = text
    for kind, fn in (
        ("bom", lambda s: s.replace("﻿", "")),
        ("mojibake", repair_mojibake),
        ("nbsp", lambda s: s.replace("\xa0", " ")),
        ("whitespace", lambda s: re.sub(r"\s+", " ", s).strip()),
    ):
        changed = fn(out)
        if changed != out:
            log.add(kind, location, out, changed)
            out = changed
    return out


def strip_trailing_dash(text: str, location: str, log: NormalizationLog) -> str:
    """Drop the export's dangling ' -' suffix ('For U.S. Senator -' -> 'For U.S. Senator')."""
    if text.endswith(" -"):
        out = text[:-2].rstrip()
        log.add("trailing_dash", location, text, out)
        return out
    return text


def precinct_name(raw: str, location: str, log: NormalizationLog) -> str:
    """Normalize a precinct name to the boundary-file form.

    Results drop the ward's leading zero outside Columbus ('BEXLEY 1-A'); the BOE precinct
    shapefile pads it ('BEXLEY 01-A'). Names are the join key; codes are row ordinals.
    """
    name = clean_text(raw, location, log).upper()
    padded = _WARD_UNPADDED.sub(r"0\1", name)
    if padded != name:
        log.add("ward_padding", location, name, padded)
    return padded


def slug(text: str) -> str:
    """Lowercase ASCII slug for stable ids.

    'For U.S. Senator (UTE 1-3-29)' -> 'for-u-s-senator-ute-1-3-29'.
    """
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not s:
        raise ValueError(f"cannot build an id from {text!r}")
    return s
