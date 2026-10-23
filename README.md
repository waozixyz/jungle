# Jungle

Learning games for young children in the style of an old PC: a 320 by 200
screen of fat pixels, VGA crayons, square-wave beeps, and the keyboard or
mouse. Made with [Ziran](https://github.com/ziranlang/ziran) and
[Kryon](https://github.com/kryonlabs/kryon).

Jungle is a menu. Each game is its own `.zib` bundle in `games/`, which the
app opens through Kryon's app host. A game keeps its saves in its own folder
under `~/.local/share/jungle/games/`.

**Animal Counting** is Animal Math's counting game: how many are there?
The pictures sit in the original eighteen fixed places, the levels climb
4, 5, 6, 9, 12 and 18, six right answers move up, six misses move
back down, the same number never comes twice, and every eighth right
answer brings one of the original praises, from GOOD JOB to AWESOME.

**Dino Colors** plays like Bert's Dinosaurs. Pick one of six scenes, place
any of twelve dinosaurs in four sizes (a right-click mirrors it), then fill
the picture with thirty crayon buttons. You can write an eight-line story
and keep the whole picture and story in one of six slots. Undo takes back the
last dinosaur, fill or erase. The working picture recovers when you reopen the
game. Dinosaur selection includes the original recorded names, with sound on,
silent and voice-only settings.

## Build and run

Needs a C compiler, SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, and Ziran. Dependencies are pinned in `ziran.lock`.

```sh
make            # build/app: the program, its assets and the game bundles
make run
make test       # counting, complete saves, painting, PNGs and printing
make test-ui    # real keyboard/mouse play on a separate virtual display
make install    # ~/.local/bin/jungle and a menu entry
```

The tests need ImageMagick, Python's Pillow package and Ghostscript. UI tests
also need Xvfb and xdotool.
They use temporary saves and never connect to the current desktop. Jungle's
`--check` validates game identities and capabilities without touching saves.
Old Jungle Math counting levels carry over into Animal Counting on startup.

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

## Pixel art and sounds

The drawings are SVG files in `art/`. `make art` cuts them down to small
sprites in the sixteen colors with Inkscape and ImageMagick, and makes the
letters from GNU Unifont. Dino Colors' scenes and dinosaurs are traced from
the original Bert's Dinosaurs artwork into `assets/dino-paint/art` and
`games/paint/paint_pages.zi`. `make sounds` makes the beeps. Both tools are
written in Ziran (`tools/`), and their output is committed. They preserve the
recovered game artwork and recordings.

`tools/paint_pages.py` compiles the committed PNG line art into portable paint
masks, respecting transparency, and makes previews that retain thin strokes.
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
