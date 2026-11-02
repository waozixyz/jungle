"""Measure real story auto-advance for each generated English recording."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from PIL import ImageChops, ImageStat
from runtime_test import Desktop, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    binary = parser.parse_args().binary.resolve()
    assert binary != ROOT / 'build/app/jungle', 'use the explicit private test host'
    inventory = json.loads((ROOT / 'assets/speech-profiles.json').read_text())
    # Use the story inventory rather than depending on a page's filename.
    row = json.loads((ROOT / 'tools/sweet_porridge.json').read_text())['pages'][1]
    voice = f"assets/jungle-book/story-sounds/en/{row['asset']}.wav"
    results = []
    for width, height in ((960, 600), (420, 900)):
        for profile in ('slow', 'normal', 'fast'):
            selected = ROOT / inventory['profiles'][profile]['voices'][voice]
            duration = json.loads(selected.with_suffix('.speech.json').read_text())['duration']
            with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='story-profile-ui-') as folder:
                data = Path(folder)
                (data / 'speech-profile.txt').write_text(profile)
                with Desktop(binary, data, screen_size='1280x1100') as desktop:
                    desktop.resize(width, height)
                    desktop.game('Sweet Porridge')
                    desktop.capture_actual('cover')
                    start = time.monotonic()
                    desktop.key('Right')
                    page = desktop.capture_actual('narrating')
                    box = (width//4, 80, width*3//4, height//2)
                    baseline = page.crop(box)
                    def changed():
                        picture = desktop.capture_actual('story-clock')
                        return max(ImageStat.Stat(ImageChops.difference(picture.crop(box), baseline)).mean) > 4
                    # A page must stay visible for its complete selected clip.
                    while time.monotonic() - start < duration - .25:
                        assert not changed(), (profile, 'page turned before narration ended')
                    # Normal autoplay adds three seconds of quiet. A stale
                    # longer fallback would hold the fast profile too long.
                    deadline = start + duration + 4.5
                    while not changed():
                        assert time.monotonic() < deadline, (profile, 'page did not advance after measured narration')
                    elapsed = time.monotonic() - start
                    assert elapsed >= duration + 2.5, (profile, elapsed, duration)
                    results.append(dict(size=[width, height], profile=profile,
                                        narration_seconds=duration, page_seconds=elapsed))
    output = ROOT / 'work/full-delivery/local-integration/story-profile-ui.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + '\n')
    print('local story autoplay: all three measured profiles, complete narration plus quiet, both orientations passed')


if __name__ == '__main__':
    main()
