from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Iterable

from .dashboard_metrics import (
    DashboardSnapshot,
    fold_text,
    parse_measurement_workbook,
    sha256_file,
)
from .dashboard_storage import RouteDashboardStorage


def should_ignore(path: Path) -> bool:
    return "tuan tra" in fold_text(path.name)


def infer_month_and_region(path: Path) -> tuple[str, str]:
    full_text = str(path)
    years = re.findall(r"(?:19|20)\d{2}", full_text)
    month_matches = re.findall(r"(?:^|[\\/_ .-])T(1[0-2]|0?[1-9])(?:[\\/_ .-]|$)", full_text, re.IGNORECASE)
    if not years or not month_matches:
        raise ValueError(f"Cannot infer year/month from {path}")
    year = int(years[-1])
    month = int(month_matches[-1])

    name = fold_text(path.name)
    if "dbb" in name:
        region = "DBB"
    elif "tbb" in name:
        region = "TBB"
    elif re.search(r"(^|[^a-z])b[ -]?n([^a-z]|$)", name) or name.startswith("bn"):
        region = "B-N"
    else:
        raise ValueError(f"Cannot infer region from {path.name}")
    return f"{year:04d}-{month:02d}", region


def collect_snapshots(root: Path) -> tuple[list[DashboardSnapshot], dict[str, object]]:
    candidates = sorted(root.rglob("*.xlsx"))
    ignored = [path for path in candidates if should_ignore(path)]
    included = [path for path in candidates if not should_ignore(path)]
    seen_hashes: set[str] = set()
    duplicates: list[str] = []
    errors: list[str] = []
    snapshots: list[DashboardSnapshot] = []
    imported_files = 0

    for path in included:
        digest = sha256_file(path)
        if digest in seen_hashes:
            duplicates.append(str(path))
            continue
        seen_hashes.add(digest)
        try:
            month, region = infer_month_and_region(path)
            parsed = parse_measurement_workbook(
                path,
                region=region,
                measurement_month=month,
            )
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
        snapshots.extend(parsed)
        imported_files += 1

    report: dict[str, object] = {
        "candidate_files": len(candidates),
        "imported_files": imported_files,
        "ignored_patrol_files": [str(path) for path in ignored],
        "duplicate_files": duplicates,
        "errors": errors,
        "snapshot_count": len(snapshots),
    }
    return snapshots, report


def _write_json(path: Path, snapshots: Iterable[DashboardSnapshot], report: dict[str, object]) -> None:
    payload = {
        "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "import_report": report,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import monthly KQĐ Excel workbooks into the route dashboard."
    )
    parser.add_argument("input_root", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--upload-supabase", action="store_true")
    args = parser.parse_args()

    snapshots, report = collect_snapshots(args.input_root.resolve())
    if args.output_json:
        _write_json(args.output_json.resolve(), snapshots, report)
    if args.upload_supabase:
        report["uploaded_snapshots"] = RouteDashboardStorage().upsert_snapshots(snapshots)

    # ASCII output keeps the CLI usable in Windows consoles that still use cp1252.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
