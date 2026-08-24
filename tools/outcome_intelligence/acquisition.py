"""
MarketHunter

tools/outcome_intelligence/acquisition.py

Module:
Outcome Intelligence acquisition - read-only capture of raw
`GET /research/statistics` and `GET /research/statistics/setup-reasons`
responses, preserved as immutable, hash-verified local run artifacts.

Responsibilities:
- Fetch each endpoint exactly as returned - raw bytes, not a
  reparsed/renormalized payload - and fail closed on a non-200
  response or invalid JSON.
- Compute SHA-256 over the exact raw bytes preserved.
- Write each run as a new, uniquely-named directory containing the
  raw payload files plus one manifest.json recording provenance
  (base_url, endpoint, captured_at_utc, http_status, content_type,
  byte_count, sha256). Never overwrites an existing run.

Non-goals:
- No DB, API, worker, dashboard, or production/VPS mutation.
- No retry/backoff policy, no scheduling. The caller controls when
  and how often this module is invoked.
- No semantic interpretation of the payload - that is
  tools/outcome_intelligence/analysis.py's job.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

STATISTICS_ENDPOINT = "/research/statistics"
SETUP_REASONS_ENDPOINT = "/research/statistics/setup-reasons"

DEFAULT_ENDPOINTS: tuple[str, ...] = (
    STATISTICS_ENDPOINT,
    SETUP_REASONS_ENDPOINT,
)

_ENDPOINT_ARTIFACT_NAMES: dict[str, str] = {
    STATISTICS_ENDPOINT: "statistics.json",
    SETUP_REASONS_ENDPOINT: "setup_reasons.json",
}


class OutcomeIntelligenceAcquisitionError(Exception):
    """Base error for Outcome Intelligence acquisition failures."""


class OutcomeIntelligenceResponseError(OutcomeIntelligenceAcquisitionError):
    """The runtime returned a non-200 status or invalid JSON body."""


class OutcomeIntelligenceRunConflictError(OutcomeIntelligenceAcquisitionError):
    """A run artifact already exists at the target path - refusing to overwrite."""


def utcnow() -> datetime:
    """
    Default clock. Tests inject a fixed `now_utc` callable instead of
    calling this directly, so acquisition output stays deterministic
    under test.
    """

    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """
    One exact, immutable capture of one endpoint response.
    """

    endpoint: str
    base_url: str
    captured_at_utc: datetime
    http_status: int
    content_type: str
    raw_bytes: bytes
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    """
    Provenance record for one RawSnapshot as written to a run
    manifest - excludes the raw bytes themselves, which live in the
    sibling artifact file named by `artifact_filename`.
    """

    endpoint: str
    artifact_filename: str
    http_status: int
    content_type: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RunManifest:
    """
    One immutable Outcome Intelligence capture run: exactly the
    endpoints captured, when, from where, and the exact provenance of
    each resulting artifact.
    """

    run_id: str
    captured_at_utc: datetime
    base_url: str
    snapshots: tuple[SnapshotRecord, ...]


def fetch_raw_snapshot(
    client: httpx.Client,
    base_url: str,
    endpoint: str,
    now_utc: Callable[[], datetime] = utcnow,
) -> RawSnapshot:
    """
    Fetch one endpoint and preserve the exact raw response bytes.

    Fails closed (raises OutcomeIntelligenceResponseError) on any
    non-200 status or a body that does not parse as JSON. Never
    fabricates a snapshot from a partial/failed response.
    """

    url = base_url.rstrip("/") + endpoint
    captured_at_utc = now_utc()

    response = client.get(url)
    raw_bytes = response.content

    if response.status_code != 200:
        raise OutcomeIntelligenceResponseError(
            f"{endpoint}: non-200 status {response.status_code} from {url}"
        )

    try:
        json.loads(raw_bytes)
    except ValueError as exc:
        raise OutcomeIntelligenceResponseError(
            f"{endpoint}: response body is not valid JSON: {exc}"
        ) from exc

    return RawSnapshot(
        endpoint=endpoint,
        base_url=base_url,
        captured_at_utc=captured_at_utc,
        http_status=response.status_code,
        content_type=response.headers.get("content-type", ""),
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        byte_count=len(raw_bytes),
    )


def _artifact_filename(endpoint: str) -> str:
    filename = _ENDPOINT_ARTIFACT_NAMES.get(endpoint)

    if filename is None:
        raise OutcomeIntelligenceAcquisitionError(
            f"no known artifact filename for endpoint {endpoint!r}"
        )

    return filename


def _write_snapshot_artifact(
    snapshot: RawSnapshot,
    run_dir: Path,
) -> SnapshotRecord:
    filename = _artifact_filename(snapshot.endpoint)
    path = run_dir / filename

    if path.exists():
        raise OutcomeIntelligenceRunConflictError(
            f"artifact already exists, refusing to overwrite: {path}"
        )

    path.write_bytes(snapshot.raw_bytes)

    return SnapshotRecord(
        endpoint=snapshot.endpoint,
        artifact_filename=filename,
        http_status=snapshot.http_status,
        content_type=snapshot.content_type,
        byte_count=snapshot.byte_count,
        sha256=snapshot.sha256,
    )


def _manifest_to_dict(manifest: RunManifest) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "captured_at_utc": manifest.captured_at_utc.isoformat(),
        "base_url": manifest.base_url,
        "snapshots": [
            {
                "endpoint": record.endpoint,
                "artifact_filename": record.artifact_filename,
                "http_status": record.http_status,
                "content_type": record.content_type,
                "byte_count": record.byte_count,
                "sha256": record.sha256,
            }
            for record in manifest.snapshots
        ],
    }


def manifest_from_dict(payload: dict[str, object]) -> RunManifest:
    return RunManifest(
        run_id=str(payload["run_id"]),
        captured_at_utc=datetime.fromisoformat(
            str(payload["captured_at_utc"])
        ),
        base_url=str(payload["base_url"]),
        snapshots=tuple(
            SnapshotRecord(
                endpoint=str(item["endpoint"]),
                artifact_filename=str(item["artifact_filename"]),
                http_status=int(item["http_status"]),
                content_type=str(item["content_type"]),
                byte_count=int(item["byte_count"]),
                sha256=str(item["sha256"]),
            )
            for item in payload["snapshots"]
        ),
    )


def capture_outcome_intelligence_run(
    base_url: str,
    output_dir: Path,
    client: httpx.Client,
    now_utc: Callable[[], datetime] = utcnow,
    endpoints: tuple[str, ...] = DEFAULT_ENDPOINTS,
) -> RunManifest:
    """
    Capture one full Outcome Intelligence run: fetch every endpoint in
    `endpoints`, preserve each as a raw artifact under a new run
    directory, and write one manifest.json recording exact
    provenance.

    Fails closed and writes nothing if any endpoint fetch fails - a
    run is either captured completely or not written at all, so a
    partial/corrupt run can never be mistaken for a complete one.
    """

    run_started_at = now_utc()
    run_id = run_started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / "runs" / run_id

    if run_dir.exists():
        raise OutcomeIntelligenceRunConflictError(
            f"run directory already exists, refusing to overwrite: {run_dir}"
        )

    snapshots = [
        fetch_raw_snapshot(
            client=client,
            base_url=base_url,
            endpoint=endpoint,
            now_utc=now_utc,
        )
        for endpoint in endpoints
    ]

    run_dir.mkdir(parents=True)

    records = tuple(
        _write_snapshot_artifact(snapshot=snapshot, run_dir=run_dir)
        for snapshot in snapshots
    )

    manifest = RunManifest(
        run_id=run_id,
        captured_at_utc=run_started_at,
        base_url=base_url,
        snapshots=records,
    )

    (run_dir / "manifest.json").write_text(
        json.dumps(_manifest_to_dict(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return manifest


def list_run_manifests(output_dir: Path) -> list[RunManifest]:
    """
    Load every captured run manifest under `output_dir`, sorted
    ascending by captured_at_utc. Skips a run directory that has no
    manifest.json (an incomplete/failed capture never wrote one).
    """

    runs_dir = output_dir / "runs"

    if not runs_dir.exists():
        return []

    manifests: list[RunManifest] = []

    for run_dir in sorted(runs_dir.iterdir()):
        manifest_path = run_dir / "manifest.json"

        if not manifest_path.is_file():
            continue

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests.append(manifest_from_dict(payload))

    manifests.sort(key=lambda manifest: manifest.captured_at_utc)

    return manifests


def load_run_payload(
    output_dir: Path,
    manifest: RunManifest,
    endpoint: str,
) -> dict[str, object]:
    """
    Load and parse the exact preserved raw JSON body for one endpoint
    of one run.
    """

    record = next(
        (
            record
            for record in manifest.snapshots
            if record.endpoint == endpoint
        ),
        None,
    )

    if record is None:
        raise OutcomeIntelligenceAcquisitionError(
            f"run {manifest.run_id!r} has no captured snapshot for "
            f"endpoint {endpoint!r}"
        )

    artifact_path = (
        output_dir / "runs" / manifest.run_id / record.artifact_filename
    )
    raw_bytes = artifact_path.read_bytes()

    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    if actual_sha256 != record.sha256:
        raise OutcomeIntelligenceAcquisitionError(
            f"run {manifest.run_id!r} artifact {artifact_path} hash "
            f"mismatch: manifest says {record.sha256}, file is "
            f"{actual_sha256}"
        )

    return json.loads(raw_bytes)
