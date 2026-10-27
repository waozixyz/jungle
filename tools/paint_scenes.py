#!/usr/bin/env python3
"""Build six additional, closed-outline coloring backgrounds as native SVGs.

Large open foregrounds leave room for placed stencils. Closed, white-filled
shapes hide scenery behind them and give the bucket clear boundaries.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def path(d):
    return f'<path d="{d}"/>'


def cloud(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + path(
        'M0 45 C-12 16 18 6 38 16 C40 -10 83 -11 94 12 '
        'C115 -2 146 12 145 31 C184 22 205 66 166 70 '
        'L22 70 C5 70 -8 60 0 45 Z') + '</g>'


def sun(x, y):
    return f'<circle cx="{x}" cy="{y}" r="42"/>' + ''.join(
        path(d) for d in (
            f'M{x} {y-61} v-19', f'M{x} {y+61} v19',
            f'M{x-61} {y} h-19', f'M{x+61} {y} h19',
            f'M{x-44} {y-44} l-14 -14', f'M{x+44} {y-44} l14 -14',
            f'M{x-44} {y+44} l-14 14', f'M{x+44} {y+44} l14 14'))


def bush(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + path(
        'M0 80 C-15 60 -2 37 20 40 C15 11 49 3 65 22 '
        'C78 -8 119 -1 123 25 C148 8 173 30 166 51 '
        'C198 51 207 83 183 95 L15 95 Q0 93 0 80 Z') + '</g>'


def flower(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + (
        path('M0 20 L0 80 M0 58 Q-33 28 -34 58 Q-18 80 0 68 '
             'M0 46 Q32 17 35 47 Q18 66 0 58') +
        path('M-13 -6 C-42 -32 -9 -58 4 -31 C22 -58 50 -28 23 -8 '
             'C53 8 27 37 9 18 C-6 45 -37 21 -16 4 Q-24 -2 -13 -6 Z') +
        '<circle cx="5" cy="-6" r="12"/></g>')


def pine(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + (
        path('M-10 250 H14 L10 172 H-7 Z') +
        path('M0 0 L49 77 H29 L76 145 H48 L99 212 H-94 L-47 145 '
             'H-74 L-29 77 H-48 Z') + '</g>')


def rock(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + path(
        'M0 50 L15 13 Q42 -6 67 6 L100 47 Q108 64 83 65 H14 Q-4 63 0 50 Z') + '</g>'


def cactus(x, y, scale=1):
    return f'<g transform="translate({x} {y}) scale({scale})">' + (
        path('M-20 240 V150 H-52 Q-79 150 -79 123 V80 C-79 57 -49 57 -49 80 '
             'V116 H-20 V22 C-20 -10 21 -10 21 22 V89 H50 V56 C50 35 80 35 80 56 '
             'V100 Q80 122 57 122 H21 V240 Z') +
        path('M-5 24 V220 M7 30 V85 M7 143 V214 M-65 88 V121 M65 62 V98') + '</g>')


def scene(number, name, elements):
    text = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 720" '
            'width="960" height="720">\n'
            f'<title>{name}</title>\n<rect width="960" height="720" fill="#fff"/>\n'
            '<g fill="#fff" stroke="#000" stroke-width="5.5" '
            'stroke-linecap="round" stroke-linejoin="round">\n' +
            '\n'.join(elements) + '\n</g>\n</svg>\n')
    (ROOT / f'art/paint/scene{number}.svg').write_text(text)


def main():
    scene(7, 'Meadow', [
        sun(730, 105), cloud(170, 70, .95), cloud(460, 145, .65),
        path('M-8 360 Q165 170 370 322 Q600 180 968 343 V728 H-8 Z'),
        path('M-8 435 Q260 285 500 402 Q750 300 968 408 V728 H-8 Z'),
        bush(-50, 350, 1.1), bush(805, 343, 1.1),
        flower(70, 524, .85), flower(154, 565, .7), flower(877, 552, .9),
        path('M-8 670 Q70 620 225 684 L280 728 H-8 Z'),
        path('M718 728 Q823 622 968 654 V728 Z'),
        flower(60, 630, .65), flower(894, 623, .65),
    ])
    scene(8, 'Forest', [
        cloud(440, 52, .8),
        path('M-8 355 Q220 250 480 349 Q725 244 968 342 V728 H-8 Z'),
        pine(310, 151, .85), pine(653, 128, .95),
        pine(115, 60, 1.6), pine(860, 25, 1.8),
        bush(-70, 401, 1), bush(822, 407, 1),
        path('M424 360 Q550 387 493 450 Q444 493 544 537 '
             'Q615 590 665 728 H295 Q370 588 399 543 Q344 472 424 360 Z'),
        rock(35, 602, 1), rock(803, 593, 1.15),
        flower(211, 570, .55), flower(741, 543, .65),
    ])
    scene(9, 'Desert', [
        sun(700, 115), cloud(170, 70, .9),
        path('M-8 342 L125 342 L172 240 L253 240 L284 327 L391 344 '
             'L443 277 L521 277 L573 346 L968 325 V728 H-8 Z'),
        path('M-8 448 Q240 298 485 421 Q748 320 968 406 V728 H-8 Z'),
        cactus(131, 270, 1.08), cactus(837, 306, .9),
        rock(32, 572, 1.1), rock(137, 612, .6), rock(807, 598, 1.1),
        path('M320 535 Q362 522 399 535 M590 616 Q643 599 702 616 '
             'M227 684 Q270 670 306 684'),
    ])
    scene(10, 'Snowy hills', [
        cloud(450, 50, .9),
        path('M-8 365 L205 98 L420 359 L625 115 L968 386 V728 H-8 Z'),
        path('M122 203 L205 98 L300 214 L254 200 L222 231 L188 194 L153 226 Z'),
        path('M532 226 L625 115 L731 230 L682 216 L651 241 L617 213 L577 244 Z'),
        path('M-8 466 Q263 292 502 423 Q752 311 968 431 V728 H-8 Z'),
        pine(100, 280, 1.2), pine(850, 265, 1.3),
        path('M28 555 Q101 520 170 554 Q187 574 145 578 H46 Q12 575 28 555 Z'),
        path('M769 566 Q850 533 936 568 Q953 586 910 588 H792 Q756 586 769 566 Z'),
        rock(30, 640, .8), rock(849, 638, .85),
    ])
    scene(11, 'Pond', [
        cloud(209, 57, .8), sun(729, 109),
        path('M-8 363 Q210 222 421 345 Q650 228 968 357 V728 H-8 Z'),
        bush(-30, 270, 1.35), bush(741, 270, 1.35),
        path('M178 459 C222 367 649 366 777 435 C930 498 833 617 676 625 '
             'C514 674 171 630 125 556 C85 512 123 475 178 459 Z'),
        path('M300 491 Q269 464 231 491 Q215 523 250 539 Q298 552 332 526 '
             'L287 518 Z'),
        path('M689 528 Q655 503 619 528 Q600 555 640 574 Q684 583 718 555 '
             'L676 552 Z'),
        path('M424 454 Q480 440 538 454 M355 580 Q410 567 471 580'),
        path('M64 519 V368 M91 526 V393 M868 544 V390 M896 536 V365'),
        '<rect x="53" y="333" width="22" height="62" rx="11"/>',
        '<rect x="80" y="361" width="22" height="58" rx="11"/>',
        '<rect x="857" y="356" width="22" height="62" rx="11"/>',
        '<rect x="885" y="329" width="22" height="66" rx="11"/>',
        rock(9, 566, .85), rock(859, 580, .85),
        flower(149, 639, .65), flower(789, 636, .65),
    ])
    scene(12, 'Farmyard', [
        sun(125, 109), cloud(392, 64, .9),
        path('M-8 375 Q220 278 480 359 Q734 254 968 358 V728 H-8 Z'),
        '<rect x="573" y="247" width="261" height="180"/>',
        path('M550 252 L704 140 L856 252 Z'),
        '<rect x="651" y="317" width="107" height="110"/>',
        path('M651 317 L758 427 M758 317 L651 427 M705 318 V426'),
        '<circle cx="704" cy="265" r="23"/>',
        path('M704 243 V287 M682 265 H726'),
        bush(-45, 277, 1.25),
        '<rect x="3" y="430" width="258" height="22" rx="4"/>',
        '<rect x="3" y="479" width="258" height="22" rx="4"/>',
        path('M35 535 V407 L50 390 L65 407 V535 Z'),
        path('M178 535 V407 L193 390 L208 407 V535 Z'),
        bush(820, 429, 1), rock(22, 615, .9),
        flower(867, 607, .8), flower(784, 645, .55),
        path('M339 728 Q372 521 649 427 M646 728 Q588 516 758 427'),
    ])
    print('Built Meadow, Forest, Desert, Snowy hills, Pond and Farmyard SVG scenes.')


if __name__ == '__main__':
    main()
