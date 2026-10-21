"""Admin ingest: the same staging -> review -> commit flow as the CLI.

Every route requires the admin login (app.api.auth).
"""

import json
import re
import shutil
import uuid
from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.auth import require_admin
from app.api.deps import AppSettings, Db
from app.api.models import Committed, Staged
from precinctmap.aggregate.run import aggregate
from precinctmap.catalog.calendar import ElectionType
from precinctmap.ingest.commit import commit_staging
from precinctmap.ingest.errors import StagingError
from precinctmap.ingest.report_text import render
from precinctmap.ingest.staging import stage_file, staging_dir

router = APIRouter(prefix="/api/ingest", tags=["admin"], dependencies=[Depends(require_admin)])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _staged(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "staging_id": report["staging_id"],
        "status": report["status"],
        "report": report,
        "report_text": render(report),
    }


@router.post("", response_model=Staged)
def upload(
    db: Db,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="Results spreadsheet (.xlsx)")],
    election_date: Annotated[date | None, Form()] = None,
    election_type: Annotated[ElectionType | None, Form()] = None,
    certified: Annotated[bool | None, Form()] = None,
    reprocess: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """Save the upload and stage it. Nothing is committed here."""
    name = _SAFE.sub("_", file.filename or "upload.xlsx").strip("._") or "upload.xlsx"
    if not name.lower().endswith(".xlsx"):
        raise StagingError(f"{name}: only .xlsx results files are supported")
    folder = settings.data_dir / "uploads" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    path = folder / name
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise StagingError(f"{name}: larger than {MAX_UPLOAD_BYTES // 2**20} MB")
    staged = stage_file(db, settings, path, election_date, election_type, certified, reprocess)
    return _staged(staged.report)


@router.get("/{staging_id}", response_model=Staged)
def get_report(settings: AppSettings, staging_id: str) -> dict[str, Any]:
    path = staging_dir(settings, staging_id) / "report.json"
    if not re.fullmatch(r"stg-[0-9a-f]{12}", staging_id) or not path.exists():
        raise StagingError(f"no staging batch {staging_id}")
    return _staged(json.loads(path.read_text()))


@router.post("/{staging_id}/commit", response_model=Committed)
def commit(db: Db, settings: AppSettings, staging_id: str, replace: bool = False) -> dict[str, Any]:
    """Commit a reviewed batch, then rebuild and reconcile that election's map results.

    `replace=true` is required when the batch would replace the election's loaded file.
    """
    result = commit_staging(db, settings, staging_id, allow_replace=replace)
    summaries = aggregate(db, [result.election_id]) if result.action == "commit" else []
    return {
        "action": result.action,
        "election_id": result.election_id,
        "detail": result.detail,
        "reconciliation": [asdict(s) for s in summaries],
    }
