#!/usr/bin/env python3
"""Build six additional, closed-outline coloring backgrounds as native SVGs.

Each scene has a wide page (art/paint/sceneN.svg, 960 by 720) and a tall page
composed for portrait screens (art/paint/portraitN.svg, 720 by 960) with the
same subject and shapes. Large open foregrounds leave room for placed
stencils. Closed, white-filled shapes hide scenery behind them and give the
bucket clear boundaries.
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


def polygon(points):
    return path('M' + ' L'.join(f'{x:g} {y:g}' for x, y in points) + ' Z')


def scene(number, name, elements, tall=False):
    width, height = (720, 960) if tall else (960, 720)
    text = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            f'<title>{name}</title>\n<rect width="{width}" height="{height}" fill="#fff"/>\n'
            '<g fill="#fff" stroke="#000" stroke-width="5.5" '
            'stroke-linecap="round" stroke-linejoin="round">\n' +
            '\n'.join(elements) + '\n</g>\n</svg>\n')
    (ROOT / f'art/paint/{"portrait" if tall else "scene"}{number}.svg').write_text(text)


def snowy_mountains(scale_x, dy):
    """The two snowy peaks and their caps, narrowed for a tall page."""
    def at(points):
        return [(round(x * scale_x, 1), y + dy) for x, y in points]
    return [
        path('M-8 ' + f'{365 + dy}' + ' L' + ' L'.join(f'{x:g} {y:g}' for x, y in at(
            [(205, 98), (420, 359), (625, 115), (968, 386)])) + f' V{960 + 8} H-8 Z'),
        polygon(at([(122, 203), (205, 98), (300, 214), (254, 200), (222, 231), (188, 194), (153, 226)])),
        polygon(at([(532, 226), (625, 115), (731, 230), (682, 216), (651, 241), (617, 213), (577, 244)])),
    ]


def portraits():
    scene(7, 'Meadow', [
        sun(560, 110), cloud(90, 80, .8), cloud(380, 190, .6),
        path('M-8 470 Q140 300 330 430 Q500 320 728 450 V968 H-8 Z'),
        path('M-8 560 Q200 430 380 530 Q560 450 728 540 V968 H-8 Z'),
        bush(-50, 470, 1.0), bush(590, 465, 1.0),
        flower(60, 660, .85), flower(140, 710, .7), flower(660, 690, .9),
        path('M-8 900 Q70 850 210 914 L250 968 H-8 Z'),
        path('M520 968 Q610 860 728 890 V968 Z'),
        flower(60, 870, .65), flower(670, 880, .6),
    ], tall=True)
    scene(8, 'Forest', [
        cloud(300, 60, .75),
        path('M-8 470 Q180 380 360 465 Q540 370 728 455 V968 H-8 Z'),
        pine(250, 250, .85), pine(480, 225, .95),
        pine(90, 120, 1.6), pine(640, 90, 1.8),
        bush(-70, 520, 1), bush(590, 525, 1),
        path('M330 475 Q440 500 390 560 Q345 600 435 650 '
             'Q500 700 545 968 H190 Q260 800 300 655 Q250 590 330 475 Z'),
        rock(30, 820, 1), rock(590, 830, 1.15),
        flower(150, 760, .55), flower(590, 740, .65),
    ], tall=True)
    scene(9, 'Desert', [
        sun(540, 120), cloud(80, 80, .85),
        path('M-8 440 L100 440 L140 340 L215 340 L240 425 L330 440 '
             'L370 380 L440 380 L480 444 L728 425 V968 H-8 Z'),
        path('M-8 560 Q190 420 370 535 Q560 450 728 520 V968 H-8 Z'),
        cactus(110, 360, 1.0), cactus(620, 400, .85),
        rock(20, 780, 1.1), rock(130, 830, .6), rock(600, 800, 1.1),
        path('M240 690 Q282 677 319 690 M440 800 Q493 783 552 800 '
             'M170 900 Q213 886 249 900'),
    ], tall=True)
    scene(10, 'Snowy hills', [
        cloud(250, 50, .85),
        *snowy_mountains(.75, 90),
        path('M-8 580 Q200 420 380 530 Q560 430 728 545 V968 H-8 Z'),
        pine(80, 390, 1.2), pine(640, 375, 1.3),
        path('M28 760 Q101 725 170 759 Q187 779 145 783 H46 Q12 780 28 760 Z'),
        path('M530 770 Q611 737 697 772 Q714 790 671 792 H553 Q517 790 530 770 Z'),
        rock(30, 860, .8), rock(600, 860, .85),
    ], tall=True)
    scene(11, 'Pond', [
        cloud(120, 57, .75), sun(560, 109),
        path('M-8 430 Q160 320 330 420 Q500 330 728 430 V968 H-8 Z'),
        bush(-30, 340, 1.2), bush(530, 340, 1.2),
        path('M140 560 C175 470 520 470 610 535 C730 600 660 740 535 750 '
             'C400 800 135 760 100 680 C70 640 95 580 140 560 Z'),
        path('M230 600 Q199 573 161 600 Q145 632 180 648 Q228 661 262 635 L217 627 Z'),
        path('M520 650 Q486 625 450 650 Q431 677 471 696 Q515 705 549 677 L507 674 Z'),
        path('M330 570 Q386 556 444 570 M280 700 Q335 687 396 700'),
        path('M44 640 V489 M71 647 V514 M650 664 V510 M678 656 V485'),
        '<rect x="33" y="454" width="22" height="62" rx="11"/>',
        '<rect x="60" y="482" width="22" height="58" rx="11"/>',
        '<rect x="639" y="476" width="22" height="62" rx="11"/>',
        '<rect x="667" y="449" width="22" height="66" rx="11"/>',
        rock(9, 820, .85), rock(590, 830, .85),
        flower(149, 880, .65), flower(600, 890, .65),
    ], tall=True)
    scene(12, 'Farmyard', [
        sun(110, 109), cloud(330, 64, .8),
        path('M-8 470 Q180 390 360 455 Q540 370 728 450 V968 H-8 Z'),
        '<rect x="393" y="337" width="261" height="180"/>',
        path('M370 342 L524 230 L676 342 Z'),
        '<rect x="471" y="407" width="107" height="110"/>',
        path('M471 407 L578 517 M578 407 L471 517 M525 408 V516'),
        '<circle cx="524" cy="355" r="23"/>',
        path('M524 333 V377 M502 355 H546'),
        bush(-45, 367, 1.2),
        '<rect x="3" y="520" width="258" height="22" rx="4"/>',
        '<rect x="3" y="569" width="258" height="22" rx="4"/>',
        path('M35 625 V497 L50 480 L65 497 V625 Z'),
        path('M178 625 V497 L193 480 L208 497 V625 Z'),
        bush(560, 560, 1), rock(22, 800, .9),
        flower(620, 800, .8), flower(540, 860, .55),
        path('M190 968 Q230 700 471 517 M500 968 Q440 720 578 517'),
    ], tall=True)


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
    portraits()
    print('Built Meadow, Forest, Desert, Snowy hills, Pond and Farmyard SVG scenes, wide and tall.')


if __name__ == '__main__':
    main()
