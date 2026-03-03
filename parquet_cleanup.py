# -*- coding: utf-8 -*-
"""
Parquet Cleanup Utility
Removes duplicate rows from all processed parquet files.

Run this once to clean up any duplicates that accumulated from
earlier merge logic. The main download script's merge now handles
dedup correctly, so this should only be needed as a one-time fix.

Usage:
    python parquet_cleanup.py
"""

import pandas as pd
from pathlib import Path

DATA_ROOT = Path("MarketData_Parquet")


def cleanup_duplicates():
    total_removed = 0
    files_cleaned = 0
    files_scanned = 0

    for processed_dir in sorted(DATA_ROOT.rglob("Processed")):
        category = processed_dir.parent.name
        print(f"\n--- {category} ---")

        for f in sorted(processed_dir.glob("*.parquet")):
            files_scanned += 1
            try:
                df = pd.read_parquet(f, engine='pyarrow')
                before = len(df)

                dedup_cols = ['Date']
                for key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
                    if key in df.columns:
                        dedup_cols.append(key)

                df = df.drop_duplicates(subset=dedup_cols, keep='last').sort_values('Date')
                after = len(df)

                if before != after:
                    removed = before - after
                    df.to_parquet(f, engine='pyarrow', compression='zstd', index=False)
                    print(f"  {f.name}: {before} -> {after} rows (removed {removed})")
                    total_removed += removed
                    files_cleaned += 1
            except Exception as e:
                print(f"  Error: {f.name}: {e}")

    print(f"\nDone. Scanned {files_scanned} files, "
          f"cleaned {files_cleaned}, removed {total_removed} duplicate rows.")


if __name__ == '__main__':
    cleanup_duplicates()
