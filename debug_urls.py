"""
Diagnostic: Use the actual NSEMarketDataDownloader class to test downloads.
For each category, find 5 REMAINING days (not yet downloaded) and test them
with verbose output showing HTTP status codes and URLs.
"""
import importlib.util
import datetime
import sys
import os
import random
from pathlib import Path

# Import the main script
spec = importlib.util.spec_from_file_location("ogn_download", "OGN v2.0-download.py")
ogn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ogn)


def find_remaining_days(dl, raw_dir, raw_prefix, start_date, end_date, max_sample=5):
    """Find days that don't have raw parquet files (same logic as _concurrent_download)."""
    all_days = dl.get_trading_days(start_date, end_date)
    remaining = [day for day in all_days
                 if not (raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet").exists()]
    # Pick newest first (like the script does)
    remaining = list(reversed(remaining))
    # Sample: first 2 (newest) + 3 random from the rest
    if len(remaining) <= max_sample:
        return remaining
    sample = remaining[:2]
    if len(remaining) > 2:
        sample += random.sample(remaining[2:], min(3, len(remaining) - 2))
    return sample


def test_category(dl, label, download_fn, raw_dir, raw_prefix):
    """Test download for 5 remaining days and show verbose results."""
    start = ogn.DEFAULT_START_DATE
    end = datetime.date.today()
    
    all_days = dl.get_trading_days(start, end)
    remaining = [day for day in all_days
                 if not (raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet").exists()]
    
    print(f"\n{'='*60}")
    print(f"  {label}: {len(all_days)} total trading days, {len(all_days)-len(remaining)} downloaded, {len(remaining)} remaining")
    
    if not remaining:
        print(f"  All days already downloaded!")
        return
    
    # Pick sample
    remaining_newest = list(reversed(remaining))
    sample = remaining_newest[:2]
    if len(remaining_newest) > 5:
        sample += random.sample(remaining_newest[5:], min(3, len(remaining_newest) - 5))
    elif len(remaining_newest) > 2:
        sample += remaining_newest[2:]
    
    print(f"  Testing {len(sample)} sample days: {[str(d) for d in sample]}")
    
    for day in sample:
        print(f"\n  --- Testing {label} for {day} ---")
        try:
            result = download_fn(day)
            if result is not None:
                day_val, df = result
                if df is not None:
                    print(f"  SUCCESS: {df.shape[0]} rows, {df.shape[1]} cols")
                    print(f"  Columns: {list(df.columns[:8])}")
                else:
                    print(f"  FAILED: download_fn returned (day, None)")
            else:
                print(f"  FAILED: download_fn returned None")
        except ogn.HTTP403Error as e:
            print(f"  HTTP403: {e}")
        except Exception as e:
            print(f"  EXCEPTION: {type(e).__name__}: {e}")


def main():
    print("=" * 60)
    print("NSE Download Diagnostic — Testing with actual download class")
    print("=" * 60)
    
    # Monkey-patch _download_file to add verbose logging
    original_download = ogn.NSEMarketDataDownloader._download_file
    
    def verbose_download(self, url, referer=None):
        import requests
        import time
        import random as rnd
        
        # Throttle (same as original)
        with self._throttle_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.REQUEST_DELAY:
                time.sleep(self.REQUEST_DELAY - elapsed)
            self._last_request_time = time.time()
            self._request_count += 1
        
        headers = dict(self.session.headers)
        if referer:
            headers["Referer"] = referer
        headers["User-Agent"] = rnd.choice(ogn._USER_AGENTS)
        
        if ogn.ARCHIVE_URL in url:
            headers["sec-fetch-dest"] = "document"
            headers["sec-fetch-mode"] = "navigate"
            headers["sec-fetch-site"] = "same-site"
            headers["sec-fetch-user"] = "?1"
        elif "/api/" in url:
            headers["sec-fetch-dest"] = "empty"
            headers["sec-fetch-mode"] = "cors"
            headers["sec-fetch-site"] = "same-origin"
        
        try:
            r = self.session.get(url, timeout=20, headers=headers)
            ct = r.headers.get('Content-Type', 'N/A')
            is_html = ct.startswith('text/html') and b'<!DOCTYPE html>' in r.content[:100]
            short_url = url.split('?')[0].split('/')[-1]
            
            print(f"    HTTP {r.status_code} | CT={ct[:40]} | HTML_page={is_html} | Size={len(r.content):,} | {short_url}")
            
            if r.status_code == 200:
                if is_html:
                    print(f"    ^ HTML error page (bot block?): {r.content[:100]}")
                    return None
                return r.content
            elif r.status_code == 404:
                return None
            elif r.status_code == 403:
                raise ogn.HTTP403Error(f"HTTP 403 for {short_url}")
            else:
                print(f"    ^ Unexpected status")
                return None
        except ogn.HTTP403Error:
            raise
        except Exception as e:
            print(f"    ^ Request error: {type(e).__name__}: {e}")
            return None
    
    # Apply monkey-patch
    ogn.NSEMarketDataDownloader._download_file = verbose_download
    
    dl = ogn.NSEMarketDataDownloader()
    
    categories = [
        ("Equity", dl._download_day_cm, ogn.EQUITY_RAW, "equity"),
        ("Derivatives", dl._download_day_fo, ogn.DERIVATIVES_RAW, "derivatives"),
        ("Indices", dl._download_day_idx, ogn.INDICES_RAW, "indices"),
        ("Short Selling", dl._download_day_ss, ogn.SHORTSELLING_RAW, "short_selling"),
        ("Volatility", dl._download_day_vol, ogn.VOLATILITY_RAW, "volatility"),
        ("Market Activity", dl._download_day_ma, ogn.MARKETACTIVITY_RAW, "market_activity"),
        ("Price Band", dl._download_day_pb, ogn.PRICEBAND_RAW, "price_band"),
        ("PE Ratio", dl._download_day_pe, ogn.PERATIO_RAW, "pe_ratio"),
        ("Corporate Bonds", dl._download_day_cb, ogn.CORPBONDS_RAW, "corp_bonds"),
        ("Delivery Positions", dl._download_day_del, ogn.DELIVERY_RAW, "delivery"),
    ]
    
    for label, download_fn, raw_dir, raw_prefix in categories:
        test_category(dl, label, download_fn, raw_dir, raw_prefix)
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")


if __name__ == "__main__":
    main()
