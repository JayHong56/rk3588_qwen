import os, shlex, subprocess
from pathlib import Path

def play_wav(path: str, player: str = None, device: str = None, wait: bool = True):
    player = player or os.getenv("AUDIO_PLAYER", "aplay")
    if player.lower() in ("none","off","false","0"):
        return None
    wav = str(Path(path))
    if player == "aplay":
        cmd = ["aplay"]
        if device:
            cmd += ["-D", device]
        cmd += [wav]
    elif player == "ffplay":
        cmd = ["ffplay","-nodisp","-autoexit","-loglevel","warning",wav]
    elif player == "pw-play":
        cmd = ["pw-play", wav]
    else:
        cmd = shlex.split(player) + [wav]
    return subprocess.run(cmd, check=False) if wait else subprocess.Popen(cmd)
