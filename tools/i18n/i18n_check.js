// Checks one language's translation files under tools/i18n/out against the
// English sources: node tools/i18n/i18n_check.js <code> [<code> ...]
//
// It checks structure - the keys, the {placeholders}, that a function still
// is one and answers with text - not the wording.
const fs = require("fs");
const path = require("path");

const dir = __dirname;
const read = (file) => JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"));
const flat = (node, prefix = "", out = {}) => {
  for (const [key, value] of Object.entries(node)) {
    if (value && typeof value === "object" && !("fn" in value)) flat(value, `${prefix}${key}.`, out);
    else out[prefix + key] = value;
  }
  return out;
};
const holders = (text) => (String(text).match(/\{[a-z_]+\}/g) || []).sort().join(",");
const emoji = (text) => (String(text).match(/^\p{Extended_Pictographic}️?/u) || [""])[0];
const SAMPLES = { names: "Apple, Tesla", name: "Apple", v: "43M" };

function check(code) {
  const faults = [];
  for (const part of ["card", "backend", "extra"]) {
    let source, target;
    try {
      source = flat(read(`src/${part}.en.json`));
      target = flat(read(`out/${code}.${part}.json`));
    } catch (err) {
      faults.push(`${part}: ${err.message}`);
      continue;
    }
    for (const key of Object.keys(source)) {
      if (!(key in target)) {
        faults.push(`${part}: missing ${key}`);
        continue;
      }
      const from = source[key];
      const to = target[key];
      if (from && typeof from === "object") {
        if (!to || typeof to !== "object" || typeof to.fn !== "string") {
          faults.push(`${part}: ${key} must stay { "fn": ... }`);
          continue;
        }
        try {
          const made = new Function(`return (${to.fn});`)();
          const params = (from.fn.match(/^\(([^)]*)\)/) || ["", ""])[1].split(",").map((p) => p.trim());
          for (const count of [0, 1, 2, 3, 5, 11, 21, 22, 25, 101]) {
            const args = params.map((p) => (p in SAMPLES ? SAMPLES[p] : p === "of" ? 30 : count));
            const text = made(...args);
            if (typeof text !== "string" || !text.trim() || /undefined|NaN|\[object/.test(text)) {
              faults.push(`${part}: ${key} answers ${JSON.stringify(text)} for ${JSON.stringify(args)}`);
              break;
            }
          }
          if (params.some((p) => p in SAMPLES) && !made(...params.map((p) => SAMPLES[p] || 2)).includes(SAMPLES[params.find((p) => p in SAMPLES)])) {
            faults.push(`${part}: ${key} drops its argument`);
          }
        } catch (err) {
          faults.push(`${part}: ${key} is not a function: ${err.message}`);
        }
        continue;
      }
      if (typeof from === "boolean") {
        if (typeof to !== "boolean") faults.push(`${part}: ${key} must be true or false`);
        continue;
      }
      if (typeof to !== "string" || (from !== "" && !to.trim())) {
        faults.push(`${part}: ${key} is empty or no text`);
        continue;
      }
      if (holders(from) !== holders(to)) faults.push(`${part}: ${key} placeholders ${holders(to)} instead of ${holders(from)}`);
      if (emoji(from) !== emoji(to)) faults.push(`${part}: ${key} must start with ${emoji(from) || "no emoji"}`);
      if ((from.match(/\*\*/g) || []).length !== (to.match(/\*\*/g) || []).length) faults.push(`${part}: ${key} lost or gained **bold**`);
      if (/https?:\/\//.test(to)) faults.push(`${part}: ${key} holds a URL`);
    }
    for (const key of Object.keys(target)) if (!(key in source)) faults.push(`${part}: unknown key ${key}`);
  }
  return faults;
}

let bad = 0;
for (const code of process.argv.slice(2)) {
  const faults = check(code);
  bad += faults.length;
  console.log(faults.length ? `${code}: ${faults.length} fault(s)\n  ${faults.join("\n  ")}` : `${code}: ok`);
}
process.exit(bad ? 1 : 0);
