# Jungle Academy

Jungle is for babies and toddlers. Every picture, sound and screen should feel
friendly, gentle and obvious.

## Narration voices (owner feedback, 2026-11-02)

- All English app narration uses locally generated Kokoro `af_bella`.
- Offer three generated profiles: slow `0.65`, normal `0.8` (default), fast `1.0`.
  Select the generated profile assets; do not stretch playback or estimate timing.
- Keep voice selections in `speech.json`; `assets/speech-profiles.json` maps
  the generated English profiles. The general male voice preference remains
  `am_michael`; it does not override the app's all-English Bella narration.

## Picture art (owner feedback, 2026-10-26)

- **AVIF is standard for every runtime/generated image:** export through
  `tools/image_exports.py` (8-bit, full range, speed 6, one encoder thread).
  Owner standard (2026-11-05, the approved tiger page: 270 KB WebP -> 31 KB):
  Lanczos-downscale the master to 75% of its size, then AVIF q35. Opaque art is
  YUV420; transparent cut-outs, layers and glows use YUV444 color with q90
  alpha so edges stay clean; one-color glows keep their single color. Authoring
  tools draw at painting size and write through `save_shipped_cutout`, which
  applies a scaled row's 75% standard. Hosts draw every picture into its layout
  rectangle, so the smaller texture keeps its on-screen size; record the
  design size (`design_dimensions` in `tools/canonical_avif.json`) wherever
  layout data needs painting pixels, such as the story paper line.
  Pictures under 512 px, source-rectangle sheets (window animation, frame,
  sky occluder), paint art, cursors and the Farm (its fields are traced in painting
  pixels) keep their pixels: q70 YUV444 with exact
  alpha (export role `cutout`). Jigsaw paintings and small menu icons (role `icon`) use q60 YUV444.
  Role `exact` is lossless and keeps every RGBA value, hidden RGB included; use it
  only where pixels must survive unchanged, such as tiny opaque art and stencils.
  A re-export ships only if it is smaller than the file it replaces.
  Keep canonical masters in ignored `local/art-development/`; ship only AVIF.
  PNG is reserved for the exact technical exceptions in
  `tools/asset_png_allowlist.json`; `tests/avif_standard_test.py` enforces this.
- **One style everywhere:** the title-screen cover style,
  `local/art-development/title-covers.png`: soft cartoonish storybook watercolor on
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
- **Always optimize new images** (owner feedback, 2026-11-02): use
  `tools/image_exports.py` in generation/export workflows. Preserve canonical
  full-resolution originals and review candidates in ignored `local/art-development/`.
  Never track generated originals, candidates or review outputs. Integrate only
  owner-approved runtime AVIFs under `assets/`; builds and CI must work without
  the development folder. Keep required provenance metadata in
  `tools/art_provenance/`. New art follows the 75%
  q35 standard above. Reuse existing AVIF without another lossy encode.
  Only explicit previews, established derivatives and the 75% standard may resize. Optimization does
  not approve changed artwork: retain the before/after owner choice.
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

Pages live in `assets/jungle-book/pages` (1254 px masters, 940 px AVIF) and cut-outs for
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

- The title screen is the painted treehouse (no list): the bookshelf leads to
  the books (Picture Book, ABC Book, 123 Book), a ladder down to the jungle
  campus and from there into the music room; every game opens from a painted
  item. Hovering an item glows exactly that item; a tap glows briefly, then
  opens it. Scenes and hotspots come from `tools/title_hotspots.json` through
  `tools/title_scenes.py`; only small flags and the sound button sit on top.
- The first Treehouse room is a clean background plate with every piece of
  furniture as its own transparent layer (`"objects"` in
  `tools/title_hotspots.json`, drawn in list order). Customize it by adding,
  moving or swapping a layer, then run `python3 tools/title_scenes.py`;
  hotspots with `"object"` follow their layer. `tools/title_room.py` rebuilds
  the layers from the ignored masters in `local/art-development/treehouse-room/`.
  No picture board hangs above the ladder. The round window opens a look-only
  view outside with only the top-left Back button.
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

- Title scenes use separate signposts: sideways arrow-shaped wooden planks
  (left or right) with clean intact ends and localized names, pointing along
  the actual route. The one upright plank is Campus's sign up its path to the
  Jungle Path. Farm points LEFT at Campus; retain no old floating navigation
  arrows or testing rooms/strips. Keep shared title-bar Back.
- The Beach is the Port (scene id port; "beach" stays an alias). Campus leads
  up to the tropical Jungle Path (tools/title_places.py): its parrot, sloth and
  butterfly only glow; right returns to Campus, left goes on to the Port. The
  Port's right-hand sandy path leads to the Market, a text-free shopping street
  whose animal shops only glow; its left sign returns to the Port and its right
  sign opens the Farm game, whose own left-edge path sign goes back to the
  Market (AppService "jungle.home" "scene:market"). Path edits regenerate only
  a crop around the join (local/art-development/market, campus-object-layers).
  Desert (Wüste, tools/title_desert.py) looks like the world map: white dunes,
  a turquoise lagoon oasis and a giant tree at the left whose one branch
  reaches only about half the width (portrait adds a shorter lower-crown
  limb), painted without birds. Every bird is its own cut-out layer (no camel
  or person), laid out along the measured limb lines in PERCHES; tapping
  any opens the parrots' tap-through speech bubble beside the macaw
  (tools/title_dialogue.json, EN/DE/ES, narrated), never a caption along the
  bottom. A left plank returns to Campus.
- Campus uses portrait-jungle-path-between (portrait-connected-desert-right
  with its Jungle Path starting between the treehouse and the music hut, the
  old left path removed and the frogs on the rocks; Farm left, Desert right) and
  landscape-connected-no-stones-proposal (clean sandy path across to the left,
  no stepping stones). Farm shows only owner-selected 27.png landscape and
  19.png portrait from owner-farm-beach-source, as the Farm subapp's full-screen
  garden chooser with a right-pointing Campus return sign and no game title bar.
  Garden play has free seed drag-and-drop and no text tutorial, help screen or
  crop-field messages; preserve jungle.garden identity and leave existing garden.txt saves untouched.
  The Port uses the approved clean plates plus its Market path. Keep originals private and ship AVIFs.
- Farm entrance fields (tools/farm_fields.py, run after the painting changes;
  make test runs --check) find each raised bed in the painting: the whole bed
  is the hover outline and an exact-alpha glow, the soil's four corners are where
  crops stand in perspective. The fields carry no labels or numbers.
- Keep fast unit tests and one local native smoke test in both orientations.
  Retired browser/UI CI gate suites and testing-room fixtures must not return.
