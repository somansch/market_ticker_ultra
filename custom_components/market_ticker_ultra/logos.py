"""Where an instrument's logo is found.

The logos come from Elbstream's logo API: public image URLs, no key, free
against a visible link back to Elbstream wherever a logo is shown - which is
why the attribution travels to the card together with the URLs, and why
switching the logos off takes both away.

Only the URL is worked out here. The browser loads the image, and falls back
to initials where Elbstream has none.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from urllib.parse import quote

_BASE = "https://api.elbstream.com/logos"
# A raster logo is asked for at this height; one that exists as a drawing
# comes as a drawing whatever is asked.
_SIZE = "?size=96"

ATTRIBUTION = {"text": "Logos by Elbstream", "url": "https://elbstream.com/logos"}

# Futures by the commodity they are a contract on, in Elbstream's names.
# Only what was seen to answer; a future not listed here gets initials.
_COMMODITIES = {
    "GC": "gold",
    "MGC": "gold",
    "SI": "silver",
    "SIL": "silver",
    "CL": "oil",
    "MCL": "oil",
    "BZ": "oil",
    "NG": "natural_gas",
}


# Spot metals, by the code their source knows them by.
_METALS = {"XAU": "gold", "XAG": "silver", "XPT": "platinum", "XPD": "palladium", "HG": "copper"}


def logo_url(
    source: str,
    symbol: str,
    instrument_type: str | None,
    isin: str | None,
    name: str | None = None,
) -> str | None:
    """The logo of one instrument, or None where there is nothing to ask for."""
    kind = (instrument_type or "").upper()
    symbol = symbol.strip()

    if source == "goldapi":
        metal = _METALS.get(symbol.upper())
        return f"{_BASE}/commodity/{metal}{_SIZE}" if metal else None
    if source == "ecb":
        base, _, counter = symbol.partition("/")
        return f"{_BASE}/currency-pair/{quote(base)}/{quote(counter)}{_SIZE}" if counter else None
    if source == "kraken":
        # The pair's readable name, "BTC/EUR": the coin is what has a logo.
        coin = (name or "").partition("/")[0]
        return f"{_BASE}/crypto/{quote(coin)}{_SIZE}" if coin else None
    if source == "boerse_frankfurt":
        # "XETR:DE0007236101" carries the ISIN.
        return f"{_BASE}/isin/{quote(symbol.partition(':')[2])}{_SIZE}"

    if kind == "CRYPTOCURRENCY":
        # "BTC-EUR": the coin is what has a logo.
        return f"{_BASE}/crypto/{quote(symbol.split('-')[0])}{_SIZE}"

    if kind == "CURRENCY":
        # "EURUSD=X"; a bare "EUR=X" is the dollar against that currency.
        pair = symbol.removesuffix("=X")
        if len(pair) == 6 and pair.isalpha():
            return f"{_BASE}/currency-pair/{pair[:3].upper()}/{pair[3:].upper()}{_SIZE}"
        if len(pair) == 3 and pair.isalpha():
            return f"{_BASE}/currency-pair/USD/{pair.upper()}{_SIZE}"
        return None

    if kind == "FUTURE":
        commodity = _COMMODITIES.get(symbol.removesuffix("=F").upper())
        return f"{_BASE}/commodity/{commodity}{_SIZE}" if commodity else None

    if isin:
        return f"{_BASE}/isin/{quote(isin)}{_SIZE}"
    return f"{_BASE}/symbol/{quote(symbol, safe='')}{_SIZE}"


# --- a logo of one's own ----------------------------------------------------
#
# An instrument can carry an image the user uploaded: for one the logo source
# does not know, or in place of the one it has. The file lives in the
# configuration folder, outside the integration's own - an update replaces
# that one - and is served from a path of its own.

OWN_LOGO_URL_BASE = "/market_ticker_ultra_logos"
OWN_LOGO_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
OWN_LOGO_MAX_BYTES = 1024 * 1024


def own_logo_dir(config_dir: str) -> Path:
    return Path(config_dir) / "market_ticker_ultra" / "logos"


def own_logo_url(config_dir: str, file_name: str | None) -> str | None:
    """Where an uploaded logo is served - None where the file is gone.

    Reads the file's time from disk: call it off the event loop. The time
    travels in the address, so that a replaced image is fetched again.
    """
    if not file_name:
        return None
    path = own_logo_dir(config_dir) / Path(file_name).name
    try:
        stamp = int(path.stat().st_mtime)
    except OSError:
        return None
    return f"{OWN_LOGO_URL_BASE}/{quote(path.name)}?v={stamp}"


def store_own_logo(config_dir: str, subentry_id: str, source: Path) -> str:
    """Keep an uploaded image as the instrument's logo; the name it has now.

    Raises ValueError with "type" or "size" where it is not an image this
    takes.
    """
    suffix = source.suffix.lower()
    if suffix not in OWN_LOGO_TYPES:
        raise ValueError("type")
    if source.stat().st_size > OWN_LOGO_MAX_BYTES:
        raise ValueError("size")
    folder = own_logo_dir(config_dir)
    folder.mkdir(parents=True, exist_ok=True)
    remove_own_logo(config_dir, subentry_id)
    target = folder / f"{subentry_id}{suffix}"
    shutil.copyfile(source, target)
    return target.name


def remove_own_logo(config_dir: str, subentry_id: str) -> None:
    """Take an instrument's uploaded logo away, whatever type it was."""
    folder = own_logo_dir(config_dir)
    for suffix in OWN_LOGO_TYPES:
        (folder / f"{subentry_id}{suffix}").unlink(missing_ok=True)


def tidy_own_logos(config_dir: str, kept: set[str]) -> None:
    """Remove the images of instruments that no longer exist."""
    folder = own_logo_dir(config_dir)
    folder.mkdir(parents=True, exist_ok=True)
    for path in folder.iterdir():
        if path.is_file() and path.name not in kept:
            path.unlink(missing_ok=True)
