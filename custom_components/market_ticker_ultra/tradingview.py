"""What TradingView calls an instrument.

The card links an instrument's details to its page there. TradingView names
everything `EXCHANGE:TICKER`, which none of the sources do, so the name is
worked out here from what a source calls the instrument - and where nothing
can be worked out there is no link, rather than one to a wrong page. A
symbol the user entered for an instrument comes before all of it.

The Frankfurt exchange knows an instrument by its ISIN, which says nothing
about its ticker. That one is looked up at OpenFIGI - once, and kept with
the instrument.
"""

from __future__ import annotations

import re
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import CONF_SOURCE, CONF_SYMBOL, CONF_TRADINGVIEW_FOUND

_OPENFIGI = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_TIMEOUT = ClientTimeout(total=10)
# How many ISINs one question may carry without a key.
_OPENFIGI_JOBS = 10
# OpenFIGI's codes for the German exchanges, Xetra's first. An instrument
# has one ticker on all of them.
_GERMAN_CODES = ("GY", "GR", "GF", "GS", "GM", "GD", "GH", "GI", "GB", "GT", "TH")
# The Frankfurt source's venue, and TradingView's word for it.
_FRANKFURT_VENUES = {"XETR": "XETR", "XFRA": "FWB"}

# What a symbol somebody typed has to look like: the exchange, a colon, the
# ticker - "XETR:SIE", "COMEX:GC1!", "NYSE:BRK.B".
OWN_SYMBOL = re.compile(r"^[A-Z0-9_]+:[A-Z0-9_.!]+$")

# Yahoo's ending for an exchange, and TradingView's word for that exchange.
_SUFFIXES = {
    "DE": "XETR",
    "F": "FWB",
    "SG": "SWB",
    "MU": "MUN",
    "DU": "DUS",
    "HM": "HAM",
    "HA": "HAN",
    "L": "LSE",
    "PA": "EURONEXT",
    "AS": "EURONEXT",
    "BR": "EURONEXT",
    "LS": "EURONEXT",
    "MI": "MIL",
    "SW": "SIX",
    "MC": "BME",
    "VI": "VIE",
    "ST": "OMXSTO",
    "HE": "OMXHEX",
    "CO": "OMXCOP",
    "OL": "OSL",
    "WA": "GPW",
    "TO": "TSX",
    "HK": "HKEX",
    "T": "TSE",
    "AX": "ASX",
}
# Where a share class is written with an underscore: "VOLV-B.ST" is VOLV_B.
_UNDERSCORED = {"OMXSTO", "OMXHEX", "OMXCOP"}

# Yahoo's name for the exchange of a symbol without an ending.
_US_EXCHANGES = (
    ("nasdaq", "NASDAQ"),
    ("nysearca", "AMEX"),
    ("nyse arca", "AMEX"),
    ("nyse american", "AMEX"),
    ("nyse", "NYSE"),
    ("otc", "OTC"),
)

_INDICES = {
    "^GDAXI": "XETR:DAX",
    "^MDAXI": "XETR:MDAX",
    "^SDAXI": "XETR:SDXP",
    "^TECDAX": "XETR:TDXP",
    "^STOXX50E": "TVC:SX5E",
    "^FTSE": "TVC:UKX",
    "^FCHI": "TVC:CAC40",
    "^SSMI": "SIX:SMI",
    "^GSPC": "SP:SPX",
    "^DJI": "DJ:DJI",
    "^IXIC": "NASDAQ:IXIC",
    "^NDX": "NASDAQ:NDX",
    "^RUT": "TVC:RUT",
    "^VIX": "TVC:VIX",
    "^N225": "TVC:NI225",
    "^HSI": "TVC:HSI",
}

# The front contract of a future, as TradingView's continuous one.
_FUTURES = {
    "GC=F": "COMEX:GC1!",
    "SI=F": "COMEX:SI1!",
    "HG=F": "COMEX:HG1!",
    "PL=F": "NYMEX:PL1!",
    "PA=F": "NYMEX:PA1!",
    "CL=F": "NYMEX:CL1!",
    "BZ=F": "NYMEX:BZ1!",
    "NG=F": "NYMEX:NG1!",
    "ZC=F": "CBOT:ZC1!",
    "ZW=F": "CBOT:ZW1!",
    "ZS=F": "CBOT:ZS1!",
    "KC=F": "ICEUS:KC1!",
    "CC=F": "ICEUS:CC1!",
    "SB=F": "ICEUS:SB1!",
    "CT=F": "ICEUS:CT1!",
    "ES=F": "CME_MINI:ES1!",
    "NQ=F": "CME_MINI:NQ1!",
    "YM=F": "CBOT_MINI:YM1!",
    "RTY=F": "CME_MINI:RTY1!",
}

# The spot metals the metal source has that are quoted like a currency.
_SPOT_METALS = {"XAU", "XAG", "XPT", "XPD"}

_PAIR = re.compile(r"^([A-Z]{3})/?([A-Z]{3})$")
_COIN = re.compile(r"^([A-Z0-9]+)-([A-Z]{3})$")
_TICKER = re.compile(r"^[A-Z0-9]+([-.][A-Z0-9]+)?$")


def clean_own_symbol(text: str | None) -> str | None:
    """A typed symbol in TradingView's writing, or nothing if it is none."""
    symbol = (text or "").strip().upper()
    return symbol if OWN_SYMBOL.match(symbol) else None


def _yahoo(symbol: str, exchange: str | None, kind: str | None) -> str | None:
    if symbol in _INDICES:
        return _INDICES[symbol]
    if symbol in _FUTURES:
        return _FUTURES[symbol]
    if symbol.startswith("^") or symbol.endswith("=F"):
        return None
    if symbol.endswith("=X"):
        pair = symbol[:-2]
        # "EUR=X" is the dollar in euros.
        if len(pair) == 3:
            pair = "USD" + pair
        return f"FX_IDC:{pair}" if _PAIR.match(pair) else None
    coin = _COIN.match(symbol)
    if coin and (kind or "").upper() == "CRYPTOCURRENCY":
        base, quote = coin.groups()
        return f"CRYPTO:{base}USD" if quote == "USD" else f"KRAKEN:{base}{quote}"
    ticker, dot, suffix = symbol.rpartition(".")
    if dot and suffix in _SUFFIXES:
        market = _SUFFIXES[suffix]
        if not _TICKER.match(ticker):
            return None
        if market == "HKEX":
            ticker = ticker.lstrip("0") or ticker
        ticker = ticker.replace("-", "_" if market in _UNDERSCORED else ".")
        return f"{market}:{ticker}"
    if dot or not _TICKER.match(symbol):
        # An ending that is not known, or nothing like a ticker.
        return None
    named = (exchange or "").lower()
    for word, market in _US_EXCHANGES:
        if word in named:
            # A share class: "BRK-B" is BRK.B.
            return f"{market}:{symbol.replace('-', '.')}"
    return None


def tradingview_symbol(
    source: str,
    symbol: str,
    exchange: str | None = None,
    kind: str | None = None,
    currency: str | None = None,
) -> str | None:
    """TradingView's symbol for an instrument of a source, where there is one."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    if source == "yahoo":
        return _yahoo(symbol, exchange, kind)
    if source == "kraken":
        # Kraken's own name for a pair is the one TradingView lists it by.
        return f"KRAKEN:{symbol}" if re.match(r"^[A-Z0-9]+$", symbol) else None
    if source == "ecb":
        pair = _PAIR.match(symbol)
        return f"FX_IDC:{pair.group(1)}{pair.group(2)}" if pair else None
    if source == "goldapi":
        # In the currency the integration shows the metal in - US dollars
        # where it is not told.
        money = (currency or "USD").upper()
        if symbol not in _SPOT_METALS or not re.match(r"^[A-Z]{3}$", money):
            return None
        return f"FX_IDC:{symbol}{money}"
    # The Frankfurt exchange is asked by ISIN, which TradingView has no
    # address for: see lookup_frankfurt.
    return None


def frankfurt_isin(data: dict[str, Any]) -> tuple[str, str] | None:
    """Venue and ISIN of an instrument of the Frankfurt source, else nothing."""
    if data.get(CONF_SOURCE) != "boerse_frankfurt":
        return None
    venue, _, isin = str(data.get(CONF_SYMBOL) or "").upper().partition(":")
    if venue not in _FRANKFURT_VENUES or not re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin):
        return None
    return venue, isin


def needs_lookup(data: dict[str, Any]) -> bool:
    """Whether an instrument's symbol has still to be looked up."""
    return frankfurt_isin(data) is not None and CONF_TRADINGVIEW_FOUND not in data


def found_symbol(data: dict[str, Any]) -> str | None:
    """The symbol that was looked up for an instrument, where one was found."""
    return clean_own_symbol(data.get(CONF_TRADINGVIEW_FOUND))


async def lookup_frankfurt(
    session: ClientSession, wanted: list[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """TradingView's symbols for venues and ISINs of the Frankfurt source.

    Asked at OpenFIGI, which names the ticker an ISIN trades under on the
    German exchanges. An empty string says it knows none; a pair that is
    missing from the answer could not be asked - to be tried again later.
    """
    result: dict[tuple[str, str], str] = {}
    for start in range(0, len(wanted), _OPENFIGI_JOBS):
        part = wanted[start : start + _OPENFIGI_JOBS]
        try:
            async with session.post(
                _OPENFIGI,
                json=[{"idType": "ID_ISIN", "idValue": isin} for _, isin in part],
                timeout=_OPENFIGI_TIMEOUT,
            ) as response:
                if response.status != 200:
                    continue
                answer = await response.json(content_type=None)
        except (TimeoutError, ClientError, ValueError):
            continue
        if not isinstance(answer, list) or len(answer) != len(part):
            continue
        for (venue, isin), job in zip(part, answer):
            if not isinstance(job, dict) or "error" in job:
                continue
            tickers: dict[str, str] = {}
            for row in job.get("data") or []:
                code, ticker = row.get("exchCode"), str(row.get("ticker") or "").upper()
                if code in _GERMAN_CODES and re.match(r"^[A-Z0-9]+$", ticker):
                    tickers.setdefault(code, ticker)
            ticker = next((tickers[code] for code in _GERMAN_CODES if code in tickers), "")
            result[(venue, isin)] = f"{_FRANKFURT_VENUES[venue]}:{ticker}" if ticker else ""
    return result
