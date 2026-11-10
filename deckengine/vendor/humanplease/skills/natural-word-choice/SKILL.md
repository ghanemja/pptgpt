---
name: natural-word-choice
description: Use when picking open-ended words or examples where a person would pick something personal and unpredictable (filling in Mad Libs or other blanks, inventing names, examples, sample data, jokes or "random" picks), so the choices don't fall back on the same stock words every model reaches for.
---

# Natural word choice

Found by an optimization loop on the Mad Libs Turing test in [Doodle Libs](https://github.com/ghanemja/madlibs) (see `research/OPTIMIZATION.md` there). On 10 held-out stories it cut how often Claude gives the same answer to the same blank from 49.2% to 14.0%. People are at 1.0%, so it gets the model closer to human, not all the way.

## Word choice

Real people choose words from their own lives: their hometown, their job, the snack in their bag, a cousin's weird hobby. Before choosing words for a fill-in or an example, silently invent one specific person to be (age, hometown, job, one odd obsession), choosing an unusual combination rather than a typical one. Then pick each word the way that person would, from things in their world. Do not mention the person in your answer.

The words a model reaches for when it tries to be funny are a giveaway, because every model reaches for the same ones. Unless the sentence truly needs one, do not use: casserole, moist, soggy, sandwich, pickle, tickle, toaster, llama, hamster, squishy, slimy, sweaty, suspicious, armpit, accordion, goat, pigeon, grandma, burrito, spaghetti, banana, yodel, interpretive dance, rubber duck, notarized permission slip.

Models invent the same "unusual" person over and over. To break that, start from chance: silently pick a random letter of the alphabet and a random number from 1 to 99. The person's first name starts with that letter, their age is that number (or the last two digits of it, if that would make them a toddler), and their job starts with the second letter after it. Build their world from there.
