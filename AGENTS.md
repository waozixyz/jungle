# Jungle Academy

Jungle is for babies and toddlers. Every picture, sound and screen should feel
friendly, gentle and obvious.

## Picture art (owner feedback, 2026-10-26)

- **One style everywhere:** the title-screen cover style,
  `art/generated/title-covers.png`: soft cartoonish storybook watercolor on
  warm cream paper, delicate botanical leaves, gentle earthy colors, friendly
  young animals with big gentle eyes. Use its tiger cover as the style
  reference for every picture. Use simplified rounded forms and smooth washes,
  without realistic wrinkles, skin texture or sharply detailed features.
  Vary the angles, favoring forward and three-quarter views with naturally
  upright heads. Their eyes look slightly past the viewer or toward nearby
  surroundings, without staring directly at the viewer. Do not make every
  animal a sideways profile or give every animal a lowered head. Keep
  natural animal anatomy and calm poses. Apply this to
  every existing animal scene, counting cut-out and animal cover. Never draw
  realistic, staring or toothy
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
- Picture Book has a compact bottom toolbar directly below the word label,
  with Play/Pause and Hear word. Keep Repeat on/off in Manage books, never
  on the picture page.
- The end-of-book screen that offers the next book must be styled as
  carefully as the book pages.
- Coloring Book save and load slots show a preview of each saved picture, so
  it is obvious which picture a slot holds.
- A new Coloring Book picture chooses its background before an animal,
  person or object. Saved pictures reopen with their existing background.
- The stencil gallery has Dinosaurs, Animals, People and Objects sections,
  including placeable objects such as crates and campfires.

- ABC and 123 share one ABC + 123 entry, with both books inside. Keep their
  existing saved progress. Menu text must fit within each row at every window
  size; use one centered title when a row cannot hold its description.
- Picture Book includes Clothing and Seasons, with the same full-scene art
  and complete English, German and Spanish names and narration as every book.

- ABC and 123 open directly into learning. No extra activity chooser or Find game.
- Animal Counting progresses gently through twenty animals, arranged in groups of five.
- Use Kryon's shared TitleBar with Back and sound controls.
- Coloring Book Back leaves directly and preserves the working picture; no Yes/No exit dialog.
- The first row of Animals and People uses the same polished generated line-art style as the second row.
- Each new release includes an AppImage built and tested in GitHub CI, published alongside the APK.

- ABC defaults to standalone spoken letter names in alphabet order, with a gentle sequence and Play/Pause. Word examples are optional; their layout separates the letter on the left from a picture and example word on the right. Spanish Ñ belongs between N and O.

- Animal faces keep natural anatomy, without human smiles, lips, eyebrows or eyelashes. The snail has exactly two eyes, only on its long upper eyestalks. Bees, spiders and butterflies keep natural insect/arachnid features. The owner approved the six corrected scene/cut-out pairs (snail, elephant, giraffe, bee, spider, butterfly).

- Picture Book pages and optional ABC examples use actual full-scene backgrounds. Cut-outs remain available for counting; standalone alphabet practice uses plain paper.

- Show the complete English, German (Ä Ö Ü ß included) and Spanish (Ñ included) alphabets at every size; no shortened alphabet strip. Show uppercase ẞ with lowercase ß on its letter page.
- 123 Book speaks each selected number from one to twenty in the active language, on entry, selection and tap-to-repeat.

- 123 Book opens with autoplay and repeat on by default. Swipes, arrows and number selection keep the current Play/Pause choice. Counting games load 128 px transparent derivatives; preserve the full-size artwork.
