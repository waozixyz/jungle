"""Write the piano's equal-tempered, quiet triangle tones as binary WAV assets.

The waveform and 8 ms edge fades match Jungle's existing tools/sounds.zi.
Listening and playing use these exact same files, tuned to A4 = 440 Hz.
"""
from array import array
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 22050


def main():
    directory = ROOT / 'assets/piano/sounds'
    directory.mkdir(parents=True, exist_ok=True)
    # A whole note at Slow lasts four seconds. Keep enough sustain
    # for its full gate while retaining the same quiet triangle timbre.
    count = int(RATE * 4.2)
    for pitch in range(48, 85):
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        samples = array('h')
        for index in range(count):
            phase = (index + 1) * frequency / RATE % 1
            triangle = phase * 4 - 1 if phase < .5 else 3 - phase * 4
            edge = min(1, index / (RATE * .008), (count - 1 - index) / (RATE * .008))
            samples.append(round(triangle * edge * .10 * 30000))
        if sys.byteorder != 'little':
            samples.byteswap()
        with wave.open(str(directory / f'{pitch}.wav'), 'wb') as output:
            output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            output.writeframes(samples.tobytes())
    print('Wrote 37 quiet piano tones (C3-C6, A4 = 440 Hz)')


if __name__ == '__main__':
    main()
