# -*- coding: utf-8 -*-
"""
Parquet Cleanup Utility
Removes duplicate rows from all processed parquet files.

Run this once to clean up any duplicates that accumulated from
earlier merge logic. The main download script's merge now handles
dedup correctly, so this should only be needed as a one-time fix.

Uses parallel processing for speed — each file is independent.

Usage:
    python parquet_cleanup.py
"""

import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

DATA_ROOT = Path("MarketData_Parquet")
MAX_WORKERS = 8


def _process_file(f: Path):
    """Check a single parquet file for duplicates, rewrite if needed.
    Returns (removed_count, error_msg_or_None).
    """
    try:
        df = pd.read_parquet(f, engine='pyarrow')
        before = len(df)

        dedup_cols = ['Date']
        for key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
            if key in df.columns:
                dedup_cols.append(key)

        df = df.drop_duplicates(subset=dedup_cols, keep='last')
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
        futures = {pool.submit(_process_file, f): f for f in all_files}

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
