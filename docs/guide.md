# Jungle Academy: detailed guide

Play at **https://jungle.waozi.xyz**.

Gentle learning games for young children, with watercolor illustrations,
cream book pages, warm colors and quiet feedback. Play with the keyboard, mouse or touch. Made with [Ziran](https://github.com/ziranlang/ziran) and
[Kryon](https://github.com/kryonlabs/kryon).

Jungle Academy is a menu. Each game is its own `.zx` bundle in `games/`, which the
app opens through Kryon's app host. A game keeps its saves in its own folder
under `~/.local/share/jungle/games/`.

Choose **English, Deutsch or Español** with the flag buttons on the title
screen. Jungle remembers the language. Its title screen shares the Picture Book's cream
paper, warm frame, native lettering and watercolor game covers. All games' menus, feedback and
controls are translated. Picture Book has local narration.
A consistent back arrow in the top title bar steps back inside each game and
returns home from its first screen. The sound button at the top right mutes
or unmutes every game.
Accented German and Spanish letters work in Dino stories, saves and exports.

**Picture Book** has thirty-two organized books: Wild animals (15 pictures), Garden
(10), Fruits (16), Farm (20), Kitchen (8), Bathroom (8), Bedroom (8),
Living room (8), Nature (8), Vegetables (16), Family (8), Body Parts (10), Breakfast (8), Lunch (8), Dinner (8), Clothing (12), Seasons (4), Birds (6), Toys (9), Vehicles (6), Bedtime (6), Vacation (6), Sports (7), Beach (6), Weather (6), Feelings (10), Tropical Fruits (8), Gardening (7), School (8), Water Animals (8), Drinks (8), and Actions (8). Browse the framed book list through Animals, Nature, Food, Home and Family tabs. Every page is one gentle watercolor
scene in the style of the title-screen covers: each animal, food or thing sits
in its own setting, so no two pages share a background. Breakfast pages are
drawn in morning light, Lunch at midday and Dinner in the evening. The scene
fills the page and its word sits on a label at the bottom. Choose **Simple** to hear each word once with
its picture, or **Spelling** to hear the word, its letters and the word again.
The selected mode is remembered. Every one of the 284 distinct picture words has names and
both kinds of narration in English, German and Spanish, including correctly
spaced accented letters. Each cover lists its page count. Manually selected pages
speak even when automatic page turns are paused; Hear word repeats the current word.
Browser pictures load before the opening screen clears. Simple pages stay open at least six seconds; spelling pages at least twelve.
Both wait until three seconds after their recording finishes. Tap the right
side of a page or swipe left for the next page; tap the left side or swipe
right for the previous one. Arrows and Enter turn pages too. The back arrow in
the title bar, Escape or right-click returns to the books. Each book ends after its final
picture and shows the next book on the shelf, which opens by itself after a
few seconds; All books returns to the book choices. Back from the first
picture stays there. **Space** or the visible **Play/Pause** button pauses
both narration and automatic page turns, and resumes the same recording.
The title-bar **Speed** button changes pacing without cutting narration short.
The compact bottom toolbar sits directly under the word label, with Play/Pause
and Hear word. **Repeat on/off** in **Manage books** chooses whether to continue
to another book. **Manage books**
on the shelf offers independent **Hide book** and **In autoplay / Skip autoplay**
choices. Hidden books disappear from the shelf and automatic reading; a book
excluded from autoplay remains available to read manually. All choices are
remembered, and selecting no books for autoplay stops at the finish screen.
Each subject belongs to only one of the 284 pages, so playing every book never
repeats a subject. Sports includes badminton, while Actions explores cooking,
cleaning, reading, drawing, singing, washing hands, brushing teeth and watering plants.

**ABC + 123** combines the letter and number books in one menu entry.
Choose **ABC Book** or **123 Book** inside it; Back returns to that choice.
Both open directly into learning, without an activity chooser or a find game.
ABC starts with standalone letter names, spoken in order with a gentle pause
between letters. The title-bar Speed button cycles through normal, fast and slow pacing; each recording finishes before the next letter. Play/Pause controls the sequence; arrows or a letter selection
pause it for exploration. Tap a letter to hear it again. **Examples** optionally
shows the letter on the left and one watercolor word example on the right;
**Next example** cycles through the words and **Spelling** toggles word spelling.
**Letter only** keeps the illustrated example visible while narration speaks
just the letter; **Word audio** returns to spoken examples. Autoplay works in
both views, and **Repeat on/off** chooses whether the alphabet starts again.
Space and Play/Pause pause or resume narration as well as the sequence.
Spanish Ñ sits between N and O.
123 pages show each numeral from one to twenty with its word and that many
watercolor animals. Every number is spoken in the selected language; tap the numeral or press Enter to hear it again. The strip along the bottom reaches every number.
Number autoplay and repeat start on by default. **Play/Pause** or Space pauses
and resumes it; **Repeat on/off** chooses whether twenty returns to one.
Swipe left or right across the number or animals to turn pages. Arrow keys
and number selection also turn pages, keeping the current Play/Pause choice. The title-bar Speed button sets its pace.
Existing saved progress files are preserved.

**Animal Counting** pairs watercolor animals with a clean answer card on
cream paper, with a touch number pad below the animals on phones or beside
them on wider screens. Animals sit in familiar dice patterns of up to five;
six to twenty animals form up to four clearly separated groups of five plus the rest.
The groups adapt to the available space. Its counting rules follow Animal Math. The levels climb
4, 5, 6, 8, 9, 10, 12, 15 and 20, six right answers move up, six misses move
back down, the same number never comes twice, and every eighth right
answer brings one of the original praises, from GOOD JOB to AWESOME.

**Coloring Book** offers 24 starting scenes in Nature, Places and Adventures.
Place any of 46 stencils from Dinosaurs, Animals, People and Objects in four
sizes, then fill the picture with forty-two crayon buttons. The picker remembers
your stencil, category, page, size and mirror choice. Six large previews appear on each numbered page, in two columns on phones or three on wider screens. Previous and Next appear only when that category has another page. Write an eight-line story
and keep pictures in the thumbnail **Gallery**. Edits save automatically;
**Save a copy** keeps another version. **Slots** retains the six original slots.
Undo takes back a placement, fill, rotation or object erasure. The working picture and up to eight undo
steps recover when you reopen the game or reload the browser page. Choose
**Erase**, then tap an object to remove it; the background and other objects
stay intact. **Rotate**, then tap an object, turns it clockwise by a quarter turn
with its paint intact. **New picture** starts a separate gallery picture after
confirmation and a background choice, preserving earlier pictures.
Scenes and dinosaurs are smooth vector line art in `art/paint`, painted
on a 960 by 720 picture. The tools have icons; on a tall screen they sit in
three rows below the picture. Paper galleries and native lettering match the
book theme. New pictures choose a background first. Choose Dinosaurs, Animals, People or Objects at the top of the stencil gallery. Dinosaur selection has no voiceover or voice controls. Quiet sound
effects follow the shared mute setting.

A new stencil starts as a green dashed placement box with a move badge.
The stencil appears on the paper after you place it. Drag it onto the picture and release. Press **Mirror**, or hold
the right mouse button while releasing the left, to mirror the dinosaur.
Its white body covers the lines and colors beneath it, which stay in their own
layers. Erasing the object reveals that artwork again, and Undo restores the
object with its colors. Older flattened saves retain their appearance; objects
added before layers were saved cannot be removed individually. Newly added
objects on those pictures are independent.

**Jigsaw Puzzles** takes inspiration from Artworx's 1990 Amiga game Jigsaw
Puzzle Mania. Choose Tiger stream, Duck pond or Meadow train, with 4, 9, 16,
25, 36 or 64 interlocking pieces. Every loose piece is already its finished
size. Pick up pieces from the scattered table and drag them onto the board,
or leave them anywhere on the table. A piece keeps its size and the place
you grabbed it throughout a drag. Overlapping pieces come to the front when
picked up; correct pieces snap into place. Edge pieces filters the loose
pieces; All pieces brings the middle pieces back.
Peek shows the finished picture for four seconds when peeking is allowed.
Lock on keeps placed pieces fixed; with Lock off, they can be picked up again.
Solo has no turn limit. Team and Competition offer two players one-minute
turns on the same device, with a Next player button to pass early. Competition
also keeps each player's placed-piece score. There is no losing screen.
Progress saves after placements, when leaving and with Save puzzle. Resume
puzzle restores the picture, piece count, stacking order, loose-piece
positions, placed pieces and turns. Older saved puzzles keep their progress.
The shared title-bar Back returns to picture selection, then the main menu.
All controls are available in English, German and Spanish.

The three original puzzle pictures were made with Codex's built-in imagegen
tool. Full-size originals and their prompts live in `art/generated/jigsaw`;
`python3 tools/jigsaw_art.py` prepares the three high-resolution pictures in
`assets/jigsaw`. Every host generates the interlocking piece outlines at runtime
and clips the original picture without distorting it. No pre-cut piece atlases
or separate picture for each difficulty are shipped. No artwork, sound or program
code from the Amiga archive is shipped in this mode.

## Little Piano

A fixed chromatic C3–C6 keyboard provides 37 keys with the same pitches,
layout and A4 = 440 Hz tuning for every song. Smaller screens scroll across
that same keyboard. Tap the song title to choose Alle meine Entchen,
Twinkle Twinkle Little Star, Mary Had a Little Lamb, Frère Jacques or Hot Cross
Buns, using traditional public-domain melodies. A real treble staff shows
beamed eighth notes, quarters, half notes and whole notes, with just the current
lyric line underneath. Practice waits for the matching note; Listen plays the
selected song; Free play opens the full keyboard. The optional **Lesson** mode
plays one lyric phrase first, then waits for your child to repeat it. A filling
bar guides the held note and says when to let go. An early release gently asks
for a longer hold; completing a phrase moves to the next demonstration. The
guided piano is recommended for ages five and up. The 1–8 and A S D F G H J K
shortcuts always address C4–C5; W E T Y U play its black keys. Slow, Normal and
Fast change only the tempo.

Listening and playing share the same quiet triangle-wave tones. Regenerate
the binary WAV assets with `python3 tools/piano_sounds.py`.

## Five more little adventures

**Shapes & Sorting (2+)** starts with large shape targets. Tap an item and its
matching home, or drag it. A whole pointing hand presses a piece, lifts it, drags it into its matching
empty slot and lets go, then pauses for the child. Show me replays the example;
any real input cancels it immediately. Quiet idle help returns after a longer pause. Switch to colors or sizes whenever the child is ready.

**Matching Pairs (2+)** begins with two pairs face up. After discovering a pair,
try optional memory rounds with two, three or four hidden pairs. Harder puzzles
offer six, eight or ten pairs and a short preview. Hints remain available, and
there is no time limit for solving a puzzle.

**Hide & Seek (2+)** offers three levels: Peekaboo introduces friendly animals,
Find gives a position clue, and Remember briefly shows four friends before hiding
them and asking for one by name. Show again repeats the preview without changing
progress. House and yard scenes give each basket, bush, table and tree a grounded place. Completed rounds continue from Peekaboo to Find to Remember, then offer another round. Choose a level at any time; each round mixes the hiding places.

**Little Drums (2+)** opens into a music room. Tap the big drum, little drum,
shaker, bell, xylophone, guitar, cymbal or tambourine where they stand around
the room to hear their distinct sounds. The guitar rests in a stand, shakers sit on a shelf, and the floor tambourine shakes when tapped. The big drum has a stronger body and attack. Empty space does nothing.
Listen & Copy starts with two hits and gradually offers longer
patterns. Copy the order at your own pace; replay and free play are always available.

These ages are flexible guides. Each activity remembers its own learning state,
uses English, German or Spanish, and shares the title bar's Back and sound controls.
The menu supports Home/End, arrows and Enter for every row; number keys select
only the first nine rows.

## Build and run

The main game list is ordered by age, from Picture Book (2+) through Coloring
Book and Little Piano (5+). ABC + 123 and Jigsaw Puzzles are both 3+. Scroll the game list with
the mouse wheel, the scrollbar or a finger; the title, language flags and
sound control stay in place. Arrow keys reveal the selected row.

Needs a C compiler, SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, and Ziran. Dependencies are pinned in `ziran.lock`.

```sh
make            # build/app: the program, its assets and the game bundles
make run
make test       # counting, complete saves, painting, PNGs and printing
make test-ui    # real keyboard/mouse play on a separate virtual display
python3 tests/new_activities_ui_test.py # five new activities, three languages/sizes
node tests/new_activities_web_test.mjs  # private DOM browser interaction
JUNGLE_WEB_PAGE=canvas.html node tests/new_activities_web_test.mjs
make install    # ~/.local/bin/jungle and a menu entry
make web        # Canvas and semantic-DOM browser games in build/web
```

Both browser editions compile the game logic to WebAssembly. The default at
`build/web/index.html` draws through Canvas, as does `build/web/canvas.html`.
`build/web/dom.html` uses native HTML text, buttons, images and CSS for the
interface, with bounded Canvas tiles for custom drawing and texture effects.
Append `?metrics=1` to either edition for live frame timing, JS heap, DOM-node,
Kryon-element and mutation counters. Run `python3 tools/measure_web.py` after
a web build for three runs of representative activities, both idle and active,
with desktop mouse and emulated phone touch. Coloring must change its saved
picture during the active workload. The HTML report at `build/web/performance.html` and complete
JSON include browser process CPU, RSS/PSS, JS/Wasm heaps, rAF cadence, long tasks
and native DOM counts. The samples use isolated headless Chromium with software
graphics; rAF cadence is not application rendering FPS.

The tests need ImageMagick, Python's Pillow package and Ghostscript. UI tests
also need Xvfb and xdotool.
They use temporary saves and never connect to the current desktop. Jungle's
`--check` validates game identities and capabilities without touching saves.
Old Jungle Math counting levels carry over into Animal Counting on startup.

Audio plays quietly by default at one quarter of the former playback gain.
Short triangle-wave cues replace the sharp beeps, and counting rewards use a
brief chime instead of a long song. Click the sound button in the menu or the
title bar, or press F10 anywhere, to mute or unmute. Muting stops queued sounds immediately, and
the setting persists when Jungle reopens.

## Saving, exporting and printing

Gallery opens saved pictures, Save a copy and Slots. Slots opens the original Save and Load choices. Each saved slot shows a small
preview of its picture. Saving over an occupied slot asks before replacing it. Each picture contains its scene, all painted pixels,
dinosaur outlines, crayon selection and eight-line story. Invalid or incomplete
slot files leave the current picture intact. Early palette-only saves still
open with their existing pixels; missing story data from those old files
cannot be recovered.

In the story window, click a position or use the arrows, Home and End to move
the cursor; Backspace and Delete erase characters. Enter or Done returns to
the picture. Lowercase and shifted punctuation use normal keyboard text input.

PRINT offers Export Files and Print. Export writes a PNG, UTF-8 story text and
a color PostScript page together under
`~/.local/share/jungle/games/jungle.paint/exports/` (or the selected XDG/Jungle
data folder). Print submits that page to the system's default CUPS printer
using `lp`. If no printer accepts the job, the exported files are retained and
the game reports that result. Tests substitute a private fake printer and
render the page with Ghostscript, without sending paper jobs.

The forty-two crayons are grouped by hue, with pastels, bright and deep shades,
skin tones and a neutral row ending in dark charcoal. The charcoal stays lighter
than the black outlines. Earlier pictures retain all their original colors.
The scene chooser has six previews per page, Previous/Next controls and a page
count. Its six new scenes are Meadow, Forest, Desert, Snowy hills, Pond and Farmyard.

## Art and sounds

Menu sprites are SVG files in `art/`. `make art` cuts them down to small
sprites in the sixteen colors with Inkscape and ImageMagick, makes the
ASCII and Latin-1 letters from GNU Unifont. Picture Book's pages and the
transparent cut-outs used by Animal Counting and the ABC Book are drawn one
picture at a time with Codex's built-in imagegen tool, in the style of the
title-screen covers (`art/generated/title-covers.png`). Their prompts are kept
in `tools/book_prompts.json`; the pages are 1254 pixel JPEG files in
`assets/jungle-book/pages`. `tools/counting_art.py` makes transparent 128 pixel copies for both counting games,
keeping their full-size sources intact. `tools/book_art.py` makes the book covers from the
first pages and writes the page and narration tables.
`tools/book_catalog.py` owns the category, word and literal letter-name inventory;
`tools/locales.py` compiles `locales/ui.json` into the portable UI translations.
Its recordings are generated through Harmony's reusable `generate_speech` tool
on OpenRouter, using Gemini TTS's Kore voice with gentle delivery and slower,
pitch-preserving playback. Each WAV has a `.speech.json` with the literal word,
spelling, model, voice, speed, measured duration and checksum. No network or
credential is needed while playing.
The original WAVs and their provenance stay in the source tree. Downloads share
artwork and narration clips, encoded as mono 22,050 Hz Ogg Vorbis at quality 4.
Spelled lessons are assembled before playback from their word and letter clips
with the original sample ranges and pauses. Building these derivatives needs
FFmpeg with its libvorbis encoder. The browser edition requires a modern browser
with Vorbis support, including Safari 18.4 or later.
The original Bert's Dinosaurs line art is retained in `art/paint`. New library
pictures are generated individually with built-in image generation; raw sources
and prompts are retained in `art/generated/coloring-stencils`,
`art/generated/coloring-scenes` and `art/generated/coloring-library-prompts.json`.
`python3 tools/paint_catalog.py --art` traces the added library entries without
changing the recovered artwork. `make sounds` retains the original game effects;
`python3 tools/music_room_audio.py --check` verifies the music-room samples and
the four added physical models. Generated output is committed.

`tools/paint_pages.py` compiles the committed PNG line art into portable paint
masks, keeping opaque white bodies separate from ink, and makes previews that
retain thin strokes. The optional Bert importer recovers body masks from the
original full-resolution DOT outlines before reducing them to game pixels.
`make art` also runs this step.

`tools/import_original.py --help` describes optional regeneration from the
original Animal Math table/screens and Bert voice data. It decodes all 24
native counting/reward sprites and can recover the BIOS glyphs from DOSBox.
The decoder was compared with the original program on a private display.
`tools/animal_score.zi` holds the original Animal Fair notes and timing.

## License

Jungle's code is BSD 3-Clause. See [LICENSE](../LICENSE). The menu and Dino letters are drawn from
[GNU Unifont](https://unifoundry.com/unifont/), under the SIL Open Font
License 1.1; see [licenses/unifont.txt](../licenses/unifont.txt). Animal Counting's
BIOS glyphs are recovered from DOSBox; see
[licenses/dosbox-font.txt](../licenses/dosbox-font.txt) and
[licenses/GPL-2.txt](../licenses/GPL-2.txt). Original game artwork and voice data
retain their original authorship.

## Website deployment

Pushes to `master` run the Linux tests and private browser tests for both
editions in GitHub Actions, then publish the same tested website artifact to
Cloudflare Pages. The deployment verifies its revision on `jungle.waozi.xyz`.
The WebAssembly Canvas edition is the default at `/`, also available at
`/canvas.html`. The native DOM edition remains at `/dom.html`. The build generates
its interactive benchmark at `build/web/performance.html`. All editions share the root canonical URL. The repository
secret `CLOUDFLARE_API_TOKEN` grants Pages Edit for the hosting account and
DNS Edit for `waozi.xyz`; credentials are never stored in this repository.
Browser saves stay on that browser in IndexedDB. Menu images load first; book pictures and narration load as needed. Browser printing opens the browser print dialog.

The same browser edition works on itch.io and other static hosts. Run
`python3 tools/prepare_itch.py` after `make web` for `build/itch-web` and the
ready-to-upload `build/jungle-html5.zip`; `index.html` is at the ZIP's root.
The build rejects more than 1,000 files, over 500 MB total, long paths or files
over Cloudflare's stricter 25 MiB limit before either host receives an update.

Game pictures and sounds travel in ordinary ZIP asset packs, grouped by
activity/directory and language, split at 4 MiB of source data. An individual
large picture stays whole. `asset-packs.json` maps each original path to a
pack, byte offset, compressed length, original size, ZIP method and SHA-256.
The browser fetches a pack when an asset is needed and decodes only that entry
with its built-in decompressor. WAV compression is lossless. Web builds use
reviewed quality-90 WebP derivatives for Picture Book and Jigsaw photos only,
at their original dimensions, retaining the original whenever WebP would be
larger. Android and Linux keep their canonical JPEG pictures. Coloring Book
keeps its SVG/PNG artwork and masks on every platform. The seek index keeps
stable game paths and source fingerprints while ZIP entries use their actual
WebP filenames. Duplicate contents share an
entry, and content-named packs remain cacheable across releases. The pack cache
holds at most 16 MiB; simultaneous reads share downloads and failed downloads
can retry. Pack and entry hashes reject damaged content. Menu pictures and
browser icons remain directly accessible for startup and sharing.

The archives can be opened by any standard ZIP reader on desktop or mobile;
the current runtime integration is for browser hosting. APK, AppImage and
portable game bundles retain their existing packaging. No service worker,
HTTP Range support, external asset server or atlas coordinate changes are
needed. `tests/asset_packs_test.py` verifies portable archives and upload gates;
`tests/asset_packs_test.mjs` compares every shipped asset with its source bytes
and exercises integrity failures, retry, deduplication and cache limits.

Linux releases include `jungle-vVERSION-x86_64.AppImage`. Make it executable and
open it; it includes the pictures, narration, fonts and desktop runtime libraries.
On systems without FUSE, use `APPIMAGE_EXTRACT_AND_RUN=1` when launching it.
Build locally with `python3 tools/build_appimage.py` and run its private-display
tests with `python3 tests/appimage_test.py`. GitHub's release workflow verifies
the AppImage before publishing it alongside the Android APK.
