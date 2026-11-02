"""Bounded live text pages for the native ASC/DCS kneeboard; no cockpit patch."""
import textwrap
import unicodedata
import uuid

PAGES=20
LINES=24
WIDTHS={'PAGE':22,'FIELD':14,'VALUE':34}


def ascii_text(value):
    text=str(value).replace('→','->').replace('·','/').replace('°',' deg')
    text=unicodedata.normalize('NFKD',text).encode('ascii','replace').decode('ascii')
    return ''.join(c if c=='\n' or 32<=ord(c)<=126 else ' ' for c in text)


def build_pages(report):
    lines=[]
    for section in report['sections']:
        lines.append((ascii_text(section['title']).upper(),'','','S'))
        for row in section['rows']:
            value=ascii_text(row['value'])
            if row.get('position_ddm') and row.get('entry')!='Position':value+='  '+ascii_text(row['position_ddm'])
            if row.get('speed'):value+='  SPD '+ascii_text(row['speed'])
            if row.get('altitude'):value+='  ALT '+ascii_text(row['altitude'])
            fields=[ascii_text(row['page']),ascii_text(row.get('entry','')),value]
            wrapped=[textwrap.wrap(text,width=width,replace_whitespace=False,drop_whitespace=True) or ['']
                     for text,width in zip(fields,WIDTHS.values())]
            for i in range(max(map(len,wrapped))):
                lines.append(tuple(col[i] if i<len(col) else '' for col in wrapped)+('R' if i==0 else 'C',))
    count=(len(lines)+LINES-1)//LINES
    if not count:raise ValueError('Prepare a manual plan first')
    if count>PAGES:raise ValueError(f'This plan exceeds the {PAGES}-page live kneeboard capacity')
    pages=[]
    for start in range(0,len(lines),LINES):
        part=lines[start:start+LINES]
        columns={key:'\n'.join(row[col] for row in part) for col,key in enumerate(WIDTHS)}
        columns['LAYOUT']=''.join(row[3] for row in part)
        pages.append(columns)
    return dict(title=ascii_text(report['subtitle'])[:80],pages=pages)


def parse_status(response):
    parts=response.split()
    if len(parts)!=7 or parts[:3]!=['OK','KB_STATUS','1']:raise ValueError('Updated live-kneeboard bridge required')
    ready,count,capacity=map(int,parts[3:6])
    if ready not in (0,1) or not 0<=count<=PAGES or capacity!=PAGES:raise ValueError('Incompatible live kneeboard')
    return dict(ready=bool(ready),pages=count,capacity=capacity,revision=parts[6])


def publish(exchange,report):
    content=build_pages(report)
    status=parse_status(exchange('KB_STATUS'))
    if not status['ready']:raise ValueError('Live kneeboard page is not loaded. Install the update and start DCS once, then open the C-130J CDU-plan kneeboard page.')
    transaction=uuid.uuid4().hex
    def encoded(text):return text.encode('ascii').hex()
    count=len(content['pages'])
    if exchange(f'KB_BEGIN|{transaction}|{count}|{encoded(content["title"])}')!=f'OK KB_BEGIN {transaction}':raise ValueError('Kneeboard did not begin the update')
    for page,columns in enumerate(content['pages'],1):
        for column,text in columns.items():
            if exchange(f'KB_DATA|{transaction}|{page}|{column}|{encoded(text)}')!=f'OK KB_DATA {transaction} {page} {column}':raise ValueError('Kneeboard did not accept the plan text')
    if exchange('KB_COMMIT|'+transaction)!=f'OK KB_COMMITTED {transaction} {count}':raise ValueError('Kneeboard update was not verified')
    return dict(message=f'Live kneeboard updated: {count} page'+('s' if count!=1 else '')+'.',pages=count,revision=transaction)
