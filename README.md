# Jungle

Learning games for young children in the style of an old PC: a 320 by 200
screen of fat pixels, sixteen colors, square-wave beeps, and the keyboard or
mouse. Made with [Ziran](https://github.com/ziranlang/ziran) and
[Kryon](https://github.com/kryonlabs/kryon).

Jungle is a menu. Each game is its own `.zib` bundle in `games/`, which the
app opens through Kryon's app host. A game keeps its saves in its own folder
under `~/.local/share/jungle/games/`.

**Jungle Math** asks one question at a time:

- **Count**: how many bananas, frogs or snails are there?
- **Stepping Stones**: which number is missing from the row? Later rows
  count down, or count by twos, fives and tens.
- **Add**: two groups join; how many in all?
- **Take Away**: some are taken; how many are left?

Type the answer and press Enter, or use the number keys on the screen. A
wrong answer numbers the pictures so the child can count along. Each
activity gets harder after four right answers in a row and easier after
three misses.

**Dino Paint** is a coloring program with six dinosaur pictures. The bucket
fills any closed area, the brush and eraser paint freely in a thin or thick
line, and Undo takes back the last four changes. Pictures are kept.

## Build and run

Needs a C compiler, SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, and Ziran. Dependencies are pinned in `ziran.lock`.

```sh
make            # build/app: the program, its assets and the game bundles
make run
make test       # questions, painting, PNG pictures and every game's check
make install    # ~/.local/bin/jungle and a menu entry
```

## Pixel art and sounds

The drawings are SVG files in `art/`. `make art` cuts them down to small
sprites in the sixteen colors with Inkscape and ImageMagick, makes the
letters from GNU Unifont, and turns each dinosaur page into black lines
written to `games/paint/paint_pages.zi`. `make sounds` makes the beeps. Both
tools are written in Ziran (`tools/`), and their output is committed.

## License

BSD 3-Clause. See [LICENSE](LICENSE). The letters are drawn from
[GNU Unifont](https://unifoundry.com/unifont/), under the SIL Open Font
License 1.1; see [licenses/unifont.txt](licenses/unifont.txt).
