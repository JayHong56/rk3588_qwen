import os, requests

def speak(text, play=None, sid=None, speed=None):
    base=os.environ.get('TTS_API_BASE','http://127.0.0.1:8011').rstrip('/')
    play=(os.environ.get('TTS_PLAY','true').lower()=='true') if play is None else play
    sid=int(os.environ.get('TTS_SID','0')) if sid is None else sid; speed=float(os.environ.get('TTS_SPEED','1.0')) if speed is None else speed
    r=requests.post(base+'/speak',json={'text':text,'play':play,'sid':sid,'speed':speed},timeout=180); r.raise_for_status(); return r.json()
def health():
    base=os.environ.get('TTS_API_BASE','http://127.0.0.1:8011').rstrip('/'); r=requests.get(base+'/health',timeout=10); r.raise_for_status(); return r.json()
