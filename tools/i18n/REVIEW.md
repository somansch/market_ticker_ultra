# Review brief

A translation of the user interface of "Market Ticker Ultra" exists for your
language. You are its reviewer: a native-level editor who knows what broker
and finance apps in that language say. Read BRIEF.md in this folder first -
it holds the rules the translator had. Then review the three files

    out/<code>.card.json   out/<code>.backend.json   out/<code>.extra.json

against the English sources src/*.en.json (src/*.de.json shows the intended
meaning where English is ambiguous). Read every value; do not sample.

Look for, and correct in place:
1. Wrong meaning - a mistranslation, a term taken in the wrong sense
   (examples of traps: "share" is a position's share of the portfolio, not a
   stock; "instrument" is a security, not a tool; "alert is on" means the
   limit is reached, "alert is set" means a limit exists; "listing" is an
   instrument at one exchange; "headline" is a news headline; "holding" is
   what is owned; "realised" gain is from sales; "tiles", "ring", "track",
   "mark" are parts of the card's drawing).
2. Grammar, spelling, diacritics, wrong case or gender agreement, wrong
   plural forms (check every { "fn": ... } for the counts 0, 1, 2, 5, 11,
   21, 22, 101).
3. Inconsistent terms: one thing, one word, across all three files.
4. Unnatural or literal wording a native speaker would not write; wording
   that is not what finance apps in the language use.
5. Labels that grew long: a label of one or two English words should not be
   a phrase. Help texts longer than two sentences, or with added content.
6. Anything left in English that should not be, and anything translated
   that must not be (see BRIEF.md rule 4), broken placeholders.
7. The tone of address: consistent, and as Home Assistant's interface in
   that language has it.

Rules for your corrections: change only what is wrong or clearly better; do
not restyle correct text. Keep keys, order, placeholders, leading emojis,
**bold**. The four chart labels barOpen/barHigh/barLow/barClose must stay
one character each. Write the files with a script or a file-writing tool
(UTF-8, same indentation). Touch only your three files; do not run git.

Afterwards run, and fix until it prints "<code>: ok":

    node tools/i18n/i18n_check.js <code>

Report: the check's last line; how many values you changed in each file; the
most important corrections as "key: before -> after (why)", at most twelve;
and what you would still have a native speaker look at. If you found
nothing worth changing, say so - do not invent corrections.
