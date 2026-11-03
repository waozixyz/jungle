"""Generate only Bremen's recordings, independently of the Qwen job."""
import json
import sys
import subprocess
from pathlib import Path
import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro
from english_speech import save, digest, profile_path, PROFILES, ROOT
PACK = ROOT.parents[2]/'harness/speech'
sys.path.insert(0, str(PACK))
import generate_kokoro_german as german

def main():
    rows = json.loads((ROOT/'tools/town_musicians.json').read_text())['pages']
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    pack = PACK/'models/kokoro'
    engine = Kokoro.from_session(ort.InferenceSession(str(pack/'model_uint8.onnx'), sess_options=options, providers=['CPUExecutionProvider']), str(pack/'voices-v1.0.bin'))
    for lang,voice in [('en','af_bella'),('es','ef_dora'),('de','dm_martin')]:
        if lang == 'de':
            model = german.MODEL_DIR
            session = ort.InferenceSession(str(model/'kokoro-e2e.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
            vocab = json.loads((model/'vocab_index.json').read_text())['vocab']
            ref = np.fromfile(model/'voices/dm_martin.bin', dtype=np.float32).reshape(1,256)
        for profile,speed in (PROFILES.items() if lang=='en' else [('normal',.8)]):
            for row in rows:
                name = f"assets/jungle-book/story-sounds/{lang}/{row['asset']}.wav"
                target = ROOT/profile_path(name,profile)
                if target.exists() and target.with_suffix('.speech.json').exists(): continue
                text = row[lang]
                if lang == 'de':
                    # Local espeak supplies German phonemes for words outside the pack dictionary.
                    from phonemizer.backend import EspeakBackend
                    phonemes = EspeakBackend('de', with_stress=True).phonemize([text])[0]
                    chunks = german.split_phonemes(phonemes)
                    audio = np.concatenate([german.synthesize_chunk(session,vocab,c,ref) for c in chunks]); rate=24000
                else:
                    audio,rate = engine.create(text,voice=voice,speed=speed,lang='en-us' if lang=='en' else 'es')
                assert np.isfinite(audio).all() and np.max(np.abs(audio))>.005
                data = subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-f','f32le','-ar',str(rate),'-ac','1','-i','pipe:0','-f','s16le','-ar','22050','-ac','1','pipe:1'],input=np.asarray(audio,dtype='<f4').tobytes(),stdout=subprocess.PIPE,check=True).stdout
                save(target,data,dict(text=text,model='kokoro-82m-uint8' if lang!='de' else 'kokoro-german-martin',voice=voice,language=lang,speed=speed,profile=profile,model_sha256=digest(pack/'model_uint8.onnx' if lang!='de' else model/'kokoro-e2e.onnx')))
                print(lang,profile,row['id'],flush=True)
    corpus_path=ROOT/'tools/english_speech_corpus.json'
    corpus=json.loads(corpus_path.read_text())
    manifest_path=ROOT/'assets/speech-profiles.json'
    manifest=json.loads(manifest_path.read_text())
    for row in rows:
        name=f"assets/jungle-book/story-sounds/en/{row['asset']}.wav"
        corpus[name]={'text':row['en']}
        for profile in PROFILES: manifest['profiles'][profile]['voices'][name]=profile_path(name,profile)
    corpus_path.write_text(json.dumps(corpus,ensure_ascii=False,indent=2)+'\n')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
