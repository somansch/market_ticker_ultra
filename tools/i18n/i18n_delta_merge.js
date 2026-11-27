// Takes a language's translation of what changed since the last release -
// delta-v200/<code>.delta.card.json and <code>.delta.backend.json, with the
// keys of delta.card.en.json and delta.backend.en.json beside them - checks it
// and puts it into out/<code>.card.json and out/<code>.backend.json, in the
// order of the English sources.
//
//   node tools/i18n/i18n_delta_merge.js <code> [<code> ...]
//   node tools/i18n/i18n_delta_merge.js --check <code>   (checks only)
//
// A backend key is a path, its parts joined by " > ".
const fs = require("fs");
const path = require("path");

const dir = __dirname;
// The folder the delta lives in: the English and German delta of a release
// and every language's translation of it.
const DELTA = "delta-v200";
const read = (file) => JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"));
const write = (file, value, indent) => fs.writeFileSync(path.join(dir, file), JSON.stringify(value, null, indent) + "\n");
const braces = (text) => (String(text).match(/\{[a-z_]+\}/g) || []).slice().sort().join(" ");

function faults(code) {
  const found = [];
  for (const part of ["card", "backend"]) {
    const en = read(`${DELTA}/delta.${part}.en.json`);
    const file = `${DELTA}/${code}.delta.${part}.json`;
    if (!fs.existsSync(path.join(dir, file))) {
      found.push(`${file}: missing`);
      continue;
    }
    let mine;
    try {
      mine = read(file);
    } catch (err) {
      found.push(`${file}: not JSON - ${err.message}`);
      continue;
    }
    for (const key of Object.keys(en)) if (!(key in mine)) found.push(`${file}: key missing: ${key}`);
    for (const key of Object.keys(mine)) if (!(key in en)) found.push(`${file}: key not in the source: ${key}`);
    for (const [key, source] of Object.entries(en)) {
      const value = mine[key];
      if (value === undefined) continue;
      if (source && typeof source === "object") {
        if (!value || typeof value !== "object" || typeof value.fn !== "string") {
          found.push(`${file}: ${key} must be { "fn": "..." }`);
          continue;
        }
        try {
          const made = new Function(`return (${value.fn});`)();
          if (typeof made !== "function") throw new Error("not a function");
          // The functions here take a count or two texts: both must give a text.
          const said = made(2, "x");
          if (typeof said !== "string" || !said) throw new Error("returns no text");
        } catch (err) {
          found.push(`${file}: ${key} is not a working function - ${err.message}`);
        }
        continue;
      }
      if (typeof value !== "string" || !value.trim()) {
        found.push(`${file}: ${key} is empty or not a text`);
        continue;
      }
      if (braces(value) !== braces(source)) found.push(`${file}: ${key} placeholders differ: ${braces(source)} / ${braces(value)}`);
      const emoji = /^\p{Extended_Pictographic}/u;
      if (emoji.test(source) && !value.startsWith(Array.from(source)[0])) found.push(`${file}: ${key} lost its leading emoji`);
    }
  }
  return found;
}

function merge(code) {
  // The card: a flat table, in the English order.
  const cardEn = read("src/card.en.json");
  const card = read(`out/${code}.card.json`);
  const cardNew = read(`${DELTA}/${code}.delta.card.json`);
  const cardOut = {};
  for (const key of Object.keys(cardEn)) {
    if (key in cardNew) cardOut[key] = cardNew[key];
    else if (key in card) cardOut[key] = card[key];
  }
  write(`out/${code}.card.json`, cardOut, 2);
  // The dialogs: nested, in the English order.
  const backEn = read("src/backend.en.json");
  const back = read(`out/${code}.backend.json`);
  const backNew = read(`${DELTA}/${code}.delta.backend.json`);
  const ordered = (source, mine, trail) => {
    const out = {};
    for (const [key, value] of Object.entries(source)) {
      const here = trail.concat(key);
      const name = here.join(" > ");
      if (value && typeof value === "object") {
        out[key] = ordered(value, (mine && mine[key]) || {}, here);
      } else if (name in backNew) {
        out[key] = backNew[name];
      } else if (mine && key in mine) {
        out[key] = mine[key];
      }
    }
    return out;
  };
  write(`out/${code}.backend.json`, ordered(backEn, back, []), 4);
}

const args = process.argv.slice(2);
const only = args[0] === "--check";
const codes = only ? args.slice(1) : args;
if (!codes.length) throw new Error("which language?");
let bad = false;
for (const code of codes) {
  const found = faults(code);
  if (found.length) {
    bad = true;
    console.log(`${code}: ${found.length} fault(s)`);
    for (const line of found.slice(0, 40)) console.log("  " + line);
    continue;
  }
  if (!only) merge(code);
  console.log(`${code}: ok${only ? "" : ", merged"}`);
}
process.exitCode = bad ? 1 : 0;
