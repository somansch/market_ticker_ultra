"""Constants of the Market Ticker Ultra integration."""

DOMAIN = "market_ticker_ultra"

# The one kind of subentry there is: an instrument - a stock, a fund, an
# index, a future, a currency pair, a coin, anything a source can quote. It
# is a subentry of its group's entry (see groups.py).
SUBENTRY_INSTRUMENT = "instrument"

# What an entry is: a group - a portfolio, whose purchases are added up, or
# a watchlist, which counts in no sum - or the one entry with the settings
# all groups share.
CONF_KIND = "kind"
KIND_PORTFOLIO = "portfolio"
KIND_WATCHLIST = "watchlist"
KINDS = (KIND_PORTFOLIO, KIND_WATCHLIST)
KIND_SETTINGS = "settings"
SETTINGS_UNIQUE_ID = "settings"
# In front of the settings entry's name: the list of entries is sorted by
# name, and this puts it first.
SETTINGS_GEAR = "⚙"

# The index a portfolio is compared with: its symbol at Yahoo Finance, in
# the group's options. Some to choose from, each by its name; any other
# symbol can be typed.
CONF_BENCHMARK = "benchmark"
BENCHMARKS = {
    "^990100-USD-STRD": "MSCI World",
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^DJI": "Dow Jones",
    "^GDAXI": "DAX",
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
}

# From before every group was an entry: a group as a subentry, and the
# group an instrument named. Read once more, when such an entry is taken
# apart (see groups.py).
SUBENTRY_GROUP = "group"
CONF_GROUP = "group"

# A price alert of an instrument: the price at or below, and at or above,
# which it is on. In the instrument's own currency.
CONF_ALERT_BELOW = "alert_below"
CONF_ALERT_ABOVE = "alert_above"
# Who is told when an alert comes on: notify entities, and whether a
# notification is put into Home Assistant itself.
CONF_ALERT_NOTIFY = "alert_notify"
CONF_ALERT_PERSISTENT = "alert_persistent"
# Notify services told by their name - "notify.whatsapp", "notify.mail":
# what mail and the messengers are reached by, which have no entity.
CONF_ALERT_SERVICES = "alert_services"
# The speakers an alert is announced on, and the voice it is spoken with -
# without one, the first voice there is.
CONF_ALERT_SPEAKERS = "alert_speakers"
CONF_ALERT_TTS = "alert_tts"
# What an alert says: its title, its message, and what is spoken on the
# speakers - each with variables in braces (see alert_texts in
# coordinator.py). Empty takes the default in Home Assistant's language.
CONF_ALERT_TITLE = "alert_title"
CONF_ALERT_MESSAGE = "alert_message"
CONF_ALERT_SPOKEN = "alert_spoken"
# An alert's default words are in localized.py, under these three keys.
# The event fired with every alert, for automations.
EVENT_ALERT = f"{DOMAIN}_alert"
# Whether an instrument's news are asked for at Google News too - a search
# for its name, which finds more and fits less well than Yahoo's own feed.
CONF_NEWS_GOOGLE = "news_google"
DEFAULT_ALERT_PERSISTENT = True

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 5  # minutes
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 120
# While no market of any instrument is open, nothing moves: the poll slows
# down to this, unless the interval set is longer anyway.
CLOSED_SCAN_INTERVAL = 30
# The longest wait after a source asked for a break (HTTP 429).
MAX_BACKOFF = 120

# Whether instruments are shown with a logo.
CONF_LOGOS = "logos"
DEFAULT_LOGOS = True

# The currency the positions are added up in.
CONF_BASE_CURRENCY = "base_currency"

# What a subentry stores about its instrument.
CONF_QUERY = "query"
CONF_LISTING = "listing"
CONF_SOURCE = "source"
CONF_SYMBOL = "symbol"
CONF_NAME = "name"
CONF_ISIN = "isin"
CONF_EXCHANGE = "exchange"
CONF_TYPE = "type"
CONF_CURRENCY = "currency"
# The colour an instrument is drawn in where a card shows a portfolio's
# shares: one of Home Assistant's own colours by its name - "red",
# "deep-purple" - or "#rrggbb"; without one the card takes the next of its own.
CONF_COLOR = "color"
# An instrument shown in the base currency although its venue quotes it in
# another: every figure is converted at the reference rate - the day's own
# for a bar of a chart. CONF_CURRENCY is the base currency then, and
# CONF_QUOTE_CURRENCY the one the venue quotes in.
CONF_CONVERT = "convert"
CONF_QUOTE_CURRENCY = "quote_currency"
# Home Assistant's own colours, as its colour picker names them.
THEME_COLORS = frozenset(
    {
        "primary",
        "accent",
        "red",
        "pink",
        "purple",
        "deep-purple",
        "indigo",
        "blue",
        "light-blue",
        "cyan",
        "teal",
        "green",
        "light-green",
        "lime",
        "yellow",
        "amber",
        "orange",
        "deep-orange",
        "brown",
        "light-grey",
        "grey",
        "dark-grey",
        "blue-grey",
        "black",
        "white",
    }
)
# The file name of a logo the user uploaded for the instrument.
CONF_LOGO_FILE = "logo_file"
# TradingView's symbol for the instrument, where the user entered one.
CONF_TRADINGVIEW = "tradingview"
# TradingView's symbol as it was looked up for an instrument that is known
# by its ISIN only (see tradingview.py). Empty: asked, and nothing found.
CONF_TRADINGVIEW_FOUND = "tradingview_found"

SOURCE_YAHOO = "yahoo"

# Which sources are asked at all. Every one of them by default; the order is
# the one their finds are listed in - the ones that only know one kind of
# thing first.
CONF_SOURCES = "sources"
ALL_SOURCES = ("ecb", "goldapi", "kraken", "yahoo", "boerse_frankfurt")

# Market states an instrument can be in.
STATE_OPEN = "open"
STATE_CLOSED = "closed"
STATE_PRE = "pre"
STATE_POST = "post"
