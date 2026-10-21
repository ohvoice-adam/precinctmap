from datetime import date

from precinctmap.ingest.detect import detect_adapter
from precinctmap.ingest.identify import identify
from precinctmap.ingest.model import NormalizationLog
from precinctmap.ingest.normalize import clean_text, precinct_name, repair_mojibake, slug
from precinctmap.ingest.votefor import infer_vote_for
from precinctmap.io.xlsx import read_single_sheet
from tests.fixtures.builders import sheet_2024, sheet_2025, sheet_2025_primary


def _parsed(sheet, tmp_path):
    grid = read_single_sheet(sheet.write(tmp_path / "f.xlsx"))
    return detect_adapter(grid, "f.xlsx").parse(grid)


def test_identify_from_filename_year_and_content(tmp_path):
    p = _parsed(sheet_2025(), tmp_path)
    ident = identify("2025-General-Election_EXPORT_Official.xlsx", p)
    assert ident.problems == []
    assert ident.election_date == date(2025, 11, 4)
    assert ident.election_id == "franklin-2025-11-04-general"
    assert ident.certified is True
    assert ident.label == "November 4, 2025 general"


def test_identify_primary_from_content_when_name_has_no_type(tmp_path):
    p = _parsed(sheet_2024(primary=True), tmp_path)
    ident = identify("2024-Election-Results-CSV.xlsx", p)
    assert ident.election_id == "franklin-2024-03-19-primary"
    assert ident.certified is False


def test_identify_blocks_without_year_until_overridden(tmp_path):
    p = _parsed(sheet_2024(), tmp_path)
    blocked = identify("Official-Results-by-Precinct.xlsx", p)
    assert blocked.election_id is None
    assert "pass --election-date" in blocked.problems[0]
    ok = identify("Official-Results-by-Precinct.xlsx", p, override_date=date(2024, 11, 5))
    assert ok.election_id == "franklin-2024-11-05-general"


def test_identify_blocks_type_conflict(tmp_path):
    p = _parsed(sheet_2025_primary(), tmp_path)  # content says primary
    ident = identify("2025-General-Election.xlsx", p)
    assert ident.election_id is None
    assert any("conflicts with content" in m for m in ident.problems)


def test_identify_blocks_date_that_calendar_lists_as_other_type(tmp_path):
    p = _parsed(sheet_2024(), tmp_path)
    ident = identify("results.xlsx", p, override_date=date(2024, 3, 19))
    assert ident.election_id is None
    assert any("calendar lists" in m for m in ident.problems)


def test_vote_for_inferred_from_over_under(tmp_path):
    vf = infer_vote_for(_parsed(sheet_2025(), tmp_path))
    assert vf[0].value == 1 and vf[0].source == "inferred"
    assert vf[1].value == 1 and "3/3" in vf[1].evidence


def test_vote_for_uses_party_ballots_in_primaries(tmp_path):
    vf = infer_vote_for(_parsed(sheet_2025_primary(), tmp_path))
    assert vf[0].value == 1


def test_vote_for_unknown_without_over_under(tmp_path):
    vf = infer_vote_for(_parsed(sheet_2024(), tmp_path))
    assert {v.source for v in vf.values()} == {"unknown"}


def test_normalize_text_and_names_are_logged():
    log = NormalizationLog()
    assert clean_text("﻿ShawnÂ\xa0Dingus  ", "x", log) == "Shawn Dingus"
    assert [e.kind for e in log.entries] == ["bom", "mojibake", "nbsp", "whitespace"]
    assert precinct_name("BEXLEY 1-A", "y", log) == "BEXLEY 01-A"
    assert precinct_name("COLUMBUS 01-A", "y", log) == "COLUMBUS 01-A"
    assert precinct_name("BLENDON-A", "y", log) == "BLENDON-A"
    assert sum(e.kind == "ward_padding" for e in log.entries) == 1


def test_repair_mojibake_leaves_clean_text_alone():
    assert repair_mojibake("Tiara Ross") == "Tiara Ross"
    assert repair_mojibake("Ã©") == "é"


def test_slug_is_stable_and_ascii():
    assert slug("For U.S. Senator (UTE 1-3-29)") == "for-u-s-senator-ute-1-3-29"


def test_corrections_fix_display_names_and_log_typos(tmp_path):
    from tests.fixtures.builders import Col

    sheet = sheet_2024(primary=True)
    rep = "Dem For State Representative (2nd Distict)"
    sheet.cols[-2].h1 = sheet.cols[-1].h1 = rep
    sheet.cols.append(
        Col(
            "Rep For Member of State Central Committee  Man (3rd District)",
            "Rep",
            "Frank J. Reed  Jr.",
            [1, 2, 3, 0],
        )
    )
    p = _parsed(sheet, tmp_path)
    names = [c.name_display for c in p.contests]
    assert "For State Representative (2nd District)" in names
    assert "For Member of State Central Committee, Man (3rd District)" in names
    assert p.contests[-1].choices[0].name_display == "Frank J. Reed, Jr."
    assert p.contests[-1].choices[0].name_raw == "Frank J. Reed  Jr."  # raw kept
    assert sum(n.kind == "typo" for n in p.normalizations.entries) == 3


def test_jurisdiction_parsing_stops_at_contest_words():
    from precinctmap.ingest.fcboe_common import jurisdiction

    assert jurisdiction("Proposed Income Tax Pickerington Local School District") == (
        "Pickerington Local School District"
    )
    assert jurisdiction(
        "For Member of Board of Education Groveport Madison Local School District"
    ) == ("Groveport Madison Local School District")
    assert jurisdiction("For Member of Council City of Dublin Council Ward 1") == "City of Dublin"
    assert jurisdiction("#12 Proposed Municipal Income Tax Village of Lockbourne") == (
        "Village of Lockbourne"
    )
    assert jurisdiction("For U.S. Senator") is None
