"""Reviewed corrections for source typos in display names. `name_raw` always keeps the source.

Each entry was confirmed against the samples (Phase 2 review, 2026-10-20). Add entries only
for typos seen in a real file; every application is logged as a 'typo' normalization.
"""

import re

from precinctmap.ingest.model import NormalizationLog

# (pattern, replacement, evidence)
CONTEST_FIXES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bDistict\b"),
        "District",
        "2024 primary '(2nd Distict)'; 2025 primary 'Road Distict'",
    ),
    (re.compile(r"\bInfrustructure\b"), "Infrastructure", "2025 general Columbus bond issue #5"),
    (re.compile(r"\b(\d+)Th\b"), r"\1th", "2024 primary '10Th District'"),
    (re.compile(r"\((\d+(?:st|nd|rd|th) District)$"), r"(\1)", "2024 primary '(9th District'"),
    (re.compile(r"\bEsc\b"), "ESC", "2025 general 'Licking Esc' vs 'Fairfield ESC'"),
    (re.compile(r"\bCommittee (Man|Woman)\b"), r"Committee, \1", "2024 primary lost commas"),
)

CHOICE_FIXES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^Frank J\. Reed Jr\.$"), "Frank J. Reed, Jr.", "2024 primary lost comma"),
    (re.compile(r"^YES$"), "Yes", "sentence case"),
    (re.compile(r"^NO$"), "No", "sentence case"),
)


def apply_fixes(
    text: str,
    fixes: tuple[tuple[re.Pattern[str], str, str], ...],
    location: str,
    log: NormalizationLog,
) -> str:
    out = text
    for pattern, replacement, _evidence in fixes:
        fixed = pattern.sub(replacement, out)
        if fixed != out:
            log.add("typo", location, out, fixed)
            out = fixed
    return out
