"""Check actual shipped pitches, WAV portability and gentle amplitude."""
from array import array
import math
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
for pitch in range(48, 85):
    with wave.open(str(ROOT / f'assets/piano/sounds/{pitch}.wav'), 'rb') as source:
        assert source.getparams()[:3] == (1, 2, 22050)
        samples = array('h', source.readframes(source.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    assert len(samples) == 92610 and samples[0] == samples[-1] == 0
    assert 2900 < max(map(abs, samples)) <= 3000
    # Estimate frequency from rising zero crossings away from the fades.
    crossings = [i for i in range(300, len(samples) - 300)
                 if samples[i - 1] < 0 <= samples[i]]
    frequency = (len(crossings) - 1) * 22050 / (crossings[-1] - crossings[0])
    expected = 440 * 2 ** ((pitch - 69) / 12)
    cents = 1200 * math.log2(frequency / expected)
    assert abs(cents) < 1, (pitch, frequency, expected)
print('local piano audio test: all 37 WAV pitches within one cent; quiet amplitude and edge fades passed')
