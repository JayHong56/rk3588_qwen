import os, subprocess
from pathlib import Path

def play_audio(path, player=None, device=None):
    wav=Path(path)
    if not wav.exists(): raise FileNotFoundError(wav)
    player=player or os.environ.get('AUDIO_PLAYER','aplay'); device=device or os.environ.get('AUDIO_DEVICE','')
    if player=='aplay':
        cmd=['aplay','-q'];
        if device: cmd += ['-D', device]
        cmd.append(str(wav))
    elif player=='ffplay': cmd=['ffplay','-nodisp','-autoexit','-loglevel','error',str(wav)]
    elif player=='pw-play': cmd=['pw-play',str(wav)]
    else: raise ValueError('unsupported AUDIO_PLAYER='+player)
    subprocess.run(cmd,check=True)
