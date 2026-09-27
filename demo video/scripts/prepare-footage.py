"""Prepare two editorial crops from the licensed source; keep the source untouched."""
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'public/footage/workspace-watch-1827.mp4'
GRADE = 'eq=contrast=1.07:saturation=0.82:brightness=-0.012,colorbalance=rs=0.012:bs=-0.008'
shots = [
 ('typing-edit.mp4','2.6','3.5','crop=1536:864:384:216'),
 ('wrist-edit.mp4','8.0','1.2','crop=1536:864:384:0,setpts=1.25*PTS'),
]
for name,start,duration,crop in shots:
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',start,'-t',duration,'-i',str(SOURCE),'-an','-vf',f'{crop},scale=1920:1080:flags=lanczos,{GRADE},fps=30','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(ROOT/'public/footage'/name)],check=True)
 print('Prepared',name)
