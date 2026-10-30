#!/usr/bin/env python3
"""PCM and envelope regression tests for the shipped drum samples."""
import math
import struct
import unittest
import wave

from generate_sounds import KINDS, OUTPUT, RATE, wav_bytes


class DrumAudioTest(unittest.TestCase):
    def test_shipped_pcm_and_quiet_envelopes(self):
        signatures = set()
        for kind in KINDS:
            with self.subTest(kind=kind):
                path = OUTPUT / f"{kind}.wav"
                data = path.read_bytes()
                self.assertEqual(data, wav_bytes(kind), "asset must match its generator")
                self.assertLess(len(data), 30000)
                with wave.open(str(path), "rb") as audio:
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertEqual(audio.getframerate(), RATE)
                    self.assertEqual(audio.getsampwidth(), 2)
                    self.assertEqual(audio.getcomptype(), "NONE")
                    count = audio.getnframes()
                    self.assertGreaterEqual(count / RATE, 0.4)
                    self.assertLessEqual(count / RATE, 0.65)
                    samples = struct.unpack(f"<{count}h", audio.readframes(count))
                peak = max(map(abs, samples)) / 32768
                rms = math.sqrt(sum(s * s for s in samples) / count) / 32768
                self.assertGreater(peak, 0.1)
                self.assertLessEqual(peak, 0.20)
                self.assertGreater(rms, 0.012)
                self.assertLess(rms, 0.085)
                self.assertEqual(samples[0], 0)
                self.assertEqual(samples[-1], 0)
                self.assertLess(max(map(abs, samples[:22])), 0.012 * 32768)
                self.assertLess(max(map(abs, samples[-220:])), 0.012 * 32768)
                signatures.add(data)
        self.assertEqual(len(signatures), 4, "each instrument has its own timbre")


if __name__ == "__main__":
    unittest.main()
