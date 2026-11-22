// Builds the integration's languages from tools/i18n:
//
//   node tools/i18n/i18n_build.js            every language under out/
//   node tools/i18n/i18n_build.js --none     English and German only
//
// English and German are written by hand where they are used - in the card's
// STRINGS table, in translations/en.json and de.json, in src/extra.*.json.
// Every other language comes from out/<code>.{card,backend,extra}.json and
// is written to three places:
//
//   translations/<code>.json                    the integration's dialogs
//   frontend/market-ticker-ultra-card.js        between the two i18n marks
//   localized.py                                what Python says itself
//
// A language whose files do not pass i18n_check.js is left out, and named.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const dir = __dirname;
const root = path.join(dir, "..", "..", "custom_components", "market_ticker_ultra");
const read = (file) => JSON.parse(fs.readFileSync(file, "utf8"));

let codes = [];
if (!process.argv.includes("--none")) {
  codes = fs
    .readdirSync(path.join(dir, "out"))
    .filter((name) => name.endsWith(".card.json"))
    .map((name) => name.slice(0, -".card.json".length))
    .sort();
}
const good = [];
for (const code of codes) {
  try {
    execFileSync(process.execPath, [path.join(dir, "i18n_check.js"), code], { stdio: "pipe" });
    good.push(code);
  } catch (err) {
    console.log(`left out: ${code}\n${String(err.stdout || err.message).trim()}`);
  }
}

// 1. The integration's dialogs.
for (const code of good) {
  const data = read(path.join(dir, "out", `${code}.backend.json`));
  fs.writeFileSync(path.join(root, "translations", `${code}.json`), JSON.stringify(data, null, 4) + "\n");
}

// 2. The card: one block per language between the marks.
const BEGIN = "    // i18n:begin - written by tools/i18n/i18n_build.js, not by hand\n";
const END = "    // i18n:end\n";
const cardFile = path.join(root, "frontend", "market-ticker-ultra-card.js");
let card = fs.readFileSync(cardFile, "utf8");
const key = (name) => (/^[A-Za-z_$][\w$]*$/.test(name) ? name : JSON.stringify(name));
let blocks = "";
for (const code of good) {
  const data = read(path.join(dir, "out", `${code}.card.json`));
  blocks += `    ${JSON.stringify(code)}: {\n`;
  for (const [name, value] of Object.entries(data)) {
    const text = value && typeof value === "object" ? value.fn : JSON.stringify(value);
    blocks += `      ${key(name)}: ${text},\n`;
  }
  blocks += "    },\n";
}
const from = card.indexOf(BEGIN);
const to = card.indexOf(END);
if (from < 0 || to < from) throw new Error("i18n marks not found in the card");
card = card.slice(0, from + BEGIN.length) + blocks + card.slice(to);
fs.writeFileSync(cardFile, card);

// 3. What Python says itself.
const table = {};
for (const code of ["en", "de"]) table[code] = read(path.join(dir, "src", `extra.${code}.json`));
for (const code of good) table[code] = read(path.join(dir, "out", `${code}.extra.json`));
const py = (value) => (typeof value === "boolean" ? (value ? "True" : "False") : JSON.stringify(value));
let python = `"""What the integration says in its own words, by language.

Written by tools/i18n/i18n_build.js - not by hand. English and German come
from tools/i18n/src/extra.*.json, the others from tools/i18n/out.

These are the texts no translation file reaches: a price alert's default
words, sent by the integration itself, and the names of what a new
installation starts with. They follow Home Assistant's own language.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

TEXTS: dict[str, dict[str, Any]] = {
`;
for (const [code, data] of Object.entries(table)) {
  python += `    ${JSON.stringify(code)}: {\n`;
  for (const [name, value] of Object.entries(data)) python += `        ${JSON.stringify(name)}: ${py(value)},\n`;
  python += "    },\n";
}
python += `}

# A language Home Assistant names otherwise than the table does.
_ALIASES = {"pt": "pt-BR", "zh": "zh-Hans", "no": "nb", "nn": "nb"}


def language_of(hass: HomeAssistant) -> str:
    """The table's language for Home Assistant's own - English where it has
    none."""
    wanted = (hass.config.language or "en").replace("_", "-")
    if wanted in TEXTS:
        return wanted
    short = wanted.split("-")[0].lower()
    if short in TEXTS:
        return short
    return _ALIASES.get(short, "en") if _ALIASES.get(short) in TEXTS else "en"


def text(hass: HomeAssistant, key: str) -> str:
    return str(TEXTS[language_of(hass)].get(key) or TEXTS["en"][key])


def decimal_comma(hass: HomeAssistant) -> bool:
    """Whether the language writes 1,5 for one and a half."""
    return bool(TEXTS[language_of(hass)].get("decimal_comma"))
`;
fs.writeFileSync(path.join(root, "localized.py"), python);

console.log(`built: en, de${good.length ? ", " + good.join(", ") : ""} (${good.length + 2} languages)`);
