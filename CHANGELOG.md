# Changelog

All notable changes to this integration are documented here.

## v2.0.0

A seventh format, the table, and with it a view of all portfolios at once. Nothing has to be changed after the update: existing cards and entries keep working as they are.

### Added
- **The table format.** Instruments as rows, with the columns you choose. Each column has a value, optionally a second value under it, and a heading of its own. 32 values to choose from: name with or without its logo, symbol, exchange, price, previous close, the day's and the 52-week range, volume, the change over the day and over the last five trading days - each as an amount and in percent -, small curves of the day, the week and the month, the price alert's symbol, the symbol for new headlines, and everything about what is held. Three starting points - Compact, Portfolio and Classic - and from the first change the columns are the card's own. A click on a heading sorts, a search field filters the rows by name or symbol, a refresh button fetches the prices again and says how long ago they were fetched, and a last line adds up the portfolio. Every figure in the gain or loss colour can stand as a pill, per column. See [The table format](README.md#the-table-format).
- **Portfolios as rows.** With **Rows** set to **Portfolios**, the table has one line per portfolio - positions, value, share, today's gain, the gain since the purchases and small curves of its performance - and the total of all of them. A click on a portfolio shows its instruments in the same table.
- **Portfolios as entries of the ticker, the compact row and the carousel.** **Entries → Portfolios** shows one entry per portfolio: its value in the place of the price and today's change. A click opens the details of its first position, and the pop-up's arrows lead through the positions of that portfolio.
- **The trend.** How the price moved with the last update - up, down or unchanged, and by how much: an arrow in a table's column, and the attributes `trend` and `trend_change` on every price sensor. It is not the change against the previous close.
- **Purchases and sales in the details.** The chart marks each of them at its day and price and draws a line at the average price paid; under **My position** they are listed one by one, a sale with what it realised. Each has its own switch.
- **Change a purchase or a sale.** A new entry in an instrument's menu, ✏️ **Change a purchase or sale**, corrects one of them - quantity, price, date, fees, taxes - or takes it out. Until now the only way was to remove it and enter it again. On the card, a click on a purchase or a sale in the details opens its form. A change after which a sale would take out more than was held on its day is refused.
- **Navigate on a click.** **On click** has a third choice beside the pop-up and TradingView: **Navigate**, to a dashboard or a view picked from Home Assistant's own list. The setting is offered for the table as well.
- **Distance to the frame.** Layout → General: how far the card's content stays from its edge. Left empty, the card finds it by itself - see below.

### Changed
- **A table starts sorted by name.** Every other format starts as listed, as before. A choice of your own is kept either way.
- **The symbols and the greying change on the entry.** A price alert that comes on, new headlines, an instrument without a price for a moment: the ticker, the row and the carousel used to build all their entries anew for each of these - and so did every card on the page whenever one sensor came back - and the ticker began again from the start. They are changed on the entry now. Where the entries are built anew - an instrument added, another order - the ticker runs on from where it was and the carousel stays where it was moved to.

### Fixed
- **Content ran across the frame some themes draw inside their cards.** Themes that give a card a bevel of hard inner shadows or an outline a few pixels in had the ticker, the tiles and the table drawn across it, cut off only at the card's edge. The card now reads that frame from the theme and ends its content before it. The card's own background was invisible with such themes as well, because it shared a layer with the theme's outline; it has a layer of its own now.
- **Statistics that had come back in the old currency.** After a new base currency or a changed listing currency, the long-term statistics are cleared. If the change fell into the first seconds of one of the recorder's five-minute windows - or Home Assistant was restarted just after - the window before it was still written, in the old currency, and from then on Home Assistant refused to write the series at all. A few minutes after every start and every change of the settings, the integration now clears the statistics of its sensors that are in another unit than the sensor reports. An installation this has happened to mends itself with the update.

## v1.1.1

Two corrections from the review for the HACS default list.

### Fixed
- **The integration loads on every installation.** The news are read with `defusedxml`, which Home Assistant does not bring along by itself - it was there only where another integration had installed it. On an installation without it, Market Ticker Ultra did not load at all. It is a requirement now and installed with the integration.
- **Uploaded logos are served to who is signed in.** A logo of your own was served from a path that asked for no sign-in: whoever could reach the instance and knew the file's name could fetch it. It now takes a sign-in - or the signature Home Assistant puts on the address the card is given, good for a day. The card asks for new addresses after half that time, when the page comes back into view, and when a picture does not load, so a dashboard on a wall keeps its logos, also across a restart of Home Assistant. The logos from the logo source are not affected.

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
