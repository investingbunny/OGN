# -*- coding: utf-8 -*-
"""
Parquet Cleanup Utility
Removes duplicate rows from all processed parquet files.

The download script's merge already removes duplicates, and repairs data
written by earlier versions on its next run, so this is only an optional
check. It applies the merge's own rules (loaded from the download script), so
rows that merely share a date and symbol, such as a stock's EQ and bond series
or several Market Activity lines, are never collapsed.

Uses parallel processing for speed — each file is independent.

Usage:
    python parquet_cleanup.py
"""

import importlib.util
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

HERE = Path(__file__).resolve().parent
# Fixed data folder (must match OGN v2.0-download.py).
DATA_ROOT = Path(r"C:\OGN-OneDrive\OneDrive\Github projects\OGN") / "MarketData_Parquet"
MAX_WORKERS = 8
# Raw-file prefix of each category folder (see the Data Categories table in README.md).
CATEGORY_PREFIXES = {
    'Equity': 'cm', 'Derivatives': 'fo', 'Indices': 'idx', 'ShortSelling': 'ss',
    'Volatility': 'vol', 'MarketActivity': 'ma', 'PriceBand': 'pb', 'PERatio': 'pe',
    'CorporateBonds': 'cb', 'DeliveryPositions': 'del', 'WDM': 'wdm',
}


def _load_merge_rules():
    spec = importlib.util.spec_from_file_location('ogn_download', HERE / 'OGN v2.0-download.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NSEMarketDataDownloader


MERGE_RULES = _load_merge_rules()


def _process_file(f: Path, raw_prefix):
    """Check a single parquet file for duplicates, rewrite if needed.
    Returns (removed_count, error_msg_or_None).
    """
    try:
        df = pd.read_parquet(f, engine='pyarrow')
        before = len(df)

        df = MERGE_RULES._deduplicate(df, raw_prefix)
        after = len(df)

        if before != after:
            df = df.sort_values('Date')
            df.to_parquet(f, engine='pyarrow', compression='zstd', index=False)
            return (before - after, None)
        return (0, None)
    except Exception as e:
        return (0, f"{f.name}: {e}")


def cleanup_duplicates():
    t0 = time.time()

    # Collect all parquet files across all Processed dirs
    all_files = []
    for processed_dir in sorted(DATA_ROOT.rglob("Processed")):
        all_files.extend(sorted(processed_dir.glob("*.parquet")))

    if not all_files:
        print("No processed parquet files found.")
        return

    print(f"Scanning {len(all_files)} files with {MAX_WORKERS} threads...")

    total_removed = 0
    files_cleaned = 0
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_file, f, CATEGORY_PREFIXES.get(f.parent.parent.name)): f
                   for f in all_files}

        done = 0
        last_report = time.time()
        for future in as_completed(futures):
            f = futures[future]
            done += 1
            removed, err = future.result()
            if err:
                errors.append(err)
            if removed > 0:
                total_removed += removed
                files_cleaned += 1
                print(f"  {f.parent.parent.name}/{f.name}: removed {removed} duplicates")

            now = time.time()
            if now - last_report >= 5 or done == len(all_files):
                pct = done * 100 // len(all_files)
                print(f"  Progress: {done}/{len(all_files)} ({pct}%) — "
                      f"{files_cleaned} cleaned, {total_removed} removed, {now - t0:.1f}s",
                      flush=True)
                last_report = now

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s. Scanned {len(all_files)} files, "
          f"cleaned {files_cleaned}, removed {total_removed} duplicate rows.")


if __name__ == '__main__':
    cleanup_duplicates()
