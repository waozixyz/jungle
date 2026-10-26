# Jungle Academy

Jungle is for babies and toddlers. Every picture, sound and screen should feel
friendly, gentle and obvious.

## Picture art (owner feedback, 2026-10-26)

- **One style everywhere:** the title-screen cover style,
  `art/generated/title-covers.png`: soft naturalistic storybook watercolor on
  warm cream paper, delicate botanical leaves, gentle earthy colors, friendly
  young animals with big gentle eyes. Use its tiger cover as the style
  reference for every picture. Never draw realistic, staring or toothy
  animals; they are too scary for babies.
- **Pages like a touch-and-learn book** (owner screenshot,
  `backup/reference/touch-and-learn-book.png`): each page is one complete
  scene with the subject sitting or standing naturally in its own setting,
  so every page has a different background. Draw the scene with the subject,
  not as a cut-out pasted over a shared backdrop.
- **Pilot first:** redraw one book (Wild animals first) and get the owner's
  choice before drawing the others.
- **Before/after, owner chooses:** an art change replaces nothing until the
  owner has seen the before and after of every affected picture side by side
  and picked a version for each one. Keep the candidates until then.
- **Generate with Codex** (built-in image generation), one picture per image,
  never cut from a grid atlas. Pictures that must be cut out use a truly
  transparent background.
- **Clean cut-outs:** no leftover white paper, painted ground patches, halos
  or other generation artifacts around a subject (plates, cups, soap…).
- **High resolution:** a page fills most of the screen, so ship pictures
  that stay sharp at that size, never 420 px pictures stretched up.
- **Believable scale:** keep relative sizes where pictures are compared, for
  example the baby is much smaller than the adults in Family.
- **Nothing floats:** an object must never hover in front of a scene it does
  not belong to (food above a table, a spoon in mid-air in a kitchen). If a
  picture does not sit naturally in a scene, put it on a generic picture
  background instead.
- **Varied backgrounds:** pages and books must not all repeat the same
  background.
- **Time of day:** Breakfast pages look like morning, Lunch like midday and
  Dinner like evening.

Pages live in `assets/jungle-book/pages` (1254 px JPEG) and cut-outs for
Animal Counting and the ABC Book in `assets/jungle-book/items`. Every prompt
is in `tools/book_prompts.json`; the full-size originals are kept in
`backup/picture-book-scenes/`.

## Screens

- A book page is the whole scene filling the page, with the word on top of
  the picture. No Books or arrow buttons: tap the left or right side of the
  page to turn it, and the title bar's back arrow returns to the books.
- The title bar has the sound on/off button at the top right.
- The end-of-book screen that offers the next book must be styled as
  carefully as the book pages.
- Coloring Book save and load slots show a preview of each saved picture, so
  it is obvious which picture a slot holds.
- A new Coloring Book picture chooses its background before an animal,
  person or object. Saved pictures reopen with their existing background.
- The stencil gallery has Dinosaurs, Animals, People and Objects sections,
  including placeable objects such as crates and campfires.
