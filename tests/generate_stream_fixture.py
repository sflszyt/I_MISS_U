from pathlib import Path
import sys
from tools.build_companion_page import build
out=Path(sys.argv[1]); out.mkdir(exist_ok=True)
for mode in ('proxy','byok'):
    html=build('synthetic',str(out),'owner',tts_origin='same',tts_token='synthetic',llm_proxy='/v1/chat/completions' if mode=='proxy' else '',default_key='' if mode=='proxy' else 'synthetic',default_provider='deepseek',voice_groups=True,auto_voice_session=True)
    (out/(mode+'.html')).write_text(html,encoding='utf-8')
