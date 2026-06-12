import os, re

def normalize_for_tts(text):
    s=text or ''
    if os.environ.get('STRIP_THINK','true').lower()=='true': s=re.sub(r'<think>.*?</think>','',s,flags=re.S|re.I)
    if os.environ.get('STRIP_MARKDOWN','true').lower()=='true':
        s=re.sub(r'```.*?```',' ',s,flags=re.S); s=re.sub(r'`([^`]+)`',r'',s); s=re.sub(r'\[([^\]]+)\]\([^\)]+\)',r'',s); s=re.sub(r'[*_#>~-]+',' ',s); s=re.sub(r'https?://\S+',' 链接 ',s)
    return re.sub(r'\s+',' ',s).strip()
