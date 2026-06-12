import os
ENDINGS=set('。！？!?；;\n')
def split_ready_sentences(buffer):
    maxc=int(os.environ.get('MAX_SENTENCE_CHARS','80')); minc=int(os.environ.get('MIN_SENTENCE_CHARS','4'))
    ready=[]; start=0
    for i,ch in enumerate(buffer):
        if ch in ENDINGS or i-start+1>=maxc:
            s=buffer[start:i+1].strip(); start=i+1
            if len(s)>=minc: ready.append(s)
    return ready, buffer[start:].strip()
