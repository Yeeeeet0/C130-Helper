"""Display-checked route loading. Never sends EXEC or route activation."""
import re
from difflib import SequenceMatcher


class MenuItemNotFound(RuntimeError):
    def __init__(self, message, available):
        super().__init__(message)
        self.available = available


def indication(raw):
    raw=raw.replace('\r\n','\n')
    pairs = re.findall(r'^-{3,}[ \t]*\n([^\n]+)\n([^\n]*)', raw,re.M)
    values = [value.strip() for _, value in pairs]
    named = {name.strip(): value.strip() for name, value in pairs}
    if not named.get('cni_title'):
        raise RuntimeError('CDU display is blank or cannot be read')
    scratch_index=next((i for i,(name,_) in enumerate(pairs) if name.strip()=='cni_scratchpad'),None)
    if scratch_index==len(pairs)-2 and re.fullmatch(r'\{[A-Fa-f0-9-]{36}\}',pairs[-1][0].strip()):
        named['cni_scratchpad_error']=pairs[-1][1].strip()
    # CNI draws the inverted DELETE prompt through scratch_error, whose
    # element has a generated GUID instead of the cni_scratchpad name.
    # Normalize only the exact final prompt; never search route text for it.
    if pairs and pairs[-1][1].strip().upper() in ('*DELETE*','DELETE'):
        named['cni_scratchpad']=pairs[-1][1].strip()
    return named, values


MENU_SELECT = {'L': (2,3,4,5), 'R': (8,9,10,11)}


def route_input_count(plan):
    """Verified fields/selections, plus reset and LEGS cleanup operations."""
    total=3+len(plan.get('fixes',[]))+2*len(plan.get('custom_waypoints',[]))+int(plan.get('overwrite',False))
    for side in ('departure','arrival'):
        terminal=plan.get(side,{})
        if terminal.get('runway'):
            total+=1
            if terminal.get('mode')=='procedure':
                total+=1+bool(terminal.get('procedure',{}).get('transition'))
    aids=plan.get('arrival_radios',{})
    return total+2*bool(aids.get('ils'))+bool(aids.get('tacan'))+sum(len(p.get('constraint',{})) for p in plan.get('constraint_fixes',[]))


def require_empty_route(values, route_number=1):
    for header in ('ORIGIN', 'DEST'):
        positions=[i for i,v in enumerate(values) if v==header]
        if len(positions)!=1 or positions[0]+1>=len(values):
            raise RuntimeError('Cannot identify the RTE '+str(route_number)+' '+header+' field; no route entries sent')
        value=values[positions[0]+1]
        # Fresh CNI export: ORIGIN is ]]]] and DEST is an empty string.
        # Other CNI states use dashes/underscores for unfilled fields.
        if not re.fullmatch(r'[-_\[\] ]*',value):
            raise RuntimeError('RTE '+str(route_number)+' must be empty before automatic loading: '+header+' contains '+repr(value))


def page_number(values):
    for value in values:
        match=re.fullmatch(r'(\d+)\s*/\s*(\d+)',value)
        if match:
            current,total=map(int,match.groups())
            if 1<=current<=total<=100:
                return current,total
    return None


def placeholder(value):
    return bool(re.fullmatch(r'[-_\[\] ]*',value))


def legs_rows(values, known_names=(), via_names=(), route_number=1, constraints=False):
    """Decode LEGS rows in the installed Lua page's speed/altitude order."""
    page=page_number(values)
    if not page:raise RuntimeError('Cannot identify the LEGS page counter')
    start=next(i for i,v in enumerate(values) if re.fullmatch(r'\d+\s*/\s*\d+',v))+1
    footer=next((i for i in range(start,len(values)) if re.fullmatch(r'ROUTE\s+'+str(route_number)+'>',values[i])),None)
    if footer is None:raise RuntimeError('Cannot identify the LEGS route footer')
    data=values[start:footer];rows=[];begin=0;i=0
    speed=r'(?:[0-9]{2,3}|---)[A-Z+\-]?/'
    altitude=r'(?:(?:FL)?[+\-]?\d{2,5}[A-Z+\-]?|[-_]{2,8})'
    metadata=r'(?:[\d.\-]+T?[\^°]T?|[\d.\-]+(?:NM|KM)|[\d\-]{2,4}:[\d\-]{2})'
    vias=set(via_names)|{'DIR','DIRECT','DCT','SID','STAR','APPR','CARP','HOLD','RNDZ','LZ'}
    known=set(known_names)
    while i<len(data):
        if 'DISCONTINUITY' in data[i]:
            # Empty discontinuity rows can omit their speed/altitude fields.
            # In that case the next bearing or marker starts the following row.
            event=next((j for j in range(i+1,len(data)) if re.fullmatch(r'[\d.\-]+T?[\^°]T?',data[j]) or 'DISCONTINUITY' in data[j] or re.fullmatch(speed,data[j])),len(data))
            if event==len(data) or not re.fullmatch(speed,data[event]):
                prefix=data[begin:i]
                if not prefix or not placeholder(prefix[-1]) or any(v and not placeholder(v) and not re.fullmatch(metadata,v) and not re.fullmatch(r'\d+\.\d+',v) for v in prefix):
                    raise RuntimeError('Cannot identify an empty LEGS discontinuity row')
                next_start=event
                if event<len(data) and 'DISCONTINUITY' in data[event]:
                    next_start=event-1
                    if next_start<=i or not placeholder(data[next_start]):raise RuntimeError('Ambiguous consecutive LEGS discontinuities')
                tail=[v for v in data[i+1:next_start] if v]
                if event==len(data) and len(tail)==2 and placeholder(tail[-1]):tail.pop()
                if len(tail)>1 or any(v not in vias and not placeholder(v) for v in tail):
                    raise RuntimeError('Unrecognized LEGS discontinuity fields')
                rows.append(dict(name=None,discontinuity=True));begin=next_start;i=next_start
                continue
        if not re.fullmatch(speed,data[i]):i+=1;continue
        if i+1>=len(data) or not re.fullmatch(altitude,data[i+1]):
            raise RuntimeError('Unrecognized LEGS speed/altitude layout; no deletion attempted')
        body=data[begin:i];markers=[j for j,v in enumerate(body) if 'DISCONTINUITY' in v]
        if sum(bool(re.fullmatch(r'[\d.\-]+T?[\^°]T?',v)) for v in body)>1:
            raise RuntimeError('Merged LEGS rows could not be identified; no deletion attempted')
        if markers:
            j=markers[0]
            tail=[v for v in body[j+1:] if v]
            prefix=body[:j]
            if len(markers)!=1 or not j or not placeholder(body[j-1]) or len(tail)>1 or any(v not in vias and not placeholder(v) for v in tail) or any(v and not placeholder(v) and not re.fullmatch(metadata,v) and not re.fullmatch(r'\d+\.\d+',v) for v in prefix):
                raise RuntimeError('Cannot identify an empty LEGS discontinuity row')
            name=None
        else:
            candidates=[v for v in body if v and not re.fullmatch(metadata,v) and not re.fullmatch(r'\d+\.\d+',v)]
            if len(candidates)>1 and candidates[-1] in vias:candidates.pop()
            if any(not placeholder(v) for v in candidates):candidates=[v for v in candidates if not placeholder(v)]
            matches=[v for v in candidates if v in known]
            if len(matches)==1:name=matches[0]
            elif len(candidates)==1:name=None if placeholder(candidates[0]) else candidates[0]
            elif candidates and all(placeholder(v) for v in candidates):name=None
            else:raise RuntimeError('Cannot identify a LEGS waypoint row; cleanup stopped')
        row=dict(name=name,discontinuity=bool(markers))
        if constraints:row.update(speed_raw=data[i][:-1],altitude_raw=data[i+1],key=7+len(rows))
        rows.append(row)
        i+=2;begin=i
    if len(rows)>5 or sum(r['discontinuity'] for r in rows)!=sum('DISCONTINUITY' in v for v in data):
        raise RuntimeError('Unrecognized LEGS row count; no deletion attempted')
    if any(v and not placeholder(v) and not re.fullmatch(metadata,v) for v in data[begin:]):
        raise RuntimeError('Incomplete LEGS row; no deletion attempted')
    return rows


def constraint_fixes(rows):
    """Keep every planned occurrence as matching context, including unconstrained fixes."""
    from route_constraints import manual_values
    result=[]
    for row in rows:
        if not row.get('position'):continue
        fields=dict(manual_values(row.get('constraint')))
        if 'Altitude' in fields and int(fields['Altitude'])<0:
            raise ValueError('Automatic altitude entry currently requires 0 to 60000 ft; use Manual for negative altitude')
        result.append(dict(ident=row['value'],constraint={k.lower():v for k,v in fields.items()}))
    return result


def match_constraint_fixes(planned, actual):
    """Earliest/latest subsequences must agree for each constrained occurrence."""
    def match(reverse=False):
        cursor=len(actual)-1 if reverse else 0;found={}
        for i in (range(len(planned)-1,-1,-1) if reverse else range(len(planned))):
            while 0<=cursor<len(actual) and actual[cursor]!=planned[i]['ident']:cursor+=-1 if reverse else 1
            if not 0<=cursor<len(actual):raise RuntimeError('Planned fixes not found in final LEGS order; constraints not entered')
            found[i]=cursor;cursor+=-1 if reverse else 1
        return found
    first,last=match(),match(True);targets={}
    for i,point in enumerate(planned):
        if not point.get('constraint'):continue
        if first[i]!=last[i]:raise RuntimeError('Ambiguous LEGS occurrence for '+point['ident']+'; constraints not entered')
        targets[first[i]]=point
    return targets


def constraint_matches(raw, expected, altitude=False):
    """Only an exact restriction matches; never mistake A/B qualifiers for an exact value."""
    if not re.fullmatch(r'(?:FL)?\d+',raw):return False
    value=int(raw[2:])*100 if altitude and raw.startswith('FL') else int(raw)
    return value==int(expected)


def verify_constraint_rows(before,after,forward_altitude=None):
    """ASC carries an entered altitude forward; identities and speeds must stay fixed."""
    if len(before)!=len(after):raise RuntimeError('LEGS layout changed')
    for old,new in zip(before,after):
        if any(old.get(k)!=new.get(k) for k in ('name','key','discontinuity','speed_raw')):
            raise RuntimeError('Another LEGS row changed')
        if old.get('altitude_raw')!=new.get('altitude_raw'):
            if forward_altitude is None or not constraint_matches(new.get('altitude_raw',''),forward_altitude,True):
                raise RuntimeError('Unexpected downstream LEGS altitude change')


class RouteRunner:
    def __init__(self, exchange, wait, report, confirm_procedure=None):
        self.exchange, self.wait, self.report = exchange, wait, report
        self.confirm_procedure = confirm_procedure
        self.replacements = []
        self.custom_airports=set()
        self.record_custom_airport=lambda ident:None
        self.route_number = 1
        self.progress=lambda completed,total,label:None
        self._completed=0
        self._total=0
        self.set_speed('default')

    def set_speed(self,speed):
        if speed not in ('default','accelerated'):raise RuntimeError('Choose Default or Accelerated input speed')
        self.input_speed=speed

    def clear_start_scratchpad(self):
        previous=None;unchanged=0
        for _ in range(33):
            named,_=indication(self.exchange('READ').split('\n',1)[1])
            current=(named.get('cni_scratchpad','').strip(' []_'),named.get('cni_scratchpad_error','').strip())
            if not any(current):return
            unchanged=unchanged+1 if current==previous else 0
            if unchanged>=3:break
            previous=current
            self.report('Clearing starting scratchpad')
            self.press('CLR')
        raise RuntimeError('CDU starting scratchpad did not clear; inspect it before retrying')

    def advance(self,label):
        if self._total:
            self._completed+=1
            if self._completed>self._total:raise RuntimeError('CDU progress count exceeded required inputs')
            self.progress(self._completed,self._total,label)

    @property
    def rte_title(self):return 'RTE '+str(self.route_number)+'$'

    @property
    def legs_title(self):return 'LEGS '+str(self.route_number)+'$'

    def read(self, title=None, allow_delete=False, expected_scratch=None):
        named, values = indication(self.exchange('READ').split('\n', 1)[1])
        if title and not re.search(title, named['cni_title']):
            raise RuntimeError('Unexpected CDU page: '+named['cni_title'])
        scratch = named.get('cni_scratchpad', '').strip(' []_')
        error=named.get('cni_scratchpad_error','')
        if error and not (allow_delete and error.upper() in ('*DELETE*','DELETE')):
            raise RuntimeError('CDU scratchpad needs attention: '+error)
        if expected_scratch is not None:
            if scratch!=expected_scratch:raise RuntimeError('CDU did not confirm complete entry; expected '+expected_scratch+', found '+(scratch or '(empty)'))
        elif scratch and not (allow_delete and scratch.upper() in ('*DELETE*','DELETE')):
            raise RuntimeError('CDU scratchpad needs attention: '+scratch)
        return named, values

    def await_page(self,title,submitted_scratch=None):
        error=None
        for _ in range(40 if self.input_speed=='accelerated' else 6):
            try:return self.read(title)
            except RuntimeError as ex:
                error=ex
                clearing=submitted_scratch is not None and str(ex)=='CDU scratchpad needs attention: '+submitted_scratch
                if 'Unexpected CDU page' not in str(ex) and not clearing:raise
                if self.wait(.03 if self.input_speed=='accelerated' else .2):raise RuntimeError('Route loading stopped')
        raise error

    def press(self, key, settle=None):
        if self.wait(0):
            raise RuntimeError('Route loading stopped before the next key')
        self.exchange('KEY|'+key)
        if settle is None:settle=0 if self.input_speed=='accelerated' else .03 if key.startswith('KBD_') else .35
        if self.wait(settle):
            raise RuntimeError('Route loading stopped; inspect the partially entered route')

    def entry(self, text, key, title):
        self.read(title)
        self.type_text(text)
        self.read(title,expected_scratch=text)
        self.press('SELECT_'+str(key))
        _, values = self.await_page(title,submitted_scratch=text)
        if text not in values:
            raise RuntimeError('CDU did not confirm '+text+'; inspect identifier selection and route')

    def type_text(self, text, fast=False):
        if not re.fullmatch(r'[A-Z0-9. ]+', text):
            raise RuntimeError('Unsupported CDU entry: '+text)
        for char in text:
            key={'.':'KBD_DOT',' ':'KBD_SPACE'}.get(char,'KBD_'+char)
            self.press(key)

    def airport_entry(self,plan,role,key):
        ident=plan[role]
        known_custom=ident in self.custom_airports
        database_error=False;named={};values=[]
        if not known_custom:
            self.read(self.rte_title);self.type_text(ident);self.read(self.rte_title,expected_scratch=ident);self.press('SELECT_'+str(key))
            try:named,values=self.await_page(self.rte_title+'|^'+re.escape(ident)+' CUSTOM DATA$',submitted_scratch=ident)
            except RuntimeError as ex:
                if str(ex)!='CDU scratchpad needs attention: NOT IN DATABASE':raise
                named,values=self.read(self.rte_title,expected_scratch='NOT IN DATABASE')
                self.press('CLR');self.read(self.rte_title);database_error=True
        if known_custom or named.get('cni_title')==ident+' CUSTOM DATA' or database_error:
            fallback=plan.get('airport_fallbacks',{}).get(role)
            if not fallback or fallback.get('ident')!=ident:
                raise RuntimeError('Airport '+ident+' is unknown to the CDU and no selected runway centre coordinates are available. Select a runway before retrying.')
            side='departure' if role=='origin' else 'arrival'
            terminal=plan.get(side,{})
            if terminal.get('mode')=='procedure':
                raise RuntimeError('Airport '+ident+' is unknown to the CDU. Its native SID/STAR cannot be loaded; choose a terminal-fix or ATC alternative before using the runway-coordinate fallback.')
            self.report('Airport '+ident+' unknown · using runway '+fallback['runway']+' centre '+fallback['position'])
            self._total+=2-int(bool(terminal.get('runway')))
            custom_ident=fallback['custom_ident']
            self.create_custom_waypoints([dict(fallback,ident=custom_ident)])
            self.custom_airports.add(ident);self.record_custom_airport(ident)
            self.route();self.entry(custom_ident,key,self.rte_title)
            plan[role]=custom_ident
            self.airport_fallback_sides.add(side)
            self.replacements.append(ident+' uses RW'+fallback['runway']+' coordinates as '+custom_ident)
            return
        if not re.search(self.rte_title,named['cni_title']):raise RuntimeError('Unexpected CDU page: '+named['cni_title'])
        header='ORIGIN' if role=='origin' else 'DEST'
        positions=[i for i,v in enumerate(values[:-1]) if v==header]
        if len(positions)!=1 or values[positions[0]+1]!=ident:raise RuntimeError('CDU did not confirm '+ident+' in '+header)

    def create_custom_waypoints(self,points):
        for point in points:
            ident,position=point['ident'],point['position']
            self.report('Setting custom waypoint '+ident)
            title='^'+re.escape(ident)+' CUSTOM DATA$'
            named,values=self.read()
            if not re.search(title,named['cni_title']):
                if named['cni_title'].endswith(' CUSTOM DATA') and 'CUSTOM LIST>' in values:
                    self.press('SELECT_12');self.await_page('^CUSTOM DATA LIST$')
                elif named['cni_title']!='CUSTOM DATA LIST':
                    if named['cni_title']!='INDEX':self.press('INDEX');_,values=self.await_page('^INDEX$')
                    if page_number(values)==(1,2):self.press('NEXT');_,values=self.await_page('^INDEX$')
                    if page_number(values)!=(2,2) or 'CUSTOM DATA>' not in values:raise RuntimeError('Cannot locate INDEX 2 CUSTOM DATA')
                    self.press('SELECT_8');self.await_page('^CUSTOM DATA LIST$')
                self.type_text(ident,fast=True);self.read('^CUSTOM DATA LIST$',expected_scratch=ident)
                self.press('SELECT_1');_,values=self.await_page(title,submitted_scratch=ident)
            self.advance('Custom identifier '+ident)
            normalize=lambda v:re.sub(r'[\s\^°]','',v)
            labels=[i for i,v in enumerate(values[:-1]) if v=='LAT/LON']
            if len(labels)!=1 or 'POSITION' not in values:raise RuntimeError('Cannot identify custom waypoint position fields')
            existing=values[labels[0]+1]
            if normalize(existing)!=position:
                self.type_text(position,fast=True);self.read(title,expected_scratch=position)
                self.press('SELECT_2');_,values=self.await_page(title,submitted_scratch=position)
                if not any(v=='LAT/LON' and normalize(values[i+1])==position for i,v in enumerate(values[:-1])):raise RuntimeError('CDU did not confirm custom waypoint position '+ident)
            self.advance('Custom position '+ident)

    def tune_arrival(self, aids):
        """Tune only explicitly associated aids; verify each individual receiver."""
        completed = []
        ils, tacan = aids.get('ils'), aids.get('tacan')
        if ils or tacan:
            self.press('NAV_TUNE'); self.await_page('^NAV TUNE INDEX$')
        for radio, aid, value, key in [('VOR1', ils, 'frequency', 7), ('TAC1', tacan, 'channel', 9)]:
            if not aid:
                continue
            target = aid[value]
            self.report('Setting '+radio+' to '+target)
            self.read('^NAV TUNE INDEX$')
            self.type_text(target);self.read('^NAV TUNE INDEX$',expected_scratch=target);self.press('SELECT_'+str(key))
            _, values = self.await_page('^NAV TUNE INDEX$',submitted_scratch=target)
            starts = [i for i,v in enumerate(values) if re.fullmatch('<'+radio+r'(?:\s+OFF)?',v)]
            if len(starts) != 1:
                raise RuntimeError('Cannot identify '+radio+' tuning row')
            start = starts[0]+1
            end = next((i for i in range(start,len(values)) if re.match(r'<(?:VOR[12]|TAC[12]|ADF[12])',values[i])),len(values))
            row = values[start:end]
            if radio == 'VOR1':
                confirmed = any(re.fullmatch(r'\d{3}\.\d{1,3}',v) and abs(float(v)-float(target))<.001 for v in row)
            else:
                confirmed = any(re.fullmatch(r'0*'+re.escape(target),v.replace(' ','')) for v in row)
            if not confirmed:
                raise RuntimeError('CDU did not confirm '+radio+' '+target)
            completed.append(radio+' '+target)
            self.advance(radio+' '+target)
        if ils:
            self.report('Loading ILS '+ils['ident']+' into INDEX 2 / NAV DATA')
            self.press('INDEX'); _, values = self.await_page('^INDEX$')
            if page_number(values) == (1,2):
                self.press('NEXT'); _, values = self.await_page('^INDEX$')
            if page_number(values) != (2,2) or 'NAV DATA>' not in values:
                raise RuntimeError('Cannot confirm INDEX page 2 NAV DATA menu')
            self.press('SELECT_7'); self.await_page('^NAV DATA$')
            self.type_text(ils['ident']);self.read('^NAV DATA$',expected_scratch=ils['ident']);self.press('SELECT_1')
            _, values = self.await_page('^NAV DATA$',submitted_scratch=ils['ident'])
            labels = [i for i,v in enumerate(values) if v == 'IDENT']
            if len(labels)!=1 or values[labels[0]+1:labels[0]+2] != [ils['ident']]:
                raise RuntimeError('NAV DATA did not confirm ILS identifier '+ils['ident'])
            completed.append('NAV DATA '+ils['ident'])
            self.advance('NAV DATA '+ils['ident'])
        return '; '.join(completed + aids.get('notes', []))

    def route(self):
        named,values=self.read()
        if re.search(self.rte_title,named['cni_title']):
            self.route_first_page(values)
            return
        if re.search(r'(?:RWYS|SIDS|STARS|TRANS|REVIEW)$',named['cni_title']) and '<ROUTE '+str(self.route_number) in values:
            self.press('SELECT_6');_,values=self.await_page(self.rte_title)
            self.route_first_page(values)
            return
        if re.search(self.legs_title,named['cni_title']) and 'ROUTE '+str(self.route_number)+'>' in values:
            self.press('SELECT_12');_,values=self.await_page(self.rte_title)
            self.route_first_page(values)
            return
        if named['cni_title']!='INDEX':
            self.press('INDEX'); _,values=self.await_page('^INDEX$')
        if page_number(values)==(2,2):
            self.press('PREV');self.await_page('^INDEX$')
        self.press('SELECT_'+str(6+self.route_number)); self.await_page(self.rte_title)

    def route_first_page(self,values):
        for _ in range(100):
            number=page_number(values)
            if number is None or number[0]==1:return
            if number[0]>3:
                # A deep header return is cheaper through INDEX than many PREVs.
                self.press('INDEX');self.await_page('^INDEX$')
                self.press('SELECT_'+str(6+self.route_number));_,values=self.await_page(self.rte_title)
                if not page_number(values) or page_number(values)[0]!=1:raise RuntimeError('CDU did not return to the route header')
                return
            self.press('PREV')
            for _ in range(6):
                _,values=self.read(self.rte_title)
                following=page_number(values)
                if following and following[0]==number[0]-1:break
                if self.wait(.2):raise RuntimeError('Route loading stopped')
            else:raise RuntimeError('RTE page did not move back')
        raise RuntimeError('Could not reach the route header')

    def menu(self, target, title):
        seen = set()
        available=[]
        for _ in range(30):
            named, values = self.await_page(title)
            number=page_number(values)
            fingerprint = tuple(values)
            if fingerprint in seen:
                break
            seen.add(fingerprint)
            for side in ('L', 'R'):
                choices = [v for v in values if (v.startswith('<') if side=='L' else v.endswith('>'))
                           and not re.search(r'ROUTE|REVIEW', v)]
                # Installed CNI menus use L2–L5 and R2–R5.
                choices = list(dict.fromkeys(choices))
                available.extend(v.strip('<> ') for v in choices)
                for i, value in enumerate(choices):
                    if value.strip('<> ').upper() == target.strip().upper() and i < 4:
                        self.report('Selecting '+target+' from '+named['cni_title'])
                        self.press('SELECT_'+str(MENU_SELECT[side][i]))
                        for _ in range(6):
                            selected,shown=self.read()
                            if selected['cni_title']!=named['cni_title'] or tuple(shown)!=fingerprint:
                                return
                            if self.wait(.2):raise RuntimeError('Route loading stopped')
                        raise RuntimeError('CDU did not confirm menu selection: '+target)
            if number and number[0]>=number[1]:
                break
            self.press('NEXT')
            for _ in range(6):
                _,next_values=self.read(title)
                changed=page_number(next_values)!=number if number else tuple(next_values)!=fingerprint
                if changed:break
                if self.wait(.2):raise RuntimeError('Route loading stopped')
            else:raise RuntimeError('CDU menu page did not advance while searching for '+target)
        raise MenuItemNotFound('CDU menu item not found: '+target+'. Available: '+', '.join(dict.fromkeys(available))+('. Review the separate CDU runway designation in the planner.' if 'RWYS' in title else ''), list(dict.fromkeys(available)))

    def suggest_procedure(self, target, error, title, reopen=None):
        choices=[v for v in error.available if re.fullmatch(r'[A-Z0-9]{2,10}',v) and v not in ('NONE','INDEX','RETURN')]
        if not choices or self.confirm_procedure is None:
            raise error
        suggestion=max(choices,key=lambda v:SequenceMatcher(None,target,v).ratio())
        named,values=self.read(title)
        snapshot=tuple(values)
        self.report(target+' not available. Closest name: '+suggestion+'. Hold CAPS for 1.5 seconds, then release to accept; Deny / Stop in the app cancels. Check the substituted procedure and restrictions.')
        if self.confirm_procedure(target,suggestion) is not True:
            raise RuntimeError('Procedure replacement was not explicitly accepted; route loading halted')
        if reopen:
            # CAPS opens its own page. Re-enter the selected runway's list
            # after the acceptance gesture has released the cockpit button.
            self.read()
            reopen()
            self.await_page(title)
        else:
            current,shown=self.read(title)
            if current['cni_title']!=named['cni_title'] or tuple(shown)!=snapshot:
                raise RuntimeError('CDU procedure menu changed while awaiting CAPS confirmation')
        # Navigate only after acceptance; the confirmation itself sends no keys.
        for _ in range(30):
            _,values=self.read(title)
            number=page_number(values)
            if not number or number[0]==1:break
            self.press('PREV');self.await_page(title)
        else:raise RuntimeError('Could not return to first procedure page')
        self.menu(suggestion,title)
        self.replacements.append(target+' → '+suggestion)
        self.report('Accepted replacement '+target+' → '+suggestion)
        return suggestion

    def procedure_list(self, terminal, departure):
        named,values=self.read()
        in_index=named['cni_title']=='DEP/ARR INDEX' and 'RTE '+str(self.route_number) in values
        if not in_index:
            if not re.search(self.rte_title,named['cni_title']) or '<DEP/ARR' not in values:
                self.route()
            self.press('SELECT_5');self.await_page('^DEP/ARR INDEX$')
        self.press('SELECT_1' if departure else 'SELECT_8')
        self.menu(terminal.get('cdu_runway') or terminal['runway'], 'RWYS')

    def terminal(self, terminal, departure):
        if not terminal.get('runway'):
            return
        self.procedure_list(terminal,departure)
        self.advance('Departure runway' if departure else 'Arrival runway')
        if terminal['mode']=='procedure':
            p=terminal['procedure']
            try:
                self.menu(p['name'], 'SIDS|STARS')
            except MenuItemNotFound as ex:
                def reopen():
                    self.procedure_list(terminal,departure)
                    self.await_page('^DEPARTURE SIDS$' if departure else '^ARRIVAL STARS$')
                replacement=self.suggest_procedure(p['name'],ex,'SIDS|STARS',reopen)
                p=dict(p,name=replacement)
                terminal['procedure']=p
            if p.get('transition'):
                self.menu(p['transition'], 'TRANS')
                self.advance('Procedure transition')
        named,values=self.read()
        # Selecting a SID/STAR can open REVIEW directly. R6 on that page
        # may be a return-to-list key, rather than an INSERT command.
        if 'REVIEW' not in named['cni_title']:
            if 'REVIEW>' not in values:
                raise RuntimeError('Expected a procedure review prompt on '+named['cni_title'])
            self.press('SELECT_12');self.await_page('REVIEW')
        name=terminal.get('procedure',{}).get('name')
        for _ in range(40):
            _, values=self.read('REVIEW')
            if name and not any(re.search(r'(?<![A-Z0-9])'+re.escape(name)+r'(?![A-Z0-9])',v) for v in values):
                raise RuntimeError('Procedure review does not confirm '+name)
            if any('INSERT' in v and v.endswith('>') for v in values):
                self.press('SELECT_12')
                break
            if 'END OF PROCEDURE' in values and any(re.fullmatch(r'(DEP SIDS|ARR STARS|STARS|SIDS)>',v) for v in values):
                # Native CNI has already applied the selection. Verify the
                # procedure in the actual route instead of pressing this key.
                break
            number=page_number(values)
            if number and number[0]>=number[1]:
                raise RuntimeError('Procedure review has no supported completion prompt')
            self.press('NEXT')
        else:
            raise RuntimeError('Procedure review did not reach its final page')
        self.route()
        if name:
            for _ in range(40):
                _,values=self.read(self.rte_title)
                if any(re.search(r'(?<![A-Z0-9])'+re.escape(name)+r'(?![A-Z0-9])',v) for v in values):
                    self.report('Verified '+name+' in RTE '+str(self.route_number))
                    self.advance(('SID ' if departure else 'STAR ')+name)
                    return
                number=page_number(values)
                if number and number[0]>=number[1]:break
                self.press('NEXT')
            raise RuntimeError('Selected procedure was not found in RTE '+str(self.route_number)+': '+name)

    def legs(self):
        named,values=self.read()
        if not re.search(self.legs_title,named['cni_title']):
            if not re.search(self.rte_title,named['cni_title']):
                self.route();_,values=self.read(self.rte_title)
            if not any(re.fullmatch(r'<LEGS\s+'+str(self.route_number),v) for v in values):
                raise RuntimeError('RTE '+str(self.route_number)+' does not offer LEGS; refusing to press an ERASE key')
            self.press('SELECT_6');self.await_page(self.legs_title)
        for _ in range(100):
            _,values=self.read(self.legs_title);number=page_number(values)
            if not number:raise RuntimeError('Cannot identify the LEGS page counter')
            if number[0]==1:return
            self.press('PREV')
            for _ in range(6):
                _,updated=self.read(self.legs_title);previous=page_number(updated)
                if previous and previous[0]==number[0]-1:break
                if self.wait(.2):raise RuntimeError('Route loading stopped')
            else:raise RuntimeError('LEGS page did not move back; cleanup stopped')
        raise RuntimeError('Could not return to the first LEGS page')

    def _leg_rows(self,values):
        return legs_rows(values,getattr(self,'_leg_names',()),getattr(self,'_leg_vias',()),self.route_number)

    def load_constraints(self,plan):
        planned=plan.get('constraint_fixes',[])
        if not any(p.get('constraint') for p in planned):return
        self.report('Matching speed / altitude targets on LEGS')
        self.legs()
        pages=[];actual=[];locations=[]
        def decode(values):
            return legs_rows(values,getattr(self,'_leg_names',()),getattr(self,'_leg_vias',()),self.route_number,True)
        def next_page(page,allow_auxiliary=False):
            self.press('NEXT')
            for _ in range(40):
                named,values=self.read()
                if allow_auxiliary and 'LEGS' in named['cni_title'] and any(tag in named['cni_title'] for tag in ('HIST','ALTN')):return False
                if not re.search(self.legs_title,named['cni_title']):raise RuntimeError('Unexpected CDU page: '+named['cni_title'])
                number=page_number(values)
                if number and number[0]==page:return True
                if self.wait(.03 if self.input_speed=='accelerated' else .2):raise RuntimeError('Route loading stopped')
            raise RuntimeError('LEGS did not advance during constraint entry')
        # Read-only preflight prevents a repeated procedure fix from receiving
        # an en-route restriction merely because it appears first.
        for page in range(1,101):
            _,values=self.read(self.legs_title);number=page_number(values)
            if not number or number[0]!=page:raise RuntimeError('Unexpected LEGS page while matching constraints')
            rows=decode(values)
            if any(r['discontinuity'] for r in rows):raise RuntimeError('LEGS still contains a discontinuity; constraints not entered')
            pages.append((number,rows))
            for local,row in enumerate(rows):
                if row['name'] is not None:
                    actual.append(row['name']);locations.append((page,local))
            if number[0]==number[1]:break
            if not next_page(page+1,True):
                self.press('PREV');self.await_page(self.legs_title);break
        else:raise RuntimeError('Constraint LEGS scan limit reached')
        targets={locations[i]:point for i,point in match_constraint_fixes(planned,actual).items()}
        self.legs()
        verified=0;required=sum(len(p.get('constraint',{})) for p in planned)
        forward_altitude=None
        for page,(number,expected) in enumerate(pages,1):
            _,values=self.read(self.legs_title)
            if page_number(values)!=number:raise RuntimeError('LEGS changed after constraint matching; stopped')
            current=decode(values)
            try:verify_constraint_rows(expected,current,forward_altitude)
            except RuntimeError as ex:raise RuntimeError('LEGS changed after constraint matching; stopped: '+str(ex)) from ex
            expected[:]=current
            for local,row in enumerate(expected):
                point=targets.get((page,local))
                if point is None:continue
                fields=point['constraint']
                try:
                    changed={name:value for name,value in fields.items() if not constraint_matches(row[name+'_raw'],value,name=='altitude')}
                    if changed:
                        self.report('Setting '+point['ident']+' speed / altitude · LEGS '+str(page))
                        # Submit both requested fields even if propagation has
                        # already satisfied one. Only an unspecified side is blank.
                        text=fields.get('speed','')+'/'+fields.get('altitude','')
                        self.read(self.legs_title)
                        for char in text:self.press('KBD_SLASH' if char=='/' else 'KBD_'+char)
                        self.read(self.legs_title,expected_scratch=text)
                        self.press('SELECT_'+str(row['key']))
                        _,after=self.await_page(self.legs_title,submitted_scratch=text)
                        updated=decode(after)
                        if page_number(after)!=number or len(updated)!=len(expected):raise RuntimeError('LEGS layout changed')
                        for i,(old,new) in enumerate(zip(expected,updated)):
                            if i!=local:
                                verify_constraint_rows([old],[new],fields.get('altitude') if i>local else None)
                            else:
                                if (old['name'],old['key'],old['discontinuity'])!=(new['name'],new['key'],new['discontinuity']):raise RuntimeError('Selected waypoint changed')
                                for field in ('speed','altitude'):
                                    if field in fields:
                                        if not constraint_matches(new[field+'_raw'],fields[field],field=='altitude'):raise RuntimeError('CDU did not confirm '+field+' '+fields[field])
                                    elif old[field+'_raw']!=new[field+'_raw']:raise RuntimeError('Unspecified '+field+' changed')
                        if 'altitude' in fields:
                            forward_altitude=fields['altitude']
                            self.report('Altitude '+forward_altitude+' applied forward by CDU; review arrival restrictions before EXEC')
                        expected[:]=updated;row=expected[local]
                    for field in fields:
                        self.advance(point['ident']+' '+field+' verified');verified+=1
                except RuntimeError as ex:
                    raise RuntimeError('Constraint entry stopped at '+point['ident']+' (LEGS '+str(page)+', R'+str(local+1)+'). '+str(verified)+'/'+str(required)+' fields verified; inspect remaining fields. '+str(ex)) from ex
            if page<len(pages):
                next_page(page+1)
        self.report(str(verified)+' speed / altitude fields verified')

    def _peek_next_legs(self,page,rows):
        """Check a boundary without leaving LEGS or reopening the route."""
        self.press('NEXT')
        for _ in range(6):
            named,values=self.read()
            if 'LEGS' in named['cni_title'] and any(tag in named['cni_title'] for tag in ('HIST','ALTN')):
                result=None;break
            number=page_number(values)
            if re.search(self.legs_title,named['cni_title']) and number and number[0]==page+1:
                result=(self._leg_rows(values),number);break
            if self.wait(.2):raise RuntimeError('Route loading stopped')
        else:raise RuntimeError('Cannot check the next LEGS boundary')
        self.press('PREV')
        _,back=self.await_page(self.legs_title)
        if not page_number(back) or page_number(back)[0]!=page or self._leg_rows(back)!=rows:
            raise RuntimeError('LEGS changed while checking the page boundary')
        return result

    def clear_discontinuities(self,plan=None):
        plan=plan or {}
        self._leg_names=set(plan.get('identifiers',()))|set(plan.get('fixes',()))|{plan.get('origin'),plan.get('destination')}
        self._leg_vias=set()
        for side in ('departure','arrival'):
            procedure=plan.get(side,{}).get('procedure',{})
            if procedure.get('name'):self._leg_vias.add(procedure['name'])
            self._leg_names.update(p['ident'] for p in procedure.get('points',()))
        self.report('Checking LEGS: gaps and consecutive duplicates…')
        self.duplicates_removed=0
        self.legs()  # Enter once. All subsequent work stays on this page stack.
        page=1;removed=0;completed={}
        def names(rows):return [r['name'] for r in rows if r['name'] is not None]
        def contains(sequence,following):
            iterator=iter(following)
            return all(any(value==candidate for candidate in iterator) for value in sequence)
        for _ in range(512):
            _,values=self.read(self.legs_title);number=page_number(values)
            if not number or number[0]!=page:
                raise RuntimeError('Unexpected LEGS page during cleanup')
            rows=self._leg_rows(values)
            row=next((i+1 for i,r in enumerate(rows) if r['discontinuity']),None)
            duplicate=False
            if row is None:
                earlier=[name for p in sorted(completed) if p<page for name in completed[p]]
                previous=earlier[-1] if earlier else None
                for i,r in enumerate(rows):
                    if r['name'] is None:continue
                    if r['name']==previous:
                        row=i+1;duplicate=True;break
                    previous=r['name']
            if row is None:
                completed[page]=names(rows)
                if number[0]==number[1]:
                    self.report(str(removed)+' gaps · '+str(self.duplicates_removed)+' duplicates removed.')
                    return removed
                self.press('NEXT')
                for _ in range(6):
                    named,following=self.read()
                    title=named['cni_title']
                    if 'LEGS' in title and any(label in title for label in ('HIST','ALTN')):
                        # An auxiliary page is not part of the route. Leave the
                        # display on the last verified main LEGS page.
                        self.press('PREV');self.await_page(self.legs_title)
                        self.report(str(removed)+' discontinuities removed; all main LEGS pages verified clear.')
                        return removed
                    if not re.search(self.legs_title,title):raise RuntimeError('Unexpected CDU page: '+title)
                    next_number=page_number(following)
                    if next_number and next_number[0]==page+1:break
                    if self.wait(.2):raise RuntimeError('Route loading stopped')
                else:raise RuntimeError('LEGS page did not advance; cleanup stopped')
                page+=1
                continue
            if removed+self.duplicates_removed>=128:raise RuntimeError('LEGS cleanup limit reached')
            boundary=None
            if number[0]<number[1] and (duplicate or not any(r['name'] is not None or r['discontinuity'] for r in rows[row:])):
                boundary=self._peek_next_legs(page,rows)
            label='duplicate '+str(rows[row-1]['name']) if duplicate else 'discontinuity'
            self.report('Removing '+label+' · LEGS '+str(page)+' L'+str(row))
            self.press('DEL')
            named,armed=self.read(self.legs_title,allow_delete=True)
            if named.get('cni_scratchpad','').strip().upper() not in ('*DELETE*','DELETE') or page_number(armed)!=number or self._leg_rows(armed)!=rows:
                raise RuntimeError('CDU did not arm deletion on the expected LEGS row')
            self.press('SELECT_'+str(row))
            _,after_values=self.read(self.legs_title);after_number=page_number(after_values)
            after_rows=self._leg_rows(after_values)
            if not after_number or after_number[0] not in (page,page-1):
                raise RuntimeError('LEGS moved unexpectedly after deletion; cleanup stopped')
            if after_rows==rows and after_number==number:
                # Consecutive gaps spanning pages can leave this page looking
                # identical. Verify the next page shifted by exactly one row.
                following=self._peek_next_legs(page,after_rows) if boundary else None
                previous=[r for r in boundary[0] if r['name'] is not None or r['discontinuity']] if boundary else []
                updated=[r for r in following[0] if r['name'] is not None or r['discontinuity']] if following else []
                pulled=bool(previous) and (previous[0]==rows[-1] if duplicate else previous[0]['discontinuity'])
                if not pulled or not following or (following==boundary) or updated[:len(previous)-1]!=previous[1:] or not contains(names(previous[1:] if duplicate else boundary[0]),names(following[0])):
                    raise RuntimeError('CDU did not remove the LEGS discontinuity; cleanup stopped')
            preserved=[r for i,r in enumerate(rows) if not duplicate or i!=row-1]
            if not contains(names(preserved),names(after_rows)):
                raise RuntimeError('Route waypoint sequence changed during cleanup; inspect the route before continuing')
            if after_number[0]==page:
                expected=[r for i,r in enumerate(rows) if i!=row-1 and (r['name'] is not None or r['discontinuity'])]
                actual=[r for r in after_rows if r['name'] is not None or r['discontinuity']]
                if actual[:len(expected)]!=expected:
                    replacement=[dict(name=None,discontinuity=True) if i==row-1 else r for i,r in enumerate(rows)]
                    replacement=[r for r in replacement if r['name'] is not None or r['discontinuity']]
                    if not duplicate or actual[:len(replacement)]!=replacement:
                        raise RuntimeError('CDU did not remove the expected LEGS '+label+'; cleanup stopped')
            else:
                # Removing the last entry can collapse the final page. Recheck
                # that page in place, including its previously verified names.
                page=after_number[0]
                if not contains(completed.get(page,[]),names(after_rows)):
                    raise RuntimeError('Earlier LEGS waypoints changed after page collapse')
                completed={p:v for p,v in completed.items() if p<page}
            if duplicate:self.duplicates_removed+=1
            else:removed+=1
            # Stay here: another discontinuity may have shifted into this page.
        raise RuntimeError('LEGS cleanup scan limit reached')

    def prepare_route(self, overwrite=False):
        _,values=self.read(self.rte_title)
        if not overwrite:
            require_empty_route(values,self.route_number)
            return
        def field(values,label):
            positions=[i for i,v in enumerate(values) if v==label]
            if len(positions)!=1 or positions[0]+1>=len(values):
                raise RuntimeError('Cannot identify selected route '+label+'; overwrite stopped')
            return values[positions[0]+1]
        def empty(value):return bool(re.fullmatch(r'[-_\[\] ]*',value))
        origin,destination=field(values,'ORIGIN'),field(values,'DEST')
        if not empty(origin) or not empty(destination):
            self.report('Overwriting RTE '+str(self.route_number)+': deleting its origin and route legs')
            if not empty(origin):
                self.press('DEL')
                named,_=self.read(self.rte_title,allow_delete=True)
                if named.get('cni_scratchpad','').strip().upper() not in ('DELETE','*DELETE*'):
                    raise RuntimeError('CDU did not arm origin deletion; overwrite stopped')
                self.press('SELECT_1')
                _,values=self.read(self.rte_title)
                if not empty(field(values,'ORIGIN')):
                    raise RuntimeError('CDU did not delete the selected route origin; overwrite stopped')
            # Some versions retain the destination field after clearing origin.
            if not empty(field(values,'DEST')):
                self.press('DEL');named,_=self.read(self.rte_title,allow_delete=True)
                if named.get('cni_scratchpad','').strip().upper() not in ('DELETE','*DELETE*'):
                    raise RuntimeError('CDU did not arm destination deletion; overwrite stopped')
                self.press('SELECT_7');_,values=self.read(self.rte_title)
        require_empty_route(values,self.route_number)
        self.legs()
        # CNI can retain multiple blank pages after clearing the origin.
        # Page count alone does not establish whether any route legs remain.
        expected=1;total=None
        for _ in range(100):
            _,values=self.read(self.legs_title)
            number=page_number(values)
            if not number or number[0]!=expected or total is not None and number[1]!=total:
                raise RuntimeError('LEGS pages changed during empty-route verification; no new route entered')
            total=number[1]
            rows=legs_rows(values,route_number=self.route_number)
            if any(r['name'] is not None or r['discontinuity'] for r in rows):
                raise RuntimeError('Selected route still contains LEGS after origin deletion; no new route entered')
            if expected==total:break
            self.press('NEXT')
            for _ in range(6):
                _,following=self.read(self.legs_title)
                if page_number(following)==(expected+1,total):break
                if self.wait(.2):raise RuntimeError('Route loading stopped')
            else:raise RuntimeError('LEGS page did not advance during empty-route verification; no new route entered')
            expected+=1
        else:raise RuntimeError('Empty-route LEGS verification limit reached')
        self.route()
        _,values=self.read(self.rte_title);require_empty_route(values,self.route_number)

    def run(self, plan):
        route_number=plan.get('route_number',1)
        if type(route_number) is not int or route_number not in (1,2):raise RuntimeError('Choose RTE 1 or RTE 2')
        if type(plan.get('overwrite',False)) is not bool:raise RuntimeError('Invalid overwrite selection')
        self.set_speed(plan.get('input_speed','default'))
        self.route_number=route_number
        self.airport_fallback_sides=set()
        self._completed=0;self._total=route_input_count(plan)
        self.progress(0,self._total,'Starting')
        self.clear_start_scratchpad()
        self.report('Loading origin and destination into RTE '+str(self.route_number))
        self.route()
        self.prepare_route(plan.get('overwrite',False))
        if plan.get('overwrite'):self.advance('Route cleared')
        if plan.get('custom_waypoints'):
            self.create_custom_waypoints(plan['custom_waypoints'])
            self.route()
        self.airport_entry(plan,'origin',1)
        self.advance('Departure '+plan['origin'])
        self.airport_entry(plan,'destination',7)
        self.advance('Arrival '+plan['destination'])
        # Enter direct legs before adding native SID/STAR legs.
        if plan['fixes']:
            self.press('NEXT')
            _,initial=self.read()
            # Some CNI versions expose a VIA/TO route page; the documented
            # LEGS page is used otherwise. Never type on an unknown layout.
            via='VIA' in initial and 'TO' in initial
            if not via:
                self.route();self.press('SELECT_6');self.await_page(self.legs_title)
        for fix in plan['fixes']:
            self.report('Loading route fix '+fix)
            for _ in range(30):
                _, values=self.read(self.rte_title if via else self.legs_title)
                if via:
                    if 'TO' not in values:raise RuntimeError('Expected VIA/TO route page')
                    slots=values[values.index('TO')+1:][:4]
                    empty=next((i for i,v in enumerate(slots) if v=='-----'),None)
                    key=7+empty if empty is not None else None
                else:
                    known=set(plan.get('identifiers',[]))|{plan['origin'],plan['destination']}|set(plan['fixes'])
                    vias={plan.get(side,{}).get('procedure',{}).get('name') for side in ('departure','arrival')}
                    slots=[r['name'] for r in legs_rows(values,known,vias,self.route_number)]
                    destination=[i for i,v in enumerate(slots) if v==plan['destination']]
                    key=1+destination[0] if len(destination)==1 else None
                if key is not None:
                    self.entry(fix,key,self.rte_title if via else self.legs_title)
                    self.advance('Waypoint '+fix)
                    break
                self.press('NEXT')
            else:
                raise RuntimeError('No empty route insertion position found')
        self.report('Loading departure selection')
        if 'departure' not in self.airport_fallback_sides:self.terminal(plan['departure'],True)
        self.report('Loading arrival selection')
        if 'arrival' not in self.airport_fallback_sides:self.terminal(plan['arrival'],False)
        removed=self.clear_discontinuities(plan)
        self.advance('LEGS verified')
        self.load_constraints(plan)
        try:
            radios=self.tune_arrival(plan.get('arrival_radios', {}))
        except RuntimeError as ex:
            raise RuntimeError('Route loaded and LEGS cleanup complete. Arrival radio setup stopped: '+str(ex)) from ex
        replacements='Accepted: '+', '.join(self.replacements)+'. ' if self.replacements else ''
        duplicates=getattr(self,'duplicates_removed',0)
        altitude_notice='Altitude applies forward; check arrival restrictions. ' if any('altitude' in p.get('constraint',{}) for p in plan.get('constraint_fixes',[])) else ''
        self.report('RTE '+str(self.route_number)+' loaded · '+str(removed)+' gaps'+(' · '+str(duplicates)+' duplicates' if duplicates else '')+' cleared. '+replacements+altitude_notice+'Review before EXEC.')
