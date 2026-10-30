"""Focused native and browser checks for composed speech playback."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/app'
DRIVER = ROOT / 'build/tests/voice'
WEB = ROOT / 'build/web'
RATE = 22050


def speech_lesson():
    lines = (APP / 'assets/speech.txt').read_text().splitlines()
    if lines[0] != '#jungle-speech-1':
        raise AssertionError('installed speech index has the wrong header')
    for line in lines:
        if not line.startswith('voice|'):
            continue
        _, path, specification = line.split('|')
        segments = specification.split()
        frames = [int(segment.split(':')[2] if ':' in segment else segment) for segment in segments]
        if len(segments) > 1 and any(':' not in segment for segment in segments):
            return path, segments, frames
    raise AssertionError('speech index has no multi-clip lesson with silence')


def native_composition_test(path, segments, frames):
    with tempfile.TemporaryDirectory(prefix='speech-playback-', dir=ROOT / 'work') as directory:
        output = Path(directory) / 'composed.wav'
        result = subprocess.run([str(DRIVER), path, str(output)], cwd=APP,
                                env={**os.environ, 'SDL_AUDIODRIVER': 'dummy'})
        assert result.returncode == 0, (path, result.returncode)
        samples = output.read_bytes()
        assert len(samples) == sum(frames) * 2
        offset = 0
        for segment, count in zip(segments, frames):
            quiet = ':' not in segment
            span = samples[offset * 2:(offset + count) * 2]
            assert (not any(span)) if quiet else any(span), (segment, offset)
            offset += count
    missing = [path for path in (APP / 'assets').rglob('*.wav') if 'assets/jungle/sounds/' not in path.as_posix()]
    assert not missing, [path.relative_to(APP) for path in missing]


def browser_test():
    index = WEB / 'index.html'
    if '#jungle-speech-1' not in index.read_text():
        raise AssertionError(f'browser build is stale; run make web before {Path(__file__).name}')
    result = subprocess.run(['node', str(ROOT / 'tests/speech_playback_web_test.mjs')], cwd=ROOT)
    assert result.returncode == 0, result.returncode


def main():
    if not DRIVER.is_file() or not (APP / 'assets/speech.txt').is_file():
        raise SystemExit('speech playback test needs make all first')
    path, segments, frames = speech_lesson()
    assert sum(frames) <= RATE * 60
    native_composition_test(path, segments, frames)
    browser_test()
    print(f'local speech playback test: native {len(segments)}-segment lesson and browser sequence controls passed')


if __name__ == '__main__':
    main()
