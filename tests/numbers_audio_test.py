"""Each of the ten number pages has verified spoken audio in every language."""
from array import array
import hashlib
import json
from pathlib import Path
import wave
ROOT=Path(__file__).resolve().parents[1]
words={'en':['One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten'],'de':['Eins','Zwei','Drei','Vier','Fünf','Sechs','Sieben','Acht','Neun','Zehn'],'es':['Uno','Dos','Tres','Cuatro','Cinco','Seis','Siete','Ocho','Nueve','Diez']}
for language,names in words.items():
    for number,name in enumerate(names,1):
        path=ROOT/f'assets/numbers/sounds/{language}/{number}.wav'
        metadata=json.loads(path.with_suffix('.speech.json').read_text())
        assert metadata['text']==name+'.',(language,number)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==metadata['sha256']
        with wave.open(str(path)) as audio:
            assert audio.getparams()[:3]==(1,2,22050)
            assert .2<audio.getnframes()/audio.getframerate()<8
            samples=array('h',audio.readframes(audio.getnframes()))
            assert max(abs(sample) for sample in samples)>200,'Silent number recording'
print('local number audio test: all 30 spoken number names, hashes, PCM format and non-silent audio passed')
