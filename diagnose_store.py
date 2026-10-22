# -*- coding: utf-8 -*-
"""
Read-only health and cost report for the MarketData_Parquet store.

Run it on the machine that runs OGN v2.0-download.py:

    python diagnose_store.py                 # summary of every category
    python diagnose_store.py --deep 10       # also inspect the 10 largest files per category
    python diagnose_store.py --deep 10 --timing

It never writes inside the data folder. Files that OneDrive keeps online-only are
counted but not opened, because opening one downloads it (use
--include-online-only to inspect them anyway). --timing copies one file to a
temporary folder outside OneDrive and times a merge-style rewrite there.
The report is printed and saved as JSON in the temporary folder.
"""

import argparse
import datetime as dt
import importlib.util
import json
import os
import platform
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
# Folder name -> raw-file prefix (see the Data Categories table in README.md).
CATEGORIES = {
    'Equity': 'cm', 'Derivatives': 'fo', 'Indices': 'idx', 'ShortSelling': 'ss',
    'Volatility': 'vol', 'MarketActivity': 'ma', 'PriceBand': 'pb', 'PERatio': 'pe',
    'CorporateBonds': 'cb', 'DeliveryPositions': 'del', 'WDM': 'wdm',
}
# Windows attributes OneDrive sets on cloud placeholders and pinned files.
RECALL_ON_DATA_ACCESS = 0x400000
RECALL_ON_OPEN = 0x40000
OFFLINE = 0x1000
PINNED = 0x80000
DATE_IN_NAME = re.compile(
    r'\d{1,2}[-\s/](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s/]\d{2,4}'
    r'|\d{4}-\d{2}-\d{2}|\d{8}', re.IGNORECASE)
NULL_TEXT = {'nan', 'none', '', 'nat', '<na>', 'null'}


def load_downloader():
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location('ogn_download', HERE / 'OGN v2.0-download.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan(folder: Path):
    """DirEntry list (stat comes from the directory listing, so nothing is downloaded)."""
    if not folder.is_dir():
        return []
    with os.scandir(folder) as entries:
        return [e for e in entries if e.is_file()]


def online_only(entry) -> bool:
    attrs = getattr(entry.stat(), 'st_file_attributes', 0)
    return bool(attrs & (RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE))


def mb(n_bytes: float) -> float:
    return round(n_bytes / (1024 * 1024), 1)


def inspect_file(path: Path, prefix: str, dedup_keys) -> dict:
    """Rows, width, dates, duplicates and suspicious columns of one processed file."""
    meta = pq.read_metadata(path)
    info = {'file': path.name, 'mb': mb(path.stat().st_size), 'rows': meta.num_rows,
            'columns': meta.num_columns, 'row_groups': meta.num_row_groups,
            'footer_kb': round(meta.serialized_size / 1024, 1)}
    table = pq.read_table(path)
    names = table.column_names
    info['date_named_columns'] = sum(bool(DATE_IN_NAME.search(n)) for n in names)
    sparse = 0
    for name in names:
        column = table[name]
        empty = column.null_count
        if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
            lowered = pc.utf8_lower(pc.utf8_trim_whitespace(column.drop_null()))
            empty += pc.sum(pc.is_in(lowered, value_set=pa.array(sorted(NULL_TEXT), type=column.type))).as_py() or 0
        if table.num_rows and empty >= 0.99 * table.num_rows:
            sparse += 1
    info['columns_99pct_empty'] = sparse
    if 'Date' in names and table.num_rows:
        per_date = pc.value_counts(table['Date'])
        counts = sorted(per_date.field('counts').to_pylist())
        info['distinct_dates'] = len(counts)
        info['rows_per_date_median'] = statistics.median(counts)
        info['rows_per_date_max'] = counts[-1]
        dates = table['Date'].drop_null()
        if len(dates):
            info['first_date'] = str(pc.min(dates).as_py())
            info['last_date'] = str(pc.max(dates).as_py())
    try:
        keys = dedup_keys(table.schema.empty_table().to_pandas(), prefix)
        info['dedup_keys'] = keys if len(keys) <= 8 else f'all {len(keys)} columns'
        if len(keys) <= 40:
            groups = table.select(keys).group_by(keys).aggregate([([], 'count_all')])
            info['duplicate_rows'] = int(pc.sum(pc.subtract(groups['count_all'], 1)).as_py() or 0)
        else:
            info['duplicate_rows'] = int(table.to_pandas().duplicated(keep='last').sum())
    except Exception as e:
        info['duplicate_rows'] = f'not checked ({type(e).__name__}: {e})'
    return info


def time_rewrite(path: Path, module) -> dict:
    """Times the current pandas rewrite vs a pyarrow rewrite of one file, outside OneDrive."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / path.name
        shutil.copy2(path, copy)
        out = {'file': f'{path.parent.parent.name}/{path.name}', 'mb': mb(copy.stat().st_size)}
        t0 = time.perf_counter()
        frame = pd.read_parquet(copy, engine='pyarrow')
        frame = module.NSEMarketDataDownloader._restore_date_columns(frame)
        out['pandas_read_s'] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()
        for col in frame.columns:
            if frame[col].dtype == object and col not in module.DATE_COLUMNS:
                converted = pd.to_numeric(frame[col], errors='coerce')
                if converted.notna().sum() >= frame[col].notna().sum() * 0.5:
                    frame[col] = converted
                else:
                    frame[col] = frame[col].astype(str)
        out['pandas_coerce_s'] = round(time.perf_counter() - t0, 2)
        t0 = time.perf_counter()
        frame.to_parquet(Path(tmp) / 'pandas.parquet', engine='pyarrow', compression='zstd', index=False)
        out['pandas_write_s'] = round(time.perf_counter() - t0, 2)
        del frame
        t0 = time.perf_counter()
        table = pq.read_table(copy)
        pq.write_table(table, Path(tmp) / 'arrow.parquet', compression='zstd')
        out['arrow_read_write_s'] = round(time.perf_counter() - t0, 2)
        out['pandas_total_s'] = round(out['pandas_read_s'] + out['pandas_coerce_s'] + out['pandas_write_s'], 2)
    return out


def main():
    parser = argparse.ArgumentParser(description='Read-only report on the MarketData_Parquet store.')
    parser.add_argument('--deep', type=int, default=0, metavar='N',
                        help='inspect the N largest processed files of each category')
    parser.add_argument('--timing', action='store_true',
                        help='time a merge-style rewrite of the largest files (in a temp folder)')
    parser.add_argument('--include-online-only', action='store_true',
                        help='also open files OneDrive keeps online-only (downloads them)')
    parser.add_argument('--root', type=Path, help='data folder to inspect (default: DATA_ROOT)')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

    module = load_downloader()
    root = args.root or module.DATA_ROOT
    dedup_keys = module.NSEMarketDataDownloader._dedup_keys
    report = {
        'generated': dt.datetime.now().isoformat(timespec='seconds'),
        'machine': platform.node(), 'python': platform.python_version(),
        'pandas': pd.__version__, 'pyarrow': pa.__version__,
        'pandas_text_dtype': str(pd.Series(['x']).dtype),
        'cpu_count': os.cpu_count(), 'data_root': str(root),
        'onedrive_folder': 'onedrive' in str(root).lower(), 'categories': {},
    }
    print(f"Data folder: {root}")
    print(f"Python {report['python']}, pandas {report['pandas']} (text dtype: {report['pandas_text_dtype']}), "
          f"pyarrow {report['pyarrow']}, {report['cpu_count']} logical CPUs")
    if not root.is_dir():
        print('Data folder not found.')
        return

    timing_candidates = []
    for folder, prefix in CATEGORIES.items():
        raw_dir, processed_dir = root / folder / 'Raw', root / folder / 'Processed'
        processed = [e for e in scan(processed_dir) if e.name.endswith('.parquet')]
        raw = scan(raw_dir)
        raw_days = [e for e in raw if re.fullmatch(rf'{prefix}_\d{{8}}\.parquet', e.name)]
        odd_raw = [e.name for e in raw if e.name.startswith(f'{prefix}_') and e.name.endswith('.parquet')
                   and not re.fullmatch(rf'{prefix}_\d{{8}}\.parquet', e.name)]
        stamp = raw_dir / f'.merged_{prefix}.txt'
        merged = set(stamp.read_text().split()) if stamp.exists() else set()
        sizes = sorted(processed, key=lambda e: e.stat().st_size, reverse=True)
        info = {
            'processed_files': len(processed),
            'processed_mb': mb(sum(e.stat().st_size for e in processed)),
            'processed_online_only': sum(online_only(e) for e in processed),
            'processed_pinned': sum(bool(getattr(e.stat(), 'st_file_attributes', 0) & PINNED) for e in processed),
            'largest': [(e.name, mb(e.stat().st_size)) for e in sizes[:5]],
            'raw_day_files': len(raw_days), 'raw_mb': mb(sum(e.stat().st_size for e in raw_days)),
            'raw_online_only': sum(online_only(e) for e in raw_days),
            'nodata_markers': sum(e.name.endswith('.nodata') for e in raw),
            'raw_files_not_yet_merged': sum(e.name not in merged for e in raw_days),
            'unexpected_raw_names': odd_raw[:20],
            'retry_files': len(scan(raw_dir / '.retry')),
            'tmp_files_in_processed': sum(e.name.endswith('.tmp') for e in scan(processed_dir)),
        }
        # What one daily merge rewrites: every processed file holding a symbol of the latest day.
        latest = max(raw_days, key=lambda e: e.name, default=None)
        if latest is not None and (args.include_online_only or not online_only(latest)):
            try:
                symbols = {str(s) for s in pq.read_table(latest.path, columns=['Symbol']).column('Symbol').to_pylist()}
                touched = [e for e in processed if e.name[:-len('.parquet')] in symbols]
                info['latest_raw_day'] = latest.name
                info['files_rewritten_per_day'] = len(touched)
                info['mb_rewritten_per_day'] = mb(sum(e.stat().st_size for e in touched))
                info['online_only_among_rewritten'] = sum(online_only(e) for e in touched)
            except Exception as e:
                info['files_rewritten_per_day'] = f'not checked ({type(e).__name__}: {e})'
        # Footer-only sample: are files wide (many columns) or long (many rows)?
        local = [e for e in processed if not online_only(e)]
        sample = sizes[:10] + local[::max(1, len(local) // 40)][:40]
        shapes = []
        for entry in sample:
            if online_only(entry) and not args.include_online_only:
                continue
            try:
                meta = pq.read_metadata(entry.path)
                shapes.append((meta.num_rows, meta.num_columns))
            except Exception:
                continue
        if shapes:
            info['sample_files'] = len(shapes)
            info['sample_rows_median'] = statistics.median(r for r, _ in shapes)
            info['sample_columns_median'] = statistics.median(c for _, c in shapes)
            info['sample_columns_max'] = max(c for _, c in shapes)
        info['catch_all_files'] = [(e.name, mb(e.stat().st_size)) for e in processed
                                   if e.name[:-len('.parquet')].strip().lower() in {'unknown', 'nan', 'none', ''}]
        if args.deep:
            inspected = []
            for entry in sizes[:args.deep]:
                if online_only(entry) and not args.include_online_only:
                    inspected.append({'file': entry.name, 'skipped': 'online-only'})
                    continue
                try:
                    inspected.append(inspect_file(Path(entry.path), prefix, dedup_keys))
                except Exception as e:
                    inspected.append({'file': entry.name, 'error': f'{type(e).__name__}: {e}'})
            info['deep'] = inspected
        if sizes and (args.include_online_only or not online_only(sizes[0])):
            timing_candidates.append(Path(sizes[0].path))
        report['categories'][folder] = info

        print(f"\n[{folder}] processed {info['processed_files']} files / {info['processed_mb']} MB "
              f"(online-only {info['processed_online_only']}, pinned {info['processed_pinned']}); "
              f"raw {info['raw_day_files']} days / {info['raw_mb']} MB, "
              f"{info['raw_files_not_yet_merged']} not merged yet")
        if 'files_rewritten_per_day' in info:
            print(f"  daily merge rewrites {info['files_rewritten_per_day']} files / "
                  f"{info.get('mb_rewritten_per_day', '?')} MB "
                  f"(online-only among them: {info.get('online_only_among_rewritten', '?')})")
        if 'sample_files' in info:
            print(f"  file shape (sample of {info['sample_files']}): median {info['sample_rows_median']:,} rows x "
                  f"{info['sample_columns_median']} columns, widest {info['sample_columns_max']} columns")
        print(f"  largest: {', '.join(f'{n} {s} MB' for n, s in info['largest'])}")
        for key in ('catch_all_files', 'unexpected_raw_names', 'retry_files', 'tmp_files_in_processed'):
            if info[key]:
                print(f"  {key}: {info[key]}")
        for item in info.get('deep', []):
            print(f"  {item}")

    if args.timing:
        report['timing'] = []
        print('\nRewrite timing (temp copy outside OneDrive):', flush=True)
        for path in sorted(timing_candidates, key=lambda p: p.stat().st_size, reverse=True)[:4]:
            width = pq.read_metadata(path).num_columns
            if width > 200:
                result = {'file': f'{path.parent.parent.name}/{path.name}',
                          'skipped': f'{width} columns; the pandas rewrite of a file this wide takes minutes'}
            else:
                try:
                    result = time_rewrite(path, module)
                except Exception as e:
                    result = {'file': path.name, 'error': f'{type(e).__name__}: {e}'}
            report['timing'].append(result)
            print(f'  {result}', flush=True)

    total_rewrite = sum(c.get('mb_rewritten_per_day', 0) for c in report['categories'].values()
                        if isinstance(c.get('mb_rewritten_per_day'), (int, float)))
    report['mb_rewritten_per_daily_run'] = round(total_rewrite, 1)
    print(f'\nA one-day update rewrites about {total_rewrite:,.0f} MB of processed files '
          f'(OneDrive uploads all of it again).')
    out = Path(tempfile.gettempdir()) / f"ogn_store_report_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    print(f'Report saved to {out}')


if __name__ == '__main__':
    main()
