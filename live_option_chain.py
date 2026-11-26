"""Real-time 5paisa option-chain snapshots for the volatility cone's --live overlay.

Fetches the next monthly expiries' chains through the py5paisa SDK and reshapes them into the
derivatives columns option_overlay prices, so live quotes go through the same Black-76,
put-call-parity forward and Smile MAD code as the stored end-of-day data. py5paisa and pyotp
are imported only when --live logs in.

Reply shapes follow the SDK source and the replies quoted in OpenApi-5p/py5paisa issues #154/#288:
get_expiry -> {'Expiry': [{'ExpiryDate': '/Date(<UTC ms>+0530)/', ...}], 'lastrate': [{'LTP': ...}]};
get_option_chain -> {'Options': [{'CPType', 'StrikeRate', 'LastRate', 'Volume', 'OpenInterest', ...}]}.
"""

import os
import re
import sys
import time

import numpy as np
import pandas as pd

import option_overlay

# ── 5paisa Xstream settings: FILL IN ──────────────────────────────────────
# API keys: https://xstream.5paisa.com/dashboard. An environment variable FIVEPAISA_<NAME>
# (e.g. FIVEPAISA_APP_NAME, FIVEPAISA_TOTP_SECRET) overrides each value below. Prefer those:
# this file is tracked by git, so real values typed here could be committed.
FIVEPAISA_CREDENTIALS = {
    'APP_NAME': 'FIVEPAISA__APP_NAME',              # FILL IN: App name
    'APP_SOURCE': 'FIVEPAISA__APP_SOURCE',          # FILL IN: App source
    'USER_ID': 'FIVEPAISA__USER_ID',                # FILL IN: API user ID
    'PASSWORD': 'FIVEPAISA__PASSWORD',          # FILL IN: API password
    'USER_KEY': 'FIVEPAISA__USER_KEY',              # FILL IN: User key (the API key)
    'ENCRYPTION_KEY': 'FIVEPAISA__ENCRYPTION_KEY',  # FILL IN: Encryption key
}
FIVEPAISA_LOGIN = {
    'CLIENT_CODE': 'FIVEPAISA__CLIENT_CODE',        # FILL IN: 8-digit 5paisa client code
    'PIN': 'FIVEPAISA__PIN',                        # FILL IN: login PIN
    'TOTP_SECRET': 'FIVEPAISA__TOTP_SECRET',        # FILL IN: authenticator (TOTP) secret
}

LIVE_EXCHANGES = {'SENSEX': 'B', 'BANKEX': 'B'}  # 5paisa exchange per symbol; the rest are NSE ('N')
REQUESTS_PER_MINUTE = 50                          # 5paisa's published limit for non-order APIs
SESSION_OPEN = pd.Timedelta(hours=9, minutes=15)  # NSE F&O open (IST); the close is OPTION_EXPIRY_CLOSE
IST = pd.Timedelta(hours=5, minutes=30)           # UTC offset; India keeps no daylight saving
CHAIN_COLUMNS = ['CPType', 'StrikeRate', 'LastRate', 'Volume', 'OpenInterest']
_WCF_DATE = re.compile(r'/Date\((-?\d+)')

_client = None
_last_request = float('-inf')


class LiveSnapshotError(RuntimeError):
    """No live snapshot; the message says why."""


def settings():
    """(credentials, login) for 5paisa: FIVEPAISA_<NAME> environment variables, else the values above."""
    groups = [{name: os.environ.get(f'FIVEPAISA_{name}', '').strip() or str(value).strip()
               for name, value in group.items()} for group in (FIVEPAISA_CREDENTIALS, FIVEPAISA_LOGIN)]
    missing = [name for group in groups for name, value in group.items()
               if not value or value.startswith('YOUR_')]
    if missing:
        raise LiveSnapshotError(f"Fill in the 5paisa {', '.join(missing)} at the top of live_option_chain.py, "
                                'or set them as FIVEPAISA_<NAME> environment variables.')
    return groups[0], groups[1]


def _filter_sdk_log():
    """Keep the SDK's console messages, minus its 'Success' echoes and the line printing the login token."""
    from loguru import logger
    logger.remove()
    logger.add(sys.stdout, level='INFO', format='  [5paisa] {message}',
               filter=lambda record: record['message'] != 'Success'
               and not record['message'].startswith('RequestToken'))


def connect():
    """Log in to 5paisa with TOTP once per run and return the SDK client."""
    global _client
    if _client is not None:
        return _client
    credentials, login = settings()
    try:
        import pyotp
        from py5paisa import FivePaisaClient
    except ImportError as error:
        raise LiveSnapshotError(f'--live needs py5paisa and pyotp (pip install py5paisa pyotp): {error}') from error
    _filter_sdk_log()

    class IssuedTOTP(pyotp.TOTP):
        min_secret_length_bits = 0  # 5paisa sets the secret's length; pyotp >= 2.10 demands 112 bits

    try:
        totp = IssuedTOTP(login['TOTP_SECRET'])
        remaining = totp.interval - time.time() % totp.interval
        if remaining < 3:  # A code that rolls over in flight fails as "Invalid TOTP"
            time.sleep(remaining)
        code = totp.now()
    except (TypeError, ValueError) as error:
        raise LiveSnapshotError('TOTP_SECRET is not a valid base32 authenticator secret.') from error
    client = FivePaisaClient(cred=credentials)
    if not client.get_totp_session(login['CLIENT_CODE'], code, login['PIN']):
        raise LiveSnapshotError('5paisa login failed (reason above); check CLIENT_CODE, PIN, TOTP_SECRET and USER_KEY.')
    _client = client
    return client


def _request(client, method, *arguments):
    """One SDK call, paced to REQUESTS_PER_MINUTE and sent without fields left over from earlier calls.

    py5paisa reuses one request body for every call, so without the reset the login's PIN,
    TOTP and keys would travel with each market-data request.
    """
    global _last_request
    pause = _last_request + 60.0 / REQUESTS_PER_MINUTE - time.monotonic()
    if pause > 0:
        time.sleep(pause)
    payload = getattr(client, 'payload', None)
    if isinstance(payload, dict) and isinstance(payload.get('body'), dict):
        payload['body'].clear()
    _last_request = time.monotonic()
    reply = getattr(client, method)(*arguments)
    if not isinstance(reply, dict):
        raise LiveSnapshotError(f'5paisa {method} returned no data (network error or expired session).')
    return reply


def now_ist():
    """Current Indian time, naive."""
    return pd.Timestamp.now(tz='UTC').tz_localize(None) + IST


def pricing_moment(moment):
    """When a snapshot's last trades happened: `moment` inside a weekday session, else the last weekday close.

    Exchange holidays count as sessions, as in the weekday tenors used elsewhere.
    """
    moment = pd.Timestamp(moment)
    day = moment.normalize()
    if moment.weekday() < 5 and moment >= day + SESSION_OPEN:
        return min(moment, day + option_overlay.OPTION_EXPIRY_CLOSE)
    return day - pd.offsets.BDay(1) + option_overlay.OPTION_EXPIRY_CLOSE


def _positive(value):
    """value as a positive float, else NaN."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) and number > 0 else np.nan


def _expiry_dates(reply):
    """{expiry date: the epoch milliseconds get_option_chain wants} from a get_expiry reply."""
    listed = {}
    for item in reply.get('Expiry') or []:
        match = _WCF_DATE.search(str(item.get('ExpiryDate', ''))) if isinstance(item, dict) else None
        if match:
            # UTC milliseconds: NSE stamps 14:30 IST and BSE 00:00 IST, so only the IST date is reliable
            listed[(pd.Timestamp(int(match.group(1)), unit='ms') + IST).normalize()] = int(match.group(1))
    return listed


def lot_size(*quantities):
    """Greatest common divisor of a chain's positive whole quantities.

    5paisa reports Volume and OpenInterest in units (lots x lot size), so this recovers the lot
    size; it is 1 when the quantities are already contracts.
    """
    values = pd.concat(quantities).to_numpy(dtype=float)
    values = values[np.isfinite(values) & (values > 0) & (values == np.round(values))]
    return int(np.gcd.reduce(values.astype(np.int64))) if len(values) else 1


def _chain_rows(options, symbol, session, expiry, spot):
    """One expiry's 5paisa chain as option_overlay derivatives rows, quantities in contracts."""
    missing = sorted(set(CHAIN_COLUMNS) - set(options.columns))
    if missing:
        raise LiveSnapshotError(f'5paisa option chain lacks {missing}.')
    numbers = options[CHAIN_COLUMNS[1:]].apply(pd.to_numeric, errors='coerce')
    lot = lot_size(numbers['Volume'], numbers['OpenInterest'])
    rows = pd.DataFrame({
        'Date': session, 'Expiry': expiry, 'Symbol': symbol,
        'Option type': options['CPType'].astype(str).str.strip().str.upper(),
        'Strike Price': numbers['StrikeRate'], 'Contracts': numbers['Volume'] / lot,
        'Open Int': numbers['OpenInterest'] / lot,
        'Close': numbers['LastRate'].where(numbers['LastRate'] > 0),
        'Underlying Price': spot, 'Lot Size': lot})
    return rows, lot


def snapshot(symbol, spot=np.nan, count=option_overlay.OPTION_MONTHLY_EXPIRIES, client=None):
    """Live option chains for `symbol`'s next `count` monthly expiries.

    Returns {'chain', 'session', 'fetched', 'priced_at', 'expiries', 'spot', 'lot sizes'}: chain
    rows in derivatives columns (Close = last traded price), dated with the session the prices
    belong to. `spot` stands in when 5paisa's reply carries no underlying price.
    """
    client = client or connect()
    symbol = symbol.upper()
    exchange = LIVE_EXCHANGES.get(symbol, 'N')
    fetched = now_ist()
    priced_at = pricing_moment(fetched)
    session = priced_at.normalize()
    reply = _request(client, 'get_expiry', exchange, symbol)
    listed = _expiry_dates(reply)
    kinds = option_overlay.classify_expiries(list(listed))
    expiries = [expiry for expiry in kinds.index[kinds.eq('Monthly')] if expiry > session][:count]
    if not expiries:
        raise LiveSnapshotError(f"5paisa lists no upcoming monthly expiry for {symbol} "
                                f"({reply.get('Message') or 'empty reply'}).")
    quotes = [_positive(row.get('LTP')) for row in reply.get('lastrate') or [] if isinstance(row, dict)]
    spot = next((quote for quote in quotes if np.isfinite(quote)), spot)
    frames, lots = [], {}
    for expiry in expiries:
        reply = _request(client, 'get_option_chain', exchange, symbol, listed[expiry])
        options = pd.DataFrame(reply.get('Options') or [])
        if not options.empty:
            rows, lots[expiry] = _chain_rows(options, symbol, session, expiry, spot)
            frames.append(rows)
    if not frames:
        raise LiveSnapshotError(f"5paisa returned empty option chains for {symbol} "
                                f"({reply.get('Message') or 'empty reply'}).")
    return {'chain': pd.concat(frames, ignore_index=True), 'session': session, 'fetched': fetched,
            'priced_at': priced_at, 'expiries': list(lots), 'spot': spot, 'lot sizes': lots}
