// Writes the sources the translations are made from: the card's English and
// German string tables and the integration's two translation files, as JSON
// under tools/i18n/src. Run it after English or German changed.
//
// A card string that is a function - a plural, a sentence with a number in
// it - is written as { "fn": "<its JavaScript source>" }.
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..", "custom_components", "market_ticker_ultra");
const card = fs.readFileSync(path.join(root, "frontend", "market-ticker-ultra-card.js"), "utf8");

function tableOf(source) {
  const start = source.indexOf("  const STRINGS = {");
  const end = source.indexOf("\n  };", start);
  if (start < 0 || end < 0) throw new Error("STRINGS table not found");
  return new Function(source.slice(start, end + 5) + "\nreturn STRINGS;")();
}

function plain(block) {
  const out = {};
  for (const [key, value] of Object.entries(block)) {
    out[key] = typeof value === "function" ? { fn: value.toString() } : value;
  }
  return out;
}

const strings = tableOf(card);
const src = path.join(__dirname, "src");
fs.mkdirSync(src, { recursive: true });
for (const lang of ["en", "de"]) {
  fs.writeFileSync(path.join(src, `card.${lang}.json`), JSON.stringify(plain(strings[lang]), null, 2) + "\n");
  fs.copyFileSync(path.join(root, "translations", `${lang}.json`), path.join(src, `backend.${lang}.json`));
}
console.log("card keys:", Object.keys(strings.en).length, "de:", Object.keys(strings.de).length);
const missing = Object.keys(strings.en).filter((key) => !(key in strings.de));
if (missing.length) console.log("not in de:", missing.join(", "));

module.exports = { tableOf, plain };
