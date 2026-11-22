# Translation brief

You translate the user interface of "Market Ticker Ultra", a Home Assistant
integration with a dashboard card: live quotes for stocks, funds, indices,
currencies and coins, portfolios and watchlists, price alerts and news.

Folder: tools/i18n in this repository

Sources (read all of them; English is the source, German is a finished
translation that shows what each text means and how short it is meant to be):
- src/card.en.json, src/card.de.json       - the card and its editor (549 keys)
- src/backend.en.json, src/backend.de.json - the integration's dialogs
- src/extra.en.json, src/extra.de.json     - nine further strings

Write three files for your language code <code>, with exactly the same keys
and nesting as the English sources:
- out/<code>.card.json
- out/<code>.backend.json
- out/<code>.extra.json

Rules:
1. Translate every value. Never change a key. Keep the order.
2. Keep every placeholder in braces exactly as written: {name}, {symbol},
   {currency}, {price}, {limit}, {direction}, {change}, {count}, {quantity},
   {average}, {realized}, {query}, {found}, {group}, {source}, {reason}.
3. Keep a leading emoji, keep **bold** markers, keep \n line breaks and
   `code`. Do not add URLs.
4. Do not translate product and technical names: Market Ticker Ultra, Home
   Assistant, Yahoo Finance, Google News, Börse Frankfurt, Xetra, Kraken,
   gold-api.com, ECB (use your language's usual abbreviation for the European
   Central Bank), TradingView, Elbstream, Sonos, Companion App, SMA 20,
   SMA 50, EMA 9, RSI 14, ISIN, P/E and EPS only where your language's
   finance pages keep them (otherwise the usual local abbreviation), the
   event name market_ticker_ultra_alert, service names such as
   notify.whatsapp, symbols such as AAPL, NASDAQ:AAPL, #009999, file types.
   "Watchlist" may stay English where that is what finance apps in your
   language call it.
5. Wording: the words a retail investor sees in a broker or finance app in
   your language. Labels are short - a label that is one or two words in
   English stays one or two words. Help texts (keys ending in Help, and
   data_description) are one or two plain sentences; do not add information.
   Address the reader the way Home Assistant's own interface does in your
   language.
6. One term for one thing, throughout all three files: instrument, listing,
   portfolio, watchlist, group, holding/position, purchase, sale, price
   alert, limit, key figures, headline, gain, loss, realised gain, share
   (a position's share of the portfolio), allocation, performance, base
   currency, candlesticks.
7. In card.json a value written as { "fn": "<JavaScript>" } is an arrow
   function. Keep its parameters, translate only its texts, and return valid
   JavaScript source in the same { "fn": "..." } shape. Where your language
   has more plural forms than English, write the function so that every
   count reads correctly (for example with n % 10 and n % 100 tests).
8. The period labels r1d, r5d, r1mo, r3mo, r6mo, r1y, r5y, rmax ("1D", "1W",
   "1M", ...) stay as short as in English, in your language's usual letters.
   barOpen/barHigh/barLow/barClose are one-letter chart labels: use your
   language's usual ones, or keep O H L C if that is what charts there show.
9. In extra.json: "decimal_comma" is true if your language writes 1,5 and
   false if it writes 1.5. "settings", "portfolio", "watchlist" are names
   of things, capitalised as a title in your language.
10. The files are JSON in UTF-8 with two spaces of indentation (the backend
    file may keep four). Write them with a script or a file-writing tool,
    not through shell echo.

When the three files are written, run this and fix whatever it reports,
until it prints "<code>: ok":

    node tools/i18n/i18n_check.js <code>

Touch nothing outside tools/i18n/out, and only your own three files there.
Do not run git. Report in three lines: the check's last line, the terms you
chose for instrument / portfolio / watchlist / price alert / holding, and
anything you were unsure about.
