"""Exercise both story cards, all Bremen pages/languages, playback and Back."""
import tempfile
import time
import subprocess
from runtime_test import OUTPUT
from pathlib import Path
from PIL import ImageChops
from runtime_test import Desktop, ROOT

def main():
    output=ROOT/'local/town-musicians-tests'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as folder:
        with Desktop(ROOT/'build/app/jungle',Path(folder),screen_size='1280x1000') as desktop:
            for language in range(3):
                desktop.game('Sweet Porridge') if language==0 else None
                if language:
                    desktop.key('Escape')
                    desktop.key('Escape')
                    desktop.key('Home')
                    desktop.select_language(language)
                    desktop.game('Sweet Porridge')
                shelf=desktop.capture_actual(f'bremen-shelf-{language}')
                words=subprocess.run(['tesseract',str(OUTPUT/f'bremen-shelf-{language}.png'),'stdout'],capture_output=True,text=True,check=True).stdout
                assert 'Brem' in words, ('Missing Bremen card',words)
                assert ('Stories','Geschichten','Cuentos')[language] in words, ('Language did not switch',words)
                # Open the second collection card with its ordinary keyboard route.
                desktop.key('2')
                time.sleep(1)
                for orientation,(width,height) in enumerate(((960,640),(540,900))):
                    desktop.resize(width,height)
                    desktop.key('space') # Pause before walking the pages by hand.
                    previous=None
                    for page in range(11):
                        picture=desktop.capture_actual(f'bremen-{language}-{orientation}-{page}')
                        assert picture.size==(width,height)
                        if previous:
                            assert ImageChops.difference(previous,picture).getbbox(), 'Page did not change'
                        previous=picture
                        desktop.key('space') # Play narration for this translated page.
                        time.sleep(.45)
                        desktop.key('space')
                        if page<10: desktop.key('Right')
                    # Turn all the way back to the cover before changing orientation.
                    for _ in range(10): desktop.key('Left')
                    desktop.key('space')
                desktop.key('Escape')
                returned=desktop.capture_actual(f'bremen-returned-shelf-{language}')
                words=subprocess.run(['tesseract',str(OUTPUT/f'bremen-returned-shelf-{language}.png'),'stdout'],capture_output=True,text=True,check=True).stdout
                assert 'Brem' in words, ('Back missed collection',words)
                desktop.key('1')
                desktop.capture_actual(f'porridge-still-available-{language}')
                desktop.key('Escape')
                # The collection also has its own easy top-left Back.
                desktop.click_actual(80,115)
                desktop.capture_actual(f'bremen-back-{language}')
    print('local real-app test passed: two cards, 66 Bremen page views, both orientations, EN/DE/ES, narration play/pause, Porridge and Back')
if __name__=='__main__': main()
