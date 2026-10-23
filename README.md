# Jungle

Learning games for young children, made with [Ziran](https://github.com/ziranlang/ziran)
and [Kryon](https://github.com/kryonlabs/kryon).

**Jungle Math** has four trails:

- **Count**: how many bananas, frogs or snails are there?
- **Stepping Stones**: which number is missing from the row? Later rows count
  down, or count by twos, fives and tens.
- **Add**: two groups join; how many in all?
- **Take Away**: the monkey takes some; how many are left?

Each trail has five levels. Four right answers in a row move up a level, and
three misses move back down. A wrong answer numbers the pictures, so the child
can count along. Every right answer puts a fruit in the basket. Ten fruits
bring a new jungle friend, eight friends in all. Answer with a tap, or by typing
the number and pressing Enter.

**Dino Colors** is a coloring book with six dinosaur pages. Pick a color, then
tap part of the picture to fill it. Undo takes back the last fill, and Clear
makes the page white again. Each page has a short dinosaur fact.

Progress and colored pages are kept in `~/.local/share/jungle/progress.txt`.

## Build and run

Needs a C compiler, SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, and Ziran. Dependencies are pinned in `ziran.lock`.

```sh
make            # build/jungle
./build/jungle
make test       # question and coloring-page checks
make install    # ~/.local/bin/jungle and a menu entry
```

## Pictures and sounds

The drawings are SVG files in `art/`. `make art` renders them into `assets/`
with Inkscape. Each coloring page becomes one fill and one outline per region,
plus a table of where each piece sits. `make sounds` makes the sound effects.
Both tools are written in Ziran (`tools/`), and their output is committed.

## License

BSD 3-Clause. See [LICENSE](LICENSE).
