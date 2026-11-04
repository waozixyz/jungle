"""Diagonal lettering uses the usable plank, in both scene orientations."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import title_scenes as title

class SignRotation(unittest.TestCase):
    def test_labels_fill_and_follow_each_plank(self):
        _,scenes,_,_=title.Load()
        diagonal=flat=0
        for scene in scenes:
            for h in scene['hotspots']:
                if not h.get('sign'):
                    continue
                old=h['sign']['label_rect']
                box,angle=title.SignTextLayout(h,h['glow_rect'],old)
                if not h['sign']['direction'].startswith('diagonal-'):
                    flat+=1
                    self.assertEqual((box,angle),(old,0))
                    continue
                diagonal+=1
                self.assertGreater(box[2],old[2]*2)
                self.assertGreater(box[3],old[3]*2)
                self.assertTrue(25<abs(angle/100)<31)
                self.assertEqual(angle>0,h['sign']['direction']=='diagonal-left')
                x,y,w,height=box
                cx=x+w/2;cy=y+height/2
                c=math.cos(math.radians(angle/100));s=math.sin(math.radians(angle/100))
                gx,gy,_,_=h['glow_rect']
                for dx,dy in [(-w/2,-height/2),(w/2,-height/2),(w/2,height/2),(-w/2,height/2)]:
                    self.assertTrue(title.Inside(h['polygon'],gx+cx+c*dx-s*dy,gy+cy+s*dx+c*dy),
                                    (scene['name'],h['id'],box,angle))
        self.assertEqual(diagonal,6)
        self.assertGreater(flat,0)

if __name__=='__main__':
    unittest.main()
