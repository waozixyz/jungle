# Jungle Academy

Play at **https://jungle.waozi.xyz**.

Gentle learning games for young children, with watercolor illustrations,
cream book pages, warm colors and quiet feedback. Play with the keyboard, mouse or touch. Made with [Ziran](https://github.com/ziranlang/ziran) and
[Kryon](https://github.com/kryonlabs/kryon).

Jungle Academy is a menu. Each game is its own `.zx` bundle in `games/`, which the
app opens through Kryon's app host. A game keeps its saves in its own folder
under `~/.local/share/jungle/games/`.

Choose **English, Deutsch or Español** with the flag buttons on the title
screen. Jungle remembers the language. Its title screen shares the Picture Book's cream
paper, warm frame, native lettering and watercolor game covers. All three games' menus, feedback and
controls are translated. Picture Book has local narration.
Accented German and Spanish letters work in Dino stories, saves and exports.

**Picture Book** has ten organized books: Wild animals (15 pictures), Garden
(10), Fruits (16), Farm (20), Kitchen (8), Bathroom (8), Bedroom (8),
Living room (8), Nature (8), and Vegetables (16). Browse the original grouped book list in a responsive scrollable shelf, with Animals and nature, Food, and At home sections. Portrait pages stack the full illustration and word; landscape pages place them side by side. Choose **Simple** to hear each word once with
its picture, or **Spelling** to hear the word, its letters and the word again.
The selected mode is remembered. Every one of the 117 pictures has names and
both kinds of narration in English, German and Spanish, including correctly
spaced accented letters. Pictures sit on cream pages inside the original warm book frame.
Simple pages stay open at least six seconds; spelling pages at least twelve.
Both wait until three seconds after their recording finishes. Swipe left for
the next page and right for the previous page. Arrows, Enter or a picture tap
turn pages too; Books or Escape returns to the categories. Pages show the
picture and word without a category heading or page counter. Each book ends
after its final picture and suggests another book. After a short finish screen,
the next book opens automatically; All books returns to the book choices. Back from the first picture stays there.

**Animal Counting** pairs watercolor animals with a clean answer card on
cream paper, with a touch number pad below the animals on phones or beside
them on wider screens. Its counting rules follow Animal Math. The levels climb
4, 5, 6, 9, 12 and 18, six right answers move up, six misses move
back down, the same number never comes twice, and every eighth right
answer brings one of the original praises, from GOOD JOB to AWESOME.

**Dino Colors** plays like Bert's Dinosaurs. Pick one of six scenes, place
any of twelve dinosaurs in four sizes, then fill
the picture with thirty crayon buttons. You can write an eight-line story
and keep the whole picture and story in one of six slots. Undo takes back the
last dinosaur, fill or erase. The working picture recovers when you reopen the
game. Scenes and dinosaurs are smooth vector line art in `art/paint`, painted
on a 960 by 720 picture. The tools have icons; on a tall screen they sit in
two rows below the picture. Paper galleries and native lettering match the
book theme. Dinosaur selection has no voiceover or voice controls. Quiet sound
effects follow the shared mute setting.

A new dinosaur waits in the upper-left corner in a green dashed box with a
move badge. Drag it onto the picture and release. Press **Mirror**, or hold
the right mouse button while releasing the left, to mirror the dinosaur.
Its white body replaces the lines and colors beneath it;
scenery outside its outline stays in place. Undo restores the covered artwork.

## Build and run

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
brief chime instead of a long song. Click the sound button in the menu or press
F10 anywhere to mute or unmute. Muting stops queued sounds immediately, and
the setting persists when Jungle reopens.

## Saving, exporting and printing

SAVE opens separate Save and Load choices. Saving over an occupied slot asks
before replacing it. Each picture contains its scene, all painted pixels,
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

The thirty crayons reproduce the original fifteen solid VGA colors and their
fifteen checkerboard fills. Earlier sixteen-color saves retain their palette.

## Art and sounds

Menu sprites are SVG files in `art/`. `make art` cuts them down to small
sprites in the sixteen colors with Inkscape and ImageMagick, makes the
ASCII and Latin-1 letters from GNU Unifont. Picture Book's pages are cut from a watercolor atlas generated with Codex's
built-in imagegen tool, following the owner's illustrated jungle-book reference.
The source, generation prompt and reference stay in `art/generated/`.
`tools/book_art.py` cuts its individual illustrations and category covers.
The 42 pages include ten more fruits and six more farm animals.
`tools/book_catalog.py` owns the category, word and literal letter-name inventory;
`tools/locales.py` compiles `locales/ui.json` into the portable UI translations.
Its recordings are generated through Harmony's reusable `generate_speech` tool
on OpenRouter, using Gemini TTS's Kore voice with gentle delivery and slower,
pitch-preserving playback. Each WAV has a `.speech.json` with the literal word,
spelling, model, voice, speed, measured duration and checksum. No network or
credential is needed while playing.
Dino Colors' scenes and dinosaurs are traced from
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

Jungle's code is BSD 3-Clause. See [LICENSE](LICENSE). The menu and Dino letters are drawn from
[GNU Unifont](https://unifoundry.com/unifont/), under the SIL Open Font
License 1.1; see [licenses/unifont.txt](licenses/unifont.txt). Animal Counting's
BIOS glyphs are recovered from DOSBox; see
[licenses/dosbox-font.txt](licenses/dosbox-font.txt) and
[licenses/GPL-2.txt](licenses/GPL-2.txt). Original game artwork and voice data
retain their original authorship.

## Website deployment

Pushes to `master` run the Linux tests and a private browser test in GitHub
Actions, then publish the same tested website artifact to Cloudflare Pages.
The deployment verifies its revision on `jungle.waozi.xyz`. The repository
secret `CLOUDFLARE_API_TOKEN` grants Pages Edit for the hosting account and
DNS Edit for `waozi.xyz`; credentials are never stored in this repository.
Browser saves stay on that browser in IndexedDB. Images load before play,
and narration loads as needed. Browser printing opens the browser print dialog.
