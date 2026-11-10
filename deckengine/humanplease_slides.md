<!--
humanplease-commit: 7f7f2d0225c7b18eba4fae102345dc6f85603d81

Slide-text voice rules, derived from humanplease
(skills/natural-voice-writing/SKILL.md at the commit above; vendored copy in
deckengine/vendor/humanplease/). Appended to every workspace_gen prompt.

The full skill is written for prose ("default to prose", paragraphs), which
does not fit short JSON fields, and small local models follow long rule
lists badly. So this keeps only what applies to eyebrow / title / metric /
bullets / takeaway, and stays under ~1,500 characters (tests enforce it).

Kept from natural-voice-writing: real specifics, the banned-phrase list,
the "not just X, it's Y" construction, no em dashes, no stated moral, the
honest item count, no hype or hedging filler.

From natural-word-choice only the IDEA of banning the words every model
reaches for: its own list is Mad Libs humor words, so the last five banned
words here (synergy … transformative) are pptgpt's slide equivalents. Its
"invent a specific person" and random-seed rules are deliberately NOT used:
on a slide an invented specific is a fabricated fact.

Two forms. The FULL form below goes to larger models. The SHORT form (after
the "short form" comment) goes to small local models (workspace_gen picks by
model size; DECKENGINE_VOICE=full|short|off overrides). On gemma3:4b the
full form cost reliability: failures 2/16 -> 7/16, its [add Q3 revenue]
example got copied into runaway output, and titles came back lowercase
(likely its "say it out loud" opener against the template's casing). The short form keeps only the rules
that moved the eval (no invented facts, the banned words, no em dash / "!" /
"not just X, it's Y", a takeaway that adds something) and has no example
text to copy: a missing fact becomes null, not a placeholder.

Everything here is content guidance. Never geometry, colours or sizes.
Only the text after this comment is sent to the model.
-->
Write every field the way the presenter would say it out loud.
- Use the input's real specifics: names, numbers, products, dates. If a field needs a fact the input does not give, leave it out or write a visible placeholder like [add Q3 revenue] or [owner]. Never invent a number, person, date, quote or source, and keep dates as the input gives them (Q1 stays Q1).
- Never use: delve, tapestry, landscape, realm, testament to, navigate, dive deep, unpack, leverage (as a verb), robust, seamless, game-changer, supercharge, unlock, elevate, curate, journey (unless it is travel), synergy, holistic, empower, cutting-edge, transformative.
- No "it's not just X, it's Y" and no "X isn't about A, it's about B".
- No em dashes. Use a comma, colon or period instead.
- Don't state the moral or tell the room what it means. Let the specifics carry the point. The takeaway adds something; it does not repeat the title.
- One bullet per real point in the input, up to four. Never pad to reach three, and never drop a real point to look tidy.
- Plain words over corporate jargon. No hype, no hedging filler, no exclamation marks, no rhetorical questions.
<!-- short form: for small local models. Everything after this comment. -->
- Use only what the input says. Never add a number, name, date, quote or source it does not give, and keep dates as written (Q1 stays Q1). If a field needs a fact the input lacks, set it to null.
- Never use these words: delve, tapestry, landscape, realm, testament to, navigate, dive deep, unpack, leverage, robust, seamless, game-changer, supercharge, unlock, elevate, curate, journey, synergy, holistic, empower, cutting-edge, transformative.
- No em dashes, no exclamation marks, no "it's not just X, it's Y".
- The takeaway adds a point the title does not make.
