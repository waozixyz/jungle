#!/usr/bin/env python3
"""Deterministic, offline physical-model instruments for the toddler music room.

Only creates missing model WAVs; never overwrites existing sounds. Existing drum, shaker and bell sounds
are deliberately preserved. No network, sound API, random global state or quota.
Run --check to validate the shipped sounds without changing any files.
"""
from array import array
import argparse
import cmath
import math
from pathlib import Path
import random
import struct
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'assets/drums/sounds'
RATE = 22050
NEW = ('big_drum', 'xylophone', 'guitar', 'cymbal', 'tambourine')
ALL = ('big_drum', 'small_drum', 'shaker', 'bell', 'xylophone', 'guitar', 'cymbal', 'tambourine')


def resonator(output, frequency, decay, amplitude, start=0., phase=0.):
    """An excited damped vibration mode (wood, membrane or metal)."""
    first = int(start * RATE)
    step = math.tau * frequency / RATE
    attenuation = math.exp(-1 / (decay * RATE))
    # Two-pole recurrence avoids accumulating trigonometric phase error.
    coefficient = 2 * math.cos(step) * attenuation
    previous = math.sin(phase - step) / attenuation
    current = math.sin(phase)
    for i in range(first, len(output)):
        output[i] += amplitude * current
        previous, current = current, coefficient * current - attenuation * attenuation * previous


def big_drum():
    output = [0.] * int(.95 * RATE)
    # Damped membrane modes plus shell/body resonances audible on small
    # speakers. The bass stays round, with a short hand impact, not a click.
    for frequency, amplitude, decay in ((92., 1., .16), (147., .72, .13),
            (198., .58, .11), (267., .48, .10), (338., .36, .075),
            (421., .25, .06), (583., .17, .04)):
        resonator(output, frequency, decay, amplitude)
    rng = random.Random(6205)
    previous = 0.
    for i in range(int(.035 * RATE)):
        previous = .65 * previous + .35 * rng.uniform(-1, 1)
        output[i] += previous * .6 * math.exp(-i / (RATE * .009))
    return output


def xylophone():
    output = [0.] * int(1.45 * RATE)
    # The bending modes of a free wooden bar are strongly inharmonic.
    for ratio, amplitude, decay in ((1., 1., .24), (3.99, .38, .09),
                                     (9.0, .17, .045), (14.37, .06, .025)):
        resonator(output, 523.25 * ratio, decay, amplitude)
    rng = random.Random(6201)
    for i in range(int(.012 * RATE)):
        output[i] += rng.uniform(-1, 1) * .09 * math.exp(-i / (RATE * .003))
    return output


def guitar():
    output = [0.] * int(2.45 * RATE)
    rng = random.Random(6202)
    # Six separately plucked strings, softly strummed E major. A fractional
    # delay line with bridge loss models propagation and string damping.
    for string, frequency in enumerate((82.4069, 123.4708, 164.8138, 207.6523, 246.9417, 329.6276)):
        delay = RATE / frequency - .5
        count = math.ceil(delay)
        fraction = count - delay
        pluck = .23
        line = [0.] * count
        for i in range(count):
            at = i / count
            line[i] = ((at / pluck if at < pluck else (1 - at) / (1 - pluck)) - .5) + rng.uniform(-.035, .035)
        at = 0
        previous = line[-1]
        for i in range(int(string * .012 * RATE), len(output)):
            sample = line[at] * (1 - fraction) + line[(at + 1) % count] * fraction
            reflected = .5 * (sample + previous) * .995
            previous = sample
            line[at] = reflected
            at = (at + 1) % count
            output[i] += sample * .48
    # The soundboard's short, low resonances support the string attack.
    resonator(output, 109., .11, .13)
    resonator(output, 213., .07, .07)
    return output


def cymbal():
    output = [0.] * int(2.1 * RATE)
    rng = random.Random(6203)
    # Many non-harmonic plate modes plus the short broadband stick impact.
    for i in range(34):
        frequency = 380 + (i / 33) ** 1.32 * 9200 + rng.uniform(-65, 65)
        resonator(output, frequency, .65 - .48 * i / 33,
                  .16 / (1 + i * .035), phase=rng.uniform(0, math.tau))
    previous = 0.
    for i in range(len(output)):
        noise = rng.uniform(-1, 1)
        output[i] += (noise - previous) * .18 * math.exp(-i / (RATE * .12))
        previous = noise
    return output


def tambourine():
    output = [0.] * int(.95 * RATE)
    rng = random.Random(6204)
    # A shaken pair of metal jingles repeatedly collides, rather than one
    # sustained splash. A muted frame/head supplies the first low tap.
    for collision, start in enumerate((0., .047, .104, .173, .247, .316)):
        for frequency in (1673., 2311., 3479., 4817., 6329., 8147., 9691.):
            resonator(output, frequency * rng.uniform(.985, 1.015), rng.uniform(.035, .075),
                      .15 * (1 - collision * .085), start, rng.uniform(0, math.tau))
    resonator(output, 186., .048, .65)
    resonator(output, 329., .022, .18)
    return output


MODELS = dict(zip(NEW, (big_drum, xylophone, guitar, cymbal, tambourine)))


def pcm(name):
    output = MODELS[name]()
    mean = sum(output) / len(output)
    output = [value - mean for value in output]
    peak = max(abs(value) for value in output)
    rms = math.sqrt(sum(value * value for value in output) / len(output))
    gain = min((.125 if name == "big_drum" else .050) / rms, (.80 if name == "big_drum" else .48) / peak)
    # Other models retain their original levels; the larger drum gets
    # stronger body energy. The shared host applies 65% to room effects.
    if name == 'big_drum':
        output = [value * min(1., i / (RATE * .003), (len(output) - 1 - i) / (RATE * .025))
                  for i, value in enumerate(output)]
        gain = .80 / max(map(abs, output))
    samples = array('h')
    for i, value in enumerate(output):
        edge = min(1., i / (RATE * .003), (len(output) - 1 - i) / (RATE * .025))
        samples.append(round(value * gain * (1 if name == "big_drum" else edge) * 32767))
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples.tobytes()


def read_pcm(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) == (1, 2, RATE, 'NONE'), path
        return source.readframes(source.getnframes())


def spectrum(samples):
    """Eight coarse spectral bands from a windowed FFT of the attack."""
    count = 4096
    values = [complex(samples[i] * (.5 - .5 * math.cos(math.tau * i / (count - 1))))
              if i < len(samples) else 0j for i in range(count)]
    j = 0
    for i in range(1, count):
        bit = count >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    size = 2
    while size <= count:
        rotation = cmath.exp(-2j * math.pi / size)
        for offset in range(0, count, size):
            turn = 1 + 0j
            for i in range(size // 2):
                a = values[offset + i]
                b = turn * values[offset + i + size // 2]
                values[offset + i], values[offset + i + size // 2] = a + b, a - b
                turn *= rotation
        size *= 2
    bands = [0.] * 8
    boundaries = (150, 300, 600, 1200, 2400, 4800, 8000)
    for i in range(1, count // 2):
        frequency = i * RATE / count
        band = sum(frequency >= boundary for boundary in boundaries)
        bands[band] += abs(values[i]) ** 2
    total = sum(bands)
    return [value / total for value in bands]


def metrics(raw):
    samples = [item[0] / 32768 for item in struct.iter_unpack('<h', raw)]
    rms = lambda seq: math.sqrt(sum(value * value for value in seq) / max(1, len(seq)))
    return dict(duration=len(samples) / RATE, rms=rms(samples), peak=max(map(abs, samples)),
                tail_rms=rms(samples[-int(.025 * RATE):]), bands=spectrum(samples))


def validate():
    reports = {}
    for name in ALL:
        raw = read_pcm(DIRECTORY / f'{name}.wav')
        result = reports[name] = metrics(raw)
        assert .08 <= result['duration'] <= 3, (name, 'duration', result)
        assert .008 < result['rms'] < .4, (name, 'RMS', result)
        assert .03 < result['peak'] <= .82, (name, 'peak', result)
        if name in NEW:
            assert raw == pcm(name), (name, 'not reproducible from model')
            assert result['tail_rms'] < .025, (name, 'unfaded tail')
            assert raw[:2] == raw[-2:] == b'\0\0', (name, 'edge click')
        print(f"{name}: {result['duration']:.2f}s RMS={result['rms']:.4f} peak={result['peak']:.3f} tail={result['tail_rms']:.5f}")
    drum = reports['big_drum']
    assert .10 <= drum['rms'] <= .14 and .75 <= drum['peak'] <= .85, ('big drum source level', drum)
    old = metrics(read_pcm(DIRECTORY / 'low_drum.wav'))
    assert drum['rms'] > old['rms'] * 3, 'big drum is still quiet'
    assert sum(drum['bands'][1:3]) > .25, 'big drum lacks laptop body overtones'
    # Spectral distance between probability distributions, independent of gain.
    minimum = 1.
    for i, first in enumerate(ALL):
        for second in ALL[i + 1:]:
            distance = sum(abs(a - b) for a, b in zip(reports[first]['bands'], reports[second]['bands'])) / 2
            minimum = min(minimum, distance)
            assert distance > .045, (first, second, 'indistinct spectra', distance)
    assert reports['guitar']['bands'][0] + reports['guitar']['bands'][1] > .5, 'guitar lacks string fundamentals'
    # A wood strike decays steadily; the shake has several separate jingle
    # collisions. Equal RMS alone would not distinguish those envelopes.
    for name in NEW:
        values = [value[0] / 32768 for value in struct.iter_unpack('<h', read_pcm(DIRECTORY / f'{name}.wav'))]
        attack = sum(value * value for value in values[:int(.15 * RATE)])
        tail = sum(value * value for value in values[-int(.15 * RATE):])
        assert tail < attack * .2, (name, 'no physical decay')
    jingles = [value[0] / 32768 for value in struct.iter_unpack('<h', read_pcm(DIRECTORY / 'tambourine.wav'))]
    energy = lambda start, end: sum(value * value for value in jingles[int(start * RATE):int(end * RATE)])
    assert energy(.24, .36) > energy(.5, .62) * 8, 'tambourine collision train missing'
    assert reports['xylophone']['bands'][2] > .4, 'wooden bar fundamental missing'
    assert sum(reports['cymbal']['bands'][4:]) > .5, 'cymbal lacks metallic partials'
    assert sum(reports['tambourine']['bands'][4:]) > .5, 'jingles lack metallic partials'
    print(f'local music room audio test: 8 active PCM sounds, 5 deterministic models, envelopes, levels and all 28 spectral pairs passed (minimum distance={minimum:.3f})')
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check:
        for name in NEW:
            if (DIRECTORY / f'{name}.wav').exists():
                continue
            with wave.open(str(DIRECTORY / f'{name}.wav'), 'wb') as target:
                target.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                target.writeframes(pcm(name))
        print('Created missing physical-model sounds; preserved all existing WAVs')
    validate()


if __name__ == '__main__':
    main()
