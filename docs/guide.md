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

**Picture Book** has twenty-one organized books: Wild animals (15 pictures), Garden
(10), Fruits (16), Farm (20), Kitchen (8), Bathroom (8), Bedroom (8),
Living room (8), Nature (8), Vegetables (16), Family (8), Body Parts (10), Breakfast (6), Lunch (6), Dinner (6), Clothing (12), Seasons (4), Birds (6), Toys (6), Vehicles (6), and Bedtime (6). Browse the framed book list through Nature, Food, Home and Family tabs. Every page is one gentle watercolor
scene in the style of the title-screen covers: each animal, food or thing sits
in its own setting, so no two pages share a background. Breakfast pages are
drawn in morning light, Lunch at midday and Dinner in the evening. The scene
fills the page and its word sits on a label at the bottom. Choose **Simple** to hear each word once with
its picture, or **Spelling** to hear the word, its letters and the word again.
The selected mode is remembered. Every one of the 180 pictures has names and
both kinds of narration in English, German and Spanish, including correctly
spaced accented letters. Each cover lists its page count. Narration is read only when played.
Browser pictures load before the opening screen clears. Simple pages stay open at least six seconds; spelling pages at least twelve.
Both wait until three seconds after their recording finishes. Tap the right
side of a page or swipe left for the next page; tap the left side or swipe
right for the previous one. Arrows and Enter turn pages too. The back arrow in
the title bar, or Escape, returns to the books. Each book ends after its final
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
Birds, Toys, Vehicles and Bedtime each have six pages; familiar pictures can
appear in more than one book without duplicating their recordings.

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
123 pages show each numeral from one to ten with its word and that many
watercolor animals. Every number is spoken in the selected language; tap the numeral or press Enter to hear it again. The strip along the bottom reaches every number.
**Play/Pause** or Space starts and pauses number autoplay; **Repeat on/off**
chooses whether ten returns to one. Arrow keys and number selection pause
the sequence for manual exploration. The title-bar Speed button sets its pace.
Existing saved progress files are preserved.

**Animal Counting** pairs watercolor animals with a clean answer card on
cream paper, with a touch number pad below the animals on phones or beside
them on wider screens. Animals sit in familiar dice patterns of up to five;
six to ten animals form two clearly separated groups, five plus the rest.
The groups adapt to the available space. Its counting rules follow Animal Math. The levels climb
4, 5, 6, 8, 9 and 10, six right answers move up, six misses move
back down, the same number never comes twice, and every eighth right
answer brings one of the original praises, from GOOD JOB to AWESOME.

**Coloring Book** plays like Bert's Dinosaurs. Pick one of twelve scenes across two pages, place
any of twelve dinosaurs, six animals, six people or six objects in four sizes, then fill
the picture with forty-two crayon buttons. You can write an eight-line story
and keep the whole picture and story in one of six slots. Undo takes back the
last dinosaur, fill or erase. The working picture recovers when you reopen the
game. Scenes and dinosaurs are smooth vector line art in `art/paint`, painted
on a 960 by 720 picture. The tools have icons; on a tall screen they sit in
two rows below the picture. Paper galleries and native lettering match the
book theme. New pictures choose a background first. Choose Dinosaurs, Animals, People or Objects at the top of the stencil gallery. Dinosaur selection has no voiceover or voice controls. Quiet sound
effects follow the shared mute setting.

A new stencil starts as a green dashed placement box with a move badge.
The stencil appears on the paper after you place it. Drag it onto the picture and release. Press **Mirror**, or hold
the right mouse button while releasing the left, to mirror the dinosaur.
Its white body replaces the lines and colors beneath it;
scenery outside its outline stays in place. Undo restores the covered artwork.

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
`python3 tools/jigsaw_art.py` makes the high-resolution pictures and smooth,
complementary piece atlases in `assets/jigsaw`. No artwork, sound or program
code from the Amiga archive is shipped in this mode.

## Build and run

The main game list is ordered by age, from Picture Book (2+) through Coloring
Book (5+). ABC + 123 and Jigsaw Puzzles are both 3+. Scroll the game list with
the mouse wheel, the scrollbar or a finger; the title, language flags and
sound control stay in place. Arrow keys reveal the selected row.

Needs a C compiler, SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, and Ziran. Dependencies are pinned in `ziran.lock`.

```sh
make            # build/app: the program, its assets and the game bundles
make run
make test       # counting, complete saves, painting, PNGs and printing
make test-ui    # real keyboard/mouse play on a separate virtual display
make install    # ~/.local/bin/jungle and a menu entry
make web        # browser game in build/web (requires Emscripten)
```

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

SAVE opens separate Save and Load choices. Each saved slot shows a small
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
`assets/jungle-book/pages`. `tools/book_art.py` makes the book covers from the
first pages and writes the page and narration tables.
`tools/book_catalog.py` owns the category, word and literal letter-name inventory;
`tools/locales.py` compiles `locales/ui.json` into the portable UI translations.
Its recordings are generated through Harmony's reusable `generate_speech` tool
on OpenRouter, using Gemini TTS's Kore voice with gentle delivery and slower,
pitch-preserving playback. Each WAV has a `.speech.json` with the literal word,
spelling, model, voice, speed, measured duration and checksum. No network or
credential is needed while playing.
Coloring Book' scenes and dinosaurs are traced from
the original Bert's Dinosaurs artwork into `assets/dino-paint/art` and
`games/paint/paint_pages.zi`. `make sounds` makes the beeps. Both tools are
written in Ziran (`tools/`), and their output is committed. They preserve the
recovered game artwork and recordings.

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

Pushes to `master` run the Linux tests and a private browser test in GitHub
Actions, then publish the same tested website artifact to Cloudflare Pages.
The deployment verifies its revision on `jungle.waozi.xyz`. The repository
secret `CLOUDFLARE_API_TOKEN` grants Pages Edit for the hosting account and
DNS Edit for `waozi.xyz`; credentials are never stored in this repository.
Browser saves stay on that browser in IndexedDB. Menu images load first; book pictures and narration load as needed. Browser printing opens the browser print dialog.

Linux releases include `jungle-vVERSION-x86_64.AppImage`. Make it executable and
open it; it includes the pictures, narration, fonts and desktop runtime libraries.
On systems without FUSE, use `APPIMAGE_EXTRACT_AND_RUN=1` when launching it.
Build locally with `python3 tools/build_appimage.py` and run its private-display
tests with `python3 tests/appimage_test.py`. GitHub's release workflow verifies
the AppImage before publishing it alongside the Android APK.
