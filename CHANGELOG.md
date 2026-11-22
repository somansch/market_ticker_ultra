# Changelog

All notable changes to this integration are documented here.

## v1.1.0

### Added
- **Change the listing of an instrument.** A new entry in an instrument's menu, 🏛️ **Change the listing**, searches for it again - by its ISIN where that is known, else by its name - and moves it to another exchange or source. Its name, purchases and sales, alerts, colour, logo and sensors stay, and the TradingView link follows. Until now the only way was to remove the instrument and add it again.
- **Show an instrument in your base currency.** 💱 **Currency** in the same menu, and a switch under the list of listings when adding: **Convert to** the base currency. A share bought in euros is often listed at a small exchange there that makes a few prices a day, while its home exchange trades it all day in dollars - with the switch, the home listing is shown in euros. The price, the previous close, the day's and the 52-week range, market cap and EPS are converted at the European Central Bank's reference rate of the day, each point of the chart at the rate of its own day. It is not the price the instrument trades at in your currency, and its change includes the currency's. A currency the ECB publishes no rate for is refused, with a message. Purchases, sales and price alerts are not converted: their figures count as the currency the instrument is shown in.

### Changed
- **The week's chart is drawn day by day.** Every day is as wide as the next, and each price stands at its time of day. The bars used to be spread evenly over the width, one beside the other: a listing with eight prices in a week had a day twice under the chart and another not at all, and a day with few prices was a narrow strip.
- **The statistics start afresh where the currency changes.** When an instrument's currency changes - by the new switch or by a listing in another currency - the long-term statistics of its price, position value and gain sensors are cleared. The same goes for a new base currency in the settings: the portfolios' sums, spot metals and converted instruments were in the old one. Home Assistant stops writing a series whose unit has changed - it used to warn about that in the log after a new base currency - and one with dollars and euros in it says nothing.

### Fixed
- **The chart follows a change at once.** The card keeps a chart and the key figures for a few minutes - up to half an hour for the longer periods - and kept them by instrument alone. After another listing or currency it went on showing the old ones for that long. They are kept by listing and currency now.

## v1.0.0

Initial release: live quotes for stocks, funds, indices, currencies, coins and precious metals from public sources - no account, no API key -, portfolios and watchlists with purchases and sales, price alerts, news, and a dashboard card of its own. Everything it does is described in the [README](README.md).
