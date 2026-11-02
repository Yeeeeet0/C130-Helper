"""Open a fixed local PDF guide or a single page extracted from it."""
import os
import sys
from pathlib import Path

GUIDE='C130J_CDU_Helper_User_Guide.pdf'
TOPICS={'all':GUIDE,'review':'C130J_Help_01.pdf','airports':'C130J_Help_02.pdf',
        'map':'C130J_Help_03.pdf','automatic':'C130J_Help_04.pdf',
        'manual':'C130J_Help_05.pdf','data':'C130J_Help_06.pdf',
        'advanced':'C130J_Help_07.pdf','troubleshooting':'C130J_Help_08.pdf'}

def document_path(topic):
    if not isinstance(topic,str) or topic not in TOPICS:
        raise ValueError('Unknown help section')
    if getattr(sys,'frozen',False):
        base=Path(sys._MEIPASS)/'assets/help'
    else:
        base=Path(__file__).resolve().parents[1]/'output/pdf'
        if topic!='all':base=base/'help'
    path=base/TOPICS[topic]
    if not path.is_file():raise ValueError('PDF help is missing. Reinstall the latest Helper update.')
    return path

def open_document(topic='all'):
    path=document_path(topic)
    os.startfile(str(path))
    return {'message':'Opened PDF help.'}
