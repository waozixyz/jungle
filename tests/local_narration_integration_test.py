"""Verify shipping DE/ES narration uses the complete validated Qwen stage."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import local_narration as narration
from speech_codec import ValidateEncodedSpeech, OggVorbisFrames


def main():
    settings = json.loads((ROOT / 'speech.json').read_text())['narration']
    counts = {'de': 0, 'es': 0}
    receipts = {}
    for receipt_path in narration._receipts(ROOT):
        receipt = json.loads(receipt_path.read_text())
        name = receipt_path.relative_to(ROOT).as_posix().removesuffix('.speech.json') + '.wav'
        receipts[name] = receipt
    for name, receipt in receipts.items():
        language = narration.identify_language(name, receipt)
        if language == 'en':
            continue
        expected = settings[language]
        kind = narration.content_kind(name, receipt)
        # speech.json picks the voice per content kind; spelling follows its word.
        voice = (receipts[receipt['sources'][0]['path']]['voice'] if kind == 'spelling'
                 else expected.get('voices', {}).get(kind, expected['voice']))
        assert receipt['model'] == expected['model'], name
        assert receipt['voice'] == voice, (name, receipt['voice'], voice)
        assert receipt.get('kind', kind) == kind, name
        retake = expected.get('retakes', {}).get(name)
        assert receipt.get('seeds') == (retake['seeds'] if retake else None), name
        assert receipt['speed'] == 1.0, name
        assert receipt['sha256'] == narration.digest(ROOT / name), name
        narration._audio(ROOT / name, receipt['text'])
        counts[language] += 1
    assert counts == {'de': 1018, 'es': 1016}, counts
    manifest = json.loads((ROOT / 'build/stage/speech-manifest.json').read_text())
    files = {entry['path']: ROOT / 'build/app' / entry['path']
             for entry in manifest['encoded'].values()}
    ValidateEncodedSpeech(manifest, files)
    for name, clip in manifest['clips'].items():
        assert OggVorbisFrames(files[manifest['encoded'][name]['path']].read_bytes()) == clip['frame_count'], name
    for language in counts:
        for story in ('porridge', 'musicians'):
            voices = [name for name in manifest['voices']
                      if f'/story-sounds/{language}/{story}_' in name]
            assert len(voices) == 11, (language, story, len(voices))
    print(f'local Qwen integration passed: {counts}, full story coverage, encoded hashes and frames')


if __name__ == '__main__':
    main()
