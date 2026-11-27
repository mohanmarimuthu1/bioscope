"""Download the PhysioNet EEGMMI files BioScope needs into data/raw/.

WHAT:  Reference set S001–S050 × {R01, R02} (100 files) + demo subject S060 × R01–R14
       (14 files) = 114 EDF files. With --holdout: only the external-test set
       S061–S109 × {R01, R02} (98 files).
WHY:   Reproducible, offline-after-first-run data for the reference, ML and demo.
CAVEATS: Idempotent — existing complete files are skipped. Downloads go to a .part
       file and are renamed only on success, so an interrupted run never leaves a
       truncated .edf that looks complete. Network errors retry 3× with backoff.

Usage:  python scripts/download_data.py              # reference + demo
        python scripts/download_data.py --holdout    # S061–S109 R01/R02
"""
import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

MAX_RETRIES = 3
BACKOFF_S = 2.0
TIMEOUT_S = 60


def wanted_files(holdout: bool = False) -> list[tuple[str, str]]:
    """Return (subject, run) pairs: reference R01/R02 + demo runs, or the holdout R01/R02."""
    if holdout:
        return [(s, r) for s in config.HOLDOUT_SUBJECTS for r in config.REFERENCE_RUNS.values()]
    ref = [(s, r) for s in config.REFERENCE_SUBJECTS for r in config.REFERENCE_RUNS.values()]
    demo = [(config.DEMO_SUBJECT, r) for r in config.DEMO_RUNS]
    return ref + demo


def fetch(subject: str, run: str, dest_dir: Path) -> str:
    """Download one EDF. Returns 'skipped', 'downloaded' or 'failed'."""
    name = f"{subject}{run}.edf"
    dest = dest_dir / subject / name
    if dest.exists() and dest.stat().st_size > 0:
        return "skipped"
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{config.PHYSIONET_BASE_URL}/{subject}/{name}"
    part = dest.with_suffix(".edf.part")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bioscope-eeg-downloader"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp, open(part, "wb") as fh:
                fh.write(resp.read())
            part.replace(dest)
            return "downloaded"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  {name}: attempt {attempt}/{MAX_RETRIES} failed ({exc})")
            if part.exists():
                part.unlink()
            time.sleep(BACKOFF_S * attempt)
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--holdout", action="store_true", help="fetch S061–S109 R01/R02 only")
    args = parser.parse_args()
    counts = {"skipped": 0, "downloaded": 0, "failed": 0}
    files = wanted_files(args.holdout)
    print(f"Fetching {len(files)} files into {config.DATA_RAW}")
    for i, (subject, run) in enumerate(files, 1):
        status = fetch(subject, run, config.DATA_RAW)
        counts[status] += 1
        if status != "skipped":
            print(f"[{i:3d}/{len(files)}] {subject}{run}.edf {status}")
    present = sum((config.DATA_RAW / s / f"{s}{r}.edf").exists() for s, r in files)
    print(f"Done: {counts} | wanted files present: {present}/{len(files)}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
