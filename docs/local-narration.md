# Local narration

German and Spanish use offline Qwen3-TTS 0.6B CustomVoice, Serena, at its
natural rate. English retains Kokoro Bella and its independently generated
slow, normal and fast recordings. `speech.json` records these choices.

`tools/local_narration.py` captures exact text, language, original hashes and
spelling assembly recipes. Synthesis uses immutable request keys and exclusive
claims, so a resumed two-worker run reuses verified recordings. Validation
checks coverage, voice/model receipts, hashes, PCM format, duration, audibility,
clipping and exact spelling reconstruction. It cannot judge pronunciation.

The source repository retains canonical WAVs and provenance receipts at the
existing narration paths. Raw staging, model weights, caches and original
backups remain ignored. The normal shared-assets build encodes distinct source
clips as mono 22050 Hz Vorbis q4, reconstructs spelling from shared clips and
silences, and writes the installed speech index. Native and web apps ship the
encoded audio; neither ships the synthesis model or canonical narration WAVs.

After validating a stage, promote with
`local_narration.promote(root, corpus, languages={'de', 'es'})` to preserve English.
Promotion saves and verifies original WAVs and receipts before replacement.
Refresh measured reader timings with `python3 tools/book_art.py --catalog-only`,
`python3 tools/story_book.py` and `python3 tools/town_musicians_book.py`.
Run `build-queue -- make -j2 all`, the narration unit tests, and
`python3 tests/local_narration_integration_test.py`. The private-display
`tests/local_narration_smoke_test.py` uses an owned Xvfb and SDL disk sink to
verify audible translated narration in ABC, 123, Picture Book, Sweet Porridge
and Town Musicians of Bremen in both orientations. Run it through build-queue
because opening native game bundles may compile them.
