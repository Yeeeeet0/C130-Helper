"""Local headless Edge verification of the actual map UI and native chart decoder."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import tempfile
import time
from urllib.request import urlopen

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from desktop import build_page, locate_files
from cdu_helper import CduApi

from flight_plan_library import FlightPlanLibrary
library_temp=tempfile.TemporaryDirectory(prefix='planner-library-check-',dir=ROOT/'build')
assert Path(library_temp.name).resolve().is_relative_to((ROOT/'build').resolve())
api=CduApi();api._plan_library=FlightPlanLibrary(library_temp.name)
page,_=build_page(*locate_files())
shim='''<script>window.pywebview={api:new Proxy({}, {get:(_,name)=>(...args)=>fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,args})}).then(r=>r.json())})};</script>'''
page=page.replace('<head>','<head>'+shim)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        data=(ROOT/'build/manual-plan-preview.html').read_bytes() if self.path=='/manual-preview' else page.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body['name'] not in ('custom_waypoint','airport_procedures','preview_flight_plan','navigation_data','chart_tile','prepare_database_route','prepare_manual_plan','list_flight_plans','save_flight_plan','load_flight_plan','airway_segment','prepare_waypoints','prepare_ipra','status','connection','refresh_airport_reference'):
            self.send_error(400);return
        result={'error':'Simulated disconnected cockpit','connected':False} if body['name']=='connection' else getattr(api,body['name'])(*body['args'])
        data=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

class CDP:
    def __init__(self,url):
        from urllib.parse import urlparse
        u=urlparse(url);self.sock=socket.create_connection((u.hostname,u.port),timeout=60);self.pending=b'';self.seq=0
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        header=b''
        while b'\r\n\r\n' not in header:header+=self.sock.recv(4096)
        head,self.pending=header.split(b'\r\n\r\n',1)
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        assert b' 101 ' in head.split(b'\r\n',1)[0] and expected in head, head.decode(errors='replace')
    def read(self,n):
        while len(self.pending)<n:self.pending+=self.sock.recv(max(4096,n-len(self.pending)))
        data,self.pending=self.pending[:n],self.pending[n:];return data
    def call(self,method,params=None):
        self.seq+=1;data=json.dumps({'id':self.seq,'method':method,'params':params or {}}).encode();mask=os.urandom(4)
        length=len(data);head=bytes([0x81,0x80|length]) if length<126 else bytes([0x81,0xfe])+struct.pack('!H',length) if length<65536 else bytes([0x81,0xff])+struct.pack('!Q',length)
        self.sock.sendall(head+mask+bytes(v^mask[i%4] for i,v in enumerate(data)))
        accumulated=b''
        while True:
            a,b=self.read(2);n=b&127
            if n==126:n=struct.unpack('!H',self.read(2))[0]
            elif n==127:n=struct.unpack('!Q',self.read(8))[0]
            chunk=self.read(n)
            if a&15==8:raise RuntimeError('Browser websocket closed')
            accumulated+=chunk
            if not a&128:continue
            result=json.loads(accumulated);accumulated=b''
            if result.get('id')==self.seq:
                if 'error' in result:raise RuntimeError(result['error'])
                return result.get('result',{})
    def js(self,expression):
        result=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
        if 'exceptionDetails' in result:raise RuntimeError(result['exceptionDetails'])
        return result.get('result',{}).get('value')

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    profile=ROOT/'build/planner-browser-profile';profile.mkdir(parents=True,exist_ok=True)
    browser=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
    process=subprocess.Popen([str(browser),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
        '--remote-debugging-port=0','--user-data-dir='+str(profile),'--window-size=1460,1000',f'http://127.0.0.1:{server.server_port}/'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        portfile=profile/'DevToolsActivePort'
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                port=int(portfile.read_text().splitlines()[0]);tabs=json.load(urlopen(f'http://127.0.0.1:{port}/json/list',timeout=1))
                tab=next(t for t in tabs if t['type']=='page' and str(server.server_port) in t['url']);break
            except (OSError,ValueError,StopIteration):time.sleep(.2)
        else:raise RuntimeError('Headless browser did not start')
        c=CDP(tab['webSocketDebuggerUrl'])
        c.call('Emulation.setDeviceMetricsOverride',{'width':1460,'height':1000,'deviceScaleFactor':1,'mobile':False})
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if c.js("!!window.Planner && !!MapDesk.state.data"):break
            time.sleep(.2)
        else:raise AssertionError('Planner failed to initialize')
        def screenshot(name):
            (ROOT/('build/'+name+'.png')).write_bytes(base64.b64decode(c.call('Page.captureScreenshot',{'format':'png'})['data']))
        print(c.js("({arrival:document.getElementById('stepArrival').disabled,procedures:document.getElementById('stepProcedures').disabled,input:document.getElementById('stepInput').disabled})"))
        print(c.js("""(()=>{const $=id=>document.getElementById(id),licence=$('appLicence').textContent,notices=$('thirdPartyNotices').textContent;if(!licence.includes('All rights reserved')||!licence.includes('both free and paid')||licence.includes('__HELPER_LICENCE__')||!notices.includes('Microsoft')||!notices.includes('Bootloader Exception'))throw Error('App legal documents are missing');$('legalNotices').open=true;$('appLicence').parentElement.open=true;if(!$('appLicence').getClientRects().length)throw Error('App licence reader is hidden');$('legalNotices').open=false;return {licenceAndNotices:'passed'};})()"""))
        screenshot('planner-start')
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),real=window.pywebview.api,calls=[];
 window.pywebview.api=new Proxy(real,{get:(target,name)=>name==='open_help'?async topic=>{calls.push(topic);return {message:'Opened'};}:target[name]});
 const click=async b=>{if(!b||b.matches(':disabled'))throw Error('Help unavailable');const before=calls.length;b.click();await new Promise(r=>setTimeout(r,20));if(calls.length!==before+1)throw Error('Help click did not reach API');};
 try{
  await click($('deskHelp'));if(calls.at(-1)!=='all')throw Error('Top Help is not the full guide');
  for(const [id,topic] of [['stepDeparture','airports'],['stepArrival','airports'],['stepProcedures','airports'],['stepRoute','map'],['stepReview','review'],['stepInput','manual']]){
   await click($(id).querySelector('legend button'));if(calls.at(-1)!==topic)throw Error('Wrong section page: '+id);
  }
  $('helperMode').value='auto';$('helperMode').dispatchEvent(new Event('change'));await click($('inputHelp'));if(calls.at(-1)!=='automatic')throw Error('Automatic help page wrong');
  $('helperKind').value='ipra';$('helperKind').dispatchEvent(new Event('change'));await click($('inputHelp'));if(calls.at(-1)!=='advanced')throw Error('Advanced help page wrong');
  $('helperKind').value='navigation';$('helperKind').dispatchEvent(new Event('change'));$('helperMode').value='manual';$('helperMode').dispatchEvent(new Event('change'));
  await Planner.open('departure');await click($('mapHelp'));if(calls.at(-1)!=='airports')throw Error('Departure dialog help page wrong');await Planner.cancel();
  await Planner.open('reference');await click($('mapHelp'));if(calls.at(-1)!=='data')throw Error('Reference help page wrong');await Planner.cancel();
  return {pdfHelpButtons:'passed',lockedSectionHelp:'passed',modeSpecificHelp:'passed'};
 }finally{window.pywebview.api=real;}
 })()"""))
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk,find=id=>[...m.state.points.values()].find(p=>p.ident===id&&p.kind==='AIRPORT');
 if(!$('stepArrival').disabled||!$('stepInput').disabled)throw Error('Initial gating failed');if(['sidSummary','starSummary','approachSummary'].some(id=>$(id).classList.contains('confirmed-choice')))throw Error('Unselected procedures appear confirmed');if($('deskLoad').matches(':disabled'))throw Error('Saved plans are inaccessible before planning');
 await Planner.open('departure');$('planOrigin').value=find('UGKO').id;await $('planOrigin').onchange();if($('modalConfirm').disabled)throw Error('Departure confirm stayed disabled after dropdown selection');await $('modalConfirm').onclick();
 if($('stepArrival').disabled||!$('stepProcedures').disabled)throw Error('Departure gating failed');
 await Planner.open('arrival');$('planDestination').value=find('UGSB').id;await $('planDestination').onchange();if($('modalConfirm').disabled)throw Error('Arrival confirm stayed disabled after dropdown selection');await $('modalConfirm').onclick();
 if($('stepProcedures').disabled)throw Error('Arrival gating failed');
 for(const [stage,side] of [['sid','departure'],['star','arrival']]){
  await Planner.open(stage);const centre=m.state.options[side].runway_focus;
  if(!Number.isFinite(centre?.x)||!Number.isFinite(centre?.y))throw Error('Missing runway preview centre');
  const assertCentred=()=>{if(Math.abs(m.state.x-centre.x)>.01||Math.abs(m.state.y-centre.y)>.01||m.state.mpp!==183)throw Error(stage+' preview moved away from runway or changed zoom');};
  m.state.mpp=183;
  for(const o of [...$(side+'Procedure').options].filter(o=>o.value.startsWith('proc:')).slice(0,4)){
   m.state.x+=7000;m.state.y-=3000;$(side+'Procedure').value=o.value;$(side+'Procedure').onchange();assertCentred();
  }
  $(side+'Next').click();assertCentred();$(side+'Prev').click();assertCentred();
  m.state.x+=9000;$(side+'Focus').click();assertCentred();await Planner.confirm();if(!$(stage+'Summary').classList.contains('confirmed-choice')||!$(stage==='sid'?'chooseSid':'chooseStar').classList.contains('primary')||getComputedStyle($(stage+'Summary')).color!=='rgb(157, 240, 213)')throw Error('Confirmed '+stage+' did not turn green');
 }

 if(!$('flightDesk').contains($('approachChoice')))throw Error('Approach selector is not on main screen');
 $('approachChoice').value='1';$('approachChoice').onchange();
 if(Planner.confirmed.approach||!$('stepRoute').disabled)throw Error('Unconfirmed approach unlocked route');if($('approachSummary').classList.contains('confirmed-choice')||$('chooseApproach').classList.contains('primary'))throw Error('Unconfirmed approach is green');
 await $('chooseApproach').onclick();
 if($('planningModal').open||Planner.confirmed.approach.mode!=='visual')throw Error('Inline approach confirmation failed');if(!$('approachSummary').classList.contains('confirmed-choice')||!$('chooseApproach').classList.contains('primary'))throw Error('Confirmed approach did not turn green');
 $('approachChoice').value='0';$('approachChoice').onchange();
 if(Planner.confirmed.approach||Planner.confirmed.route)throw Error('Approach change retained stale confirmations');
 await $('chooseApproach').onclick();
 if($('stepRoute').disabled)throw Error('Procedure gating failed');
 await Planner.open('route');const p=[...m.state.points.values()].find(p=>p.ident==='IBERI');m.selectPoint(p.id,true);
 if(m.state.route.points.length!==1)throw Error('Left click did not add fix');
 $('routeUndo').click();if(m.state.route.points.length)throw Error('Undo failed');$('routeRedo').click();if(m.state.route.points.length!==1)throw Error('Redo failed');
 const screen=m.screen(p),rect=$('routeMap').getBoundingClientRect();$('routeMap').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:rect.left+screen[0],clientY:rect.top+screen[1]}));if($('routeContext').hidden||!$('planningModal').contains($('routeContext')))throw Error('Context menu unavailable');[...$('routeContext').querySelectorAll('button')].find(b=>b.textContent==='Replace waypoint').click();m.selectPoint([...m.state.points.values()].find(p=>p.ident==='KTS').id);if(m.state.route.points[0].ident!=='KTS')throw Error('Replace failed');$('routeUndo').click();if(m.state.route.points[0].ident!=='IBERI')throw Error('Undo replace failed');
 await Planner.confirm();if($('stepReview').disabled)throw Error('Review gating failed');
 $('reviewAccepted').checked=true;await $('reviewAccepted').onchange();if($('stepInput').disabled)throw Error('Input gating failed');
 document.getElementById('stepReview').scrollIntoView();const before=JSON.stringify(m.state.route);await Planner.open('route');m.addPoints([[...m.state.points.values()].find(p=>p.ident==='KTS')]);await Planner.cancel();if(JSON.stringify(m.state.route)!==before)throw Error('Cancel changed confirmed route');
 const saved=m.state.route.points.map(p=>p.ident).join();await Planner.open('departure');await m.setAirport('origin',find('UGTB'));await Planner.confirm();if(m.state.route.points.map(p=>p.ident).join()!==saved)throw Error('Airport change removed enroute fixes');if(Planner.confirmed.sid)throw Error('Affected SID was not cleared');if(!Planner.confirmed.star)throw Error('Unaffected STAR cleared');if($('sidSummary').classList.contains('confirmed-choice')||$('chooseSid').classList.contains('primary')||!$('starSummary').classList.contains('confirmed-choice'))throw Error('Airport change did not reset the affected procedure colour');
 return {flight:document.getElementById('compactRoute').textContent,points:m.state.route.points.length,arrivalRetained:!!Planner.confirmed.arrival,inputLocked:$('stepInput').disabled};
 })()"""))
        c.js("(async()=>{await Planner.open('sid');await Planner.confirm();await Planner.open('route');await Planner.confirm();const e=document.getElementById('reviewAccepted');e.checked=true;await e.onchange();window.scrollTo(0,0);})()")
        c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk;window.customBefore=JSON.stringify(m.state.route);await Planner.open('route');
 const modeButton=mode=>document.querySelector('[data-route-mode="'+mode+'"]');
 const assertMode=mode=>{if(m.state.routeMode!==mode||modeButton(mode).getAttribute('aria-pressed')!=='true'||document.querySelectorAll('[data-route-mode][aria-pressed=true]').length!==1)throw Error('Route mode toggle mismatch: '+mode);};
 if($('routeSelectMode'))throw Error('Route mode dropdown remains');assertMode('fixes');
 const a=[...m.state.airways.values()].find(a=>a.legs.length>2&&a.legs.length<10&&a.legs.slice(0,-1).every(l=>l.direction!=='B'));
 m.selectAirway(a.id);if(m.state.selected?.type==='airway')throw Error('Fix mode selected an airway');
 modeButton('airways').click();assertMode('airways');m.selectAirway(a.id);await $('addAirway').onclick();
 if(!m.state.route.points.some(p=>p.via===a.name))throw Error('Airway mode did not add its fixes');
 $('routeUndo').click();if(JSON.stringify(m.state.route)!==customBefore)throw Error('Airway undo failed');
 modeButton('custom').click();assertMode('custom');modeButton('custom').click();assertMode('custom');modeButton('fixes').click();assertMode('fixes');modeButton('custom').click();assertMode('custom');
 })()""")
        rect=c.js("(()=>{const r=document.getElementById('routeMap').getBoundingClientRect();return {x:r.left+r.width*.5,y:r.top+r.height*.5}})()")
        def mouse(kind,x,y,**extra):c.call('Input.dispatchMouseEvent',dict(type=kind,x=x,y=y,**extra))
        mouse('mousePressed',rect['x'],rect['y'],button='left',buttons=1,clickCount=1)
        mouse('mouseMoved',rect['x']+30,rect['y']+15,buttons=1)
        mouse('mouseReleased',rect['x']+30,rect['y']+15,button='left',buttons=0,clickCount=1)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if c.js("MapDesk.state.route.points.some(p=>p.kind==='CUSTOM')&&!MapDesk.state.customBusy"):break
            time.sleep(.1)
        else:raise AssertionError('Custom click/drag did not create a waypoint: '+str(c.js("document.getElementById('mapStatus').textContent")))
        dragpoint=c.js("(()=>{window.customOld=structuredClone(MapDesk.state.route.points.find(p=>p.kind==='CUSTOM'));const s=MapDesk.screen(customOld),r=document.getElementById('routeMap').getBoundingClientRect();return {x:r.left+s[0],y:r.top+s[1]}})()")
        mouse('mousePressed',dragpoint['x'],dragpoint['y'],button='left',buttons=1,clickCount=1)
        mouse('mouseMoved',dragpoint['x']+50,dragpoint['y']-25,buttons=1)
        mouse('mouseReleased',dragpoint['x']+50,dragpoint['y']-25,button='left',buttons=0,clickCount=1)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if c.js("!MapDesk.state.customBusy&&MapDesk.state.route.points.find(p=>p.kind==='CUSTOM').lat!==customOld.lat"):break
            time.sleep(.1)
        else:raise AssertionError('Dragging existing custom point did not update coordinates')
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk,p=m.state.route.points.find(p=>p.kind==='CUSTOM');const moved=structuredClone(p);
 $('routeUndo').click();if(m.state.route.points.find(q=>q.id===p.id).lat!==customOld.lat)throw Error('Custom move undo failed');
 $('routeRedo').click();if(m.state.route.points.find(p=>p.kind==='CUSTOM').lat!==moved.lat)throw Error('Custom move redo failed');
 m.customDetails(moved.id);$('customIdent').value='CWTEST';await $('renameCustom').onclick();if(!m.state.route.points.some(p=>p.kind==='CUSTOM'&&p.ident==='CWTEST'))throw Error('Custom rename failed');
 const saved=JSON.parse(JSON.stringify(m.state.route));await m.restore(saved,true);const checked=await window.pywebview.api.prepare_database_route(m.state.route);
 if(checked.error||checked.custom_waypoints?.length!==1||!checked.custom_waypoints[0].position.startsWith('N'))throw Error('Saved custom point did not reach CDU handover: '+JSON.stringify(checked));
 if(!m.state.points.has('custom:CWTEST'))throw Error('Restored custom marker missing');
 return {routeModes:'passed',customMoveUndoSaveHandover:'passed',custom:checked.custom_waypoints[0]};
 })()"""))
        screenshot('route-custom-waypoints')
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk;let i=m.state.route.points.findIndex(p=>p.kind==='CUSTOM');
 Display.set({units:'imperial',coordinates:'DDM'});Planner.editConstraint(i);
 if(!$('mapStage').contains($('fixConstraintBox'))||$('fixConstraintBox').hidden)throw Error('Constraint editor is not beside the selected map fix');
 if($('fixConstraintBox').querySelector('select')||$('fixAltitude').getBoundingClientRect().top>=$('fixSpeed').getBoundingClientRect().top)throw Error('Altitude is not above speed or the dropdown remains');
 $('fixSpeed').value='M';$('fixSpeed').oninput();if(!$('applyConstraint').disabled)throw Error('Incomplete Mach entry accepted');
 $('fixSpeed').value='0.8M';$('fixSpeed').oninput();if($('fixMachMode').getAttribute('aria-pressed')!=='true'||!$('applyConstraint').disabled)throw Error('Mach without altitude was accepted');
 $('fixAltitude').value='10000';$('fixAltitude').oninput();$('fixSpeedMode').click();if(Math.abs(Number($('fixSpeed').value)-448.5)>.1)throw Error('Mach to speed conversion failed');
 $('fixMachMode').click();if(Number($('fixSpeed').value)!==.8)throw Error('Mach round trip drifted');$('fixFlightLevelMode').click();if(Number($('fixAltitude').value)!==100)throw Error('Altitude to FL conversion failed');$('fixAltitudeMode').click();if(Number($('fixAltitude').value)!==10000)throw Error('FL to altitude conversion failed');$('fixSpeedMode').click();
 const submit=()=>document.getElementById('constraintForm').dispatchEvent(new Event('submit',{cancelable:true}));
 $('fixSpeed').value='250';$('fixSpeed').oninput();$('fixSpeed').dispatchEvent(new WheelEvent('wheel',{deltaY:-100,cancelable:true}));if(Number($('fixSpeed').value)!==255)throw Error('Speed scroll failed');$('fixSpeed').dispatchEvent(new WheelEvent('wheel',{deltaY:100,cancelable:true}));
 $('fixAltitude').value='10000';$('fixAltitude').oninput();$('fixAltitude').dispatchEvent(new WheelEvent('wheel',{deltaY:-100,cancelable:true}));if(Number($('fixAltitude').value)!==10100)throw Error('Altitude scroll failed');$('fixAltitude').dispatchEvent(new WheelEvent('wheel',{deltaY:100,cancelable:true}));
 $('fixSpeed').value='250';$('fixSpeed').oninput();$('fixAltitude').value='10000';$('fixAltitude').oninput();submit();
 if(m.state.route.points[i].constraint?.speed_kt!==250||m.state.route.points[i].constraint?.altitude_ft!==10000)throw Error('Fix constraint not saved');
 const changed=structuredClone(m.state.route.points[i].constraint),id=m.state.route.points[i].id;
 $('routePoints').querySelector('[data-move="'+i+'"][data-dir="-1"]').click();i=m.state.route.points.findIndex(p=>p.id===id);
 if(JSON.stringify(m.state.route.points[i].constraint)!==JSON.stringify(changed)||Number($('constraintForm').dataset.index)!==i)throw Error('Reordering detached the constraint editor');
 $('routeUndo').click();i=m.state.route.points.findIndex(p=>p.id===id);
 $('routeUndo').click();if(m.state.route.points[i].constraint)throw Error('Constraint undo failed');$('routeRedo').click();
 Display.set({units:'metric',coordinates:'DDM'});
 if(Math.abs(Number($('fixSpeed').value)-463)>.001||Math.abs(Number($('fixAltitude').value)-3048)>.001||!$('fixAltitudeMode').textContent.includes('(m)'))throw Error('Metric constraint conversion failed');
 $('fixFlightLevelMode').click();$('fixAltitude').value='180';$('fixAltitude').oninput();submit();
 $('fixConstraintBox').querySelector('[data-spin="altitude:1"]').click();if($('fixAltitude').value!=='181')throw Error('FL step failed');$('fixConstraintBox').querySelector('[data-spin="altitude:-1"]').click();
 Display.set({units:'imperial',coordinates:'DDM'});if($('fixAltitude').value!=='180'||m.state.route.points[i].constraint.altitude_ft!==18000)throw Error('FL changed with display units');
 $('fixSpeed').value='1000';$('fixSpeed').oninput();submit();if(!$('constraintError').textContent||m.state.route.points[i].constraint.speed_kt!==250)throw Error('Invalid constraint was accepted');
 Planner.editConstraint(i);$('clearConstraint').click();if(m.state.route.points[i].constraint)throw Error('Clear constraint failed');$('routeUndo').click();
 const p=m.state.route.points[i];await m.commitCustom({x:p.x+100,y:p.y},p.id);
 if(m.state.route.points[i].constraint?.speed_kt!==250||m.state.route.points[i].constraint?.altitude_ft!==18000)throw Error('Custom movement lost constraints');
 Planner.editConstraint(i);$('fixMachMode').click();$('fixSpeed').value='M0.8';$('fixSpeed').oninput();$('fixAltitude').value='100';$('fixAltitude').oninput();submit();
 if(Object.keys(m.state.route.points[i].constraint).sort().join()!=='altitude_ft,speed_kt'||Math.abs(m.state.route.points[i].constraint.speed_kt-448.546089)>.001)throw Error('Constraint is not stored in canonical knots/feet');
 $('fixAltitude').value='200';$('fixAltitude').oninput();$('fixSpeedMode').click();if(Math.abs(Number($('fixSpeed').value)-373.1)>.1)throw Error('Changing altitude did not recalculate speed');submit();
 const machSaved=structuredClone(m.state.route);await m.restore(machSaved,true);Planner.editConstraint(i);$('fixMachMode').click();if(Math.abs(Number($('fixSpeed').value)-.8)>1e-6||Math.abs(m.state.route.points[i].constraint.speed_kt-373.084489)>.001)throw Error('Saved Mach or altitude conversion was lost');
 $('fixSpeedMode').click();$('fixSpeed').value='250';$('fixSpeed').oninput();$('fixAltitude').value='180';$('fixAltitude').oninput();submit();
 const stored=structuredClone(m.state.route);await m.restore(stored,true);
 const prepared=await window.pywebview.api.prepare_database_route(m.state.route),manual=await window.pywebview.api.prepare_manual_plan({kind:'navigation',plan:m.state.route});
 if(prepared.error||manual.error)throw Error('Constraint handover rejected');
 if(!manual.report.text.includes('18000')||!manual.report.text.includes('250'))throw Error('Manual plan omitted constraints');
 if(manual.report.sections.some(s=>s.title==='Custom')||manual.report.html.includes('CUSTOM DATA'))throw Error('Redundant Custom section remains');if(!manual.report.sections.find(s=>s.title==='Fixes').rows.some(r=>r.value==='CWTEST'&&r.position_ddm))throw Error('Removing Custom section lost waypoint coordinates');
 if(prepared.rows.some(r=>r.value==='250'||r.value==='18000'))throw Error('Constraints entered automatic field list');
 Planner.editConstraint(i);return {fixConstraints:'passed',metricAndFL:'passed',constraintUndoMoveRestore:'passed',manualPlan:'passed',sharedModeInputs:'passed',machAltitudeConversionAndSave:'passed'};
 })()"""))
        screenshot('route-speed-altitude')
        c.js("(async()=>{await Planner.cancel();if(JSON.stringify(MapDesk.state.route)!==customBefore||[...MapDesk.state.points.values()].some(p=>p.kind==='CUSTOM'))throw Error('Cancel retained custom edits');})()")
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk;window.runwayBefore=JSON.stringify(m.state.route);
 await Planner.open('arrival');await m.setAirport('destination',[...m.state.points.values()].find(p=>p.ident==='UGSB'&&p.kind==='AIRPORT'));
 const box=$('runwayDirectionBox'),button=rw=>box.querySelector('[data-runway-direction="'+rw+'"]');
 if(box.hidden||!button('13')||!button('31'))throw Error('Runway direction overlay missing');
 if(!button('13').textContent.includes('RW 12')||!button('31').textContent.includes('RW 30'))throw Error('Batumi box is not showing DCS runway labels');
 if(!button('13').textContent.includes('ILS ILU')||!button('13').textContent.includes('110.30')||!button('31').textContent.includes('ILS not listed'))throw Error('ILS status is not runway-specific');
 const first=structuredClone(m.state.runwayDirection);await button('31').onclick();
 if($('arrivalRunway').value!=='31'||$('arrivalCduRunway').value!=='31'||button('31').getAttribute('aria-pressed')!=='true')throw Error('Overlay did not select reciprocal runway');
 const second=m.state.runwayDirection,dot=(first.end.x-first.start.x)*(second.end.x-second.start.x)+(first.end.y-first.start.y)*(second.end.y-second.start.y);
 if(dot>=0)throw Error('Runway arrow did not reverse');
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const before=box.getBoundingClientRect();m.state.x+=m.state.mpp*100;m.requestDraw();
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const after=box.getBoundingClientRect();if(Math.abs(after.left-before.left+100)>2)throw Error('Runway overlay did not follow map pan');
 m.state.x-=m.state.mpp*100;m.state.mpp*=1.25;m.requestDraw();await button('13').onclick();
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const b=box.getBoundingClientRect(),map=$('routeMap').getBoundingClientRect();if(b.left<map.left||b.right>map.right||b.top<map.top||b.bottom>map.bottom)throw Error('Runway overlay lies outside map');
 return {runwayDirectionOverlay:'passed',reciprocalArrowAndIls:'passed',panAndZoom:'passed'};
 })()"""))
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            scale=c.js("document.getElementById('mapScale').textContent");counts=re.search(r'(\d+)/(\d+) chart tiles',scale or '')
            if counts and counts[1]==counts[2] and int(counts[2])>0:break
            time.sleep(.15)
        screenshot('runway-direction-overlay')
        c.js("(async()=>{await Planner.cancel();if(JSON.stringify(MapDesk.state.route)!==runwayBefore)throw Error('Runway overlay cancel changed saved route');})()")
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk,before=JSON.stringify(m.state.route);
 await Planner.open('arrival');await m.setAirport('destination',[...m.state.points.values()].find(p=>p.ident==='URSS'&&p.kind==='AIRPORT'));
 const cards=[...$('runwayDirectionBox').querySelectorAll('[data-runway-direction]')];
 if(cards.map(b=>b.dataset.runwayDirection).join()!=='06,24')throw Error('Confirmed Sochi box still includes crossed-out runway ends');
 await cards.find(b=>b.dataset.runwayDirection==='24').onclick();
 if($('arrivalRunway').value!=='24'||$('arrivalCduRunway').value!=='24')throw Error('Selecting another runway strip failed');
 for(const side of ['departure','arrival']){if(!$(side+'Runway').hidden||$(side+'Runway').getClientRects().length||document.querySelector('label[for="'+side+'Runway"]'))throw Error('Old right-side runway selector remains visible');}
 if(!cards.every(b=>b.querySelector('.direction-icon svg path')))throw Error('Solid pointer button icons missing');
 if(getComputedStyle(document.querySelector('.map-aside')).display!=='none')throw Error('Departure/arrival side panel remains visible');
 if(Math.abs($('mapStage').getBoundingClientRect().width-document.querySelector('.map-layout').getBoundingClientRect().width)>2)throw Error('Airport map did not expand into removed panel space');
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const box=$('runwayDirectionBox').getBoundingClientRect(),map=$('routeMap').getBoundingClientRect();if(box.bottom>map.bottom||box.right>map.right)throw Error('Multi-runway box overflowed map');
 window.multirunwayBefore=before;return {allAirportRunways:'passed',sideRunwaySelectorRemoved:true};
 })()"""))
        screenshot('all-runways-overlay')
        c.js("(async()=>{await Planner.cancel();if(JSON.stringify(MapDesk.state.route)!==multirunwayBefore)throw Error('Multi-runway cancel changed confirmed plan');})()")
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk,before=JSON.stringify(m.state.route);
 await Planner.open('arrival');
 for(const [code,expected] of [['UGSB',[['13','12','13'],['31','30','31']]],['URMO',[['09','09','10'],['27','27','28']]],['URKG',[['01','04','01'],['19','22','19']]],['UGKO',[['07','08','07'],['25','26','25']]],['UG24',[['14','13','14'],['32','31','32']]],['UG27',[['14','13','13'],['32','31','31']]],['URKK',[['05R','05','05'],['23L','23','23']]],['UG5X',[['07','07','07'],['25','25','25']]]]){
  await m.setAirport('destination',[...m.state.points.values()].find(p=>p.ident===code&&p.kind==='AIRPORT'));
  for(const [source,label,cdu] of expected){
   const button=$('runwayDirectionBox').querySelector('[data-runway-direction="'+source+'"]');
   if(!button||!button.querySelector('strong').textContent.endsWith(label))throw Error(code+' DCS map label mismatch');
   await button.onclick();if($('arrivalCduRunway').value!==cdu||$('arrivalRunway').selectedOptions[0].textContent!==label)throw Error(code+' ASC CDU mapping mismatch');
   if(!$('mapSelection').textContent.includes('Runway '+label))throw Error(code+' summary does not use DCS label');
  }
 }
 await Planner.cancel();if(JSON.stringify(m.state.route)!==before)throw Error('Mapped airport selection cancel changed plan');
 return {confirmedDcsLabelsAndAscTargets:'passed',missingAscRunwayTable:'passed'};
 })()"""))
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id);await Planner.open('route');Planner.editConstraint(0);$('fixSpeed').value='250';$('fixSpeed').oninput();$('fixFlightLevelMode').click();$('fixAltitude').value='100';$('fixAltitude').oninput();$('constraintForm').dispatchEvent(new Event('submit',{cancelable:true}));await Planner.confirm();$('reviewAccepted').checked=true;await $('reviewAccepted').onchange();
 if($('copyManualPlan').matches(':disabled'))throw Error('Reviewed manual plan is locked');
 if($('entryReady')||$('nextEntry')||$('previousEntry')||$('sendEntry'))throw Error('Manual field confirmation controls remain');
 const body=$('manualPlanBody');if(getComputedStyle(body).backgroundColor!=='rgb(11, 20, 30)'||!body.querySelector('h1')?.textContent.includes('CDU manual entry plan'))throw Error('Compact themed layout is missing inside the app');if(body.querySelectorAll('.manual-main-table').length!==1||body.querySelectorAll('.fixes-table').length!==1)throw Error('Fix-specific table layout missing');if(!body.textContent.includes('Origin')||!body.textContent.includes('Destination')||!body.textContent.includes('Runway'))throw Error('Manual entry locations are missing');if(body.querySelector('.manual-main-table>thead').textContent!=='PageCDU value'||!body.querySelector('.fixes-table>thead').textContent.includes('Speed (kt)Altitude (ft)')||[...body.querySelectorAll('.manual-main-table>tbody>tr:not(.manual-section):not(.fixes-container)')].some(r=>r.children.length!==3)||[...body.querySelectorAll('.fixes-table>tbody>tr')].some(r=>r.children.length!==5)||body.textContent.includes('No published approach legs or minima'))throw Error('Speed and altitude columns leaked outside the fixes');if(body.querySelectorAll('tbody tr:not(.manual-section)').length<6||!body.textContent.includes('Departure')||!body.textContent.includes('Fixes'))throw Error('Complete manual plan missing');
 if($('copyManualPlan').disabled||$('printManualPlan').disabled||$('saveManualText').disabled)throw Error('Manual export is disabled without a cockpit');
 $('manualRoute').value='2';await $('manualRoute').onchange();if(!body.textContent.includes('RTE 2')||body.textContent.includes('RTE 1'))throw Error('Manual route number did not update');
 if(!body.querySelector('.fix-speed-cell')||!body.querySelector('.fixes-table').textContent.includes('10000')||body.textContent.includes('IBERI SPD'))throw Error('Constraint values are not on their fix row');
 const descriptors=[...body.querySelectorAll('.manual-main-table>tbody>tr:not(.manual-section):not(.fixes-container),.fixes-table>tbody>tr')].map(r=>r.children[1].getBoundingClientRect().left);if(Math.max(...descriptors)-Math.min(...descriptors)>1)throw Error('Descriptor subcolumn is not aligned');
 const real=window.pywebview.api;let exported=[];let published=null;
 window.pywebview.api=new Proxy(real,{get:(target,name)=>name==='export_manual_plan'?async(request,format)=>{exported.push({request,format});return {message:'Export checked'};}:name==='send_manual_kneeboard'?async(request)=>{published=request;return {message:'Live kneeboard updated: 1 page.',pages:1};}:target[name]});
 await $('printManualPlan').onclick();await $('saveManualText').onclick();await $('sendKneeboard').onclick();window.pywebview.api=real;if(published?.kind!=='navigation'||published?.route!==2||CduHelper.busy||$('sendKneeboard').disabled)throw Error('Live kneeboard handover failed');
 if(exported.map(e=>e.format).join()!=='html,txt'||exported.some(e=>e.request.route!==2||e.request.kind!=='navigation'))throw Error('Manual export handover failed');
 $('manualChecklist').scrollIntoView();return {fullManualPlan:'passed',noStepConfirmations:'passed',manualExport:'passed',liveKneeboardHandover:'passed'};
 })()"""))
        screenshot('manual-entry-plan')
        (ROOT/'build/manual-plan-preview.html').write_text(c.js("(async()=>{const r=await window.pywebview.api.prepare_manual_plan({kind:'navigation',route:2,plan:MapDesk.state.route});if(r.error)throw Error(r.error);return r.report.html;})()"),encoding='utf-8')
        target=c.call('Target.createTarget',{'url':f'http://127.0.0.1:{server.server_port}/manual-preview'})['targetId']
        tabs=json.load(urlopen(f'http://127.0.0.1:{port}/json/list',timeout=3))
        preview=CDP(next(t for t in tabs if t['id']==target)['webSocketDebuggerUrl'])
        preview.call('Emulation.setDeviceMetricsOverride',{'width':1460,'height':1000,'deviceScaleFactor':1,'mobile':False})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if preview.js("document.readyState==='complete'&&document.querySelectorAll('tbody tr').length>5"):break
            time.sleep(.1)
        else:raise AssertionError('Standalone manual plan did not load')
        if not preview.js("!window.pywebview&&document.body.textContent.includes('RTE 2')&&document.querySelector('.tools button').textContent.includes('Save as PDF')"):raise AssertionError('Printable plan depends on app or has no print control')
        preview.call('Emulation.setEmulatedMedia',{'media':'print'})
        if preview.js("getComputedStyle(document.querySelector('.tools')).display")!='none':raise AssertionError('Print buttons appear on paper')
        (ROOT/'build/manual-plan-print-preview.png').write_bytes(base64.b64decode(preview.call('Page.captureScreenshot',{'format':'png'})['data']))
        c.call('Target.closeTarget',{'targetId':target});preview.sock.close()

        c.js("(async()=>{const $=id=>document.getElementById(id);$('manualRoute').value='1';await $('manualRoute').onchange();})()")
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk;
 window.libraryOriginalInputs=CduHelper.snapshot();window.libraryOriginalDisplay=Display.settings;
 const real=window.pywebview.api;
 window.pywebview.api=new Proxy(real,{get:(target,name)=>['save_plan','load_plan'].includes(name)?()=>{throw Error('File browser opened during library save/load');}:target[name]});
 await Planner.open('route');const first=m.state.route.points[0]||m.state.route.origin;const custom=await real.custom_waypoint(first.x+1200,first.y+1500,'LIBFIX');if(custom.error)throw Error(custom.error);m.addPoints([custom]);await Planner.confirm();
 Display.set({coordinates:'DD',units:'metric'});$('inputRoute').value='2';$('manualRoute').value='2';$('inputSpeed').value='accelerated';$('helperSeat').value='copilot';
 window.libraryExpectedRoute=structuredClone(m.state.route);window.libraryExpectedInputs=CduHelper.snapshot();
 await $('deskSave').onclick();if(!$('planLibrary').open)throw Error('In-app save dialog did not open');
 $('planLibraryName').value='Library flight test';$('planLibraryName').oninput();await $('planLibrarySave').onclick();
 const result=await real.list_flight_plans();if(result.plans.length!==1)throw Error('Flight plan was not stored');window.librarySavedId=result.plans[0].id;
 const saved=await real.load_flight_plan(librarySavedId);if(JSON.stringify(saved.plan.navigation)!==JSON.stringify(libraryExpectedRoute)||!saved.plan.navigation.points.some(p=>p.ident==='LIBFIX')||saved.plan.display.units!=='metric'||saved.plan.entry.route!=='2')throw Error('Entire flight plan was not saved');
 await $('planLibrarySave').onclick();if((await real.list_flight_plans()).plans.length!==1)throw Error('Updating a plan created a duplicate');
 $('planLibraryClose').click();window.pywebview.api=real;return {fullFlightPlanSaved:'passed',namedUpdate:'passed',noFileBrowser:'passed'};
 })()"""))
        c.call('Page.reload')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if c.js("!!window.Planner&&!!MapDesk.state.data"):break
            time.sleep(.1)
        else:raise AssertionError('Planner did not restart for library test')
        print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),m=MapDesk,real=window.pywebview.api;
 const saved=(await real.list_flight_plans()).plans[0],expected=(await real.load_flight_plan(saved.id)).plan;
 if(m.state.route.origin||$('deskLoad').matches(':disabled'))throw Error('Saved plans cannot be loaded on a fresh app screen');
 await $('deskLoad').onclick();$('planLibrarySearch').value='Library flight';$('planLibrarySearch').oninput();
 const button=$('planLibraryList').querySelector('[data-saved-plan]');if(!button)throw Error('Named saved plan is not listed');button.click();await $('planLibraryLoad').onclick();
 if($('planLibrary').open)throw Error('Saved plan did not load: '+$('planLibraryStatus').textContent);
 if(JSON.stringify(m.state.route)!==JSON.stringify(expected.navigation))throw Error('Loaded route differs from saved flight plan');
 if(Display.settings.units!=='metric'||Display.settings.coordinates!=='DD'||$('inputRoute').value!=='2'||$('manualRoute').value!=='2'||$('inputSpeed').value!=='accelerated'||$('helperSeat').value!=='copilot')throw Error('Saved display/input settings were not restored');
 if($('reviewAccepted').checked||!$('stepInput').disabled)throw Error('Loading a plan bypassed CDU review');if(['sidSummary','starSummary','approachSummary'].some(id=>!$(id).classList.contains('confirmed-choice')))throw Error('Restored valid procedures did not turn green');
 window.libraryBeforeFailure=JSON.stringify(m.state.route);await $('deskLoad').onclick();
 let rejected=false;window.pywebview.api=new Proxy(real,{get:(target,name)=>name==='prepare_database_route'?async(...args)=>{if(!rejected){rejected=true;return {error:'Test stale navigation'};}return target[name](...args);}:target[name]});
 await $('planLibraryLoad').onclick();window.pywebview.api=real;
 if(!$('planLibrary').open||JSON.stringify(m.state.route)!==libraryBeforeFailure||!$('planLibraryStatus').textContent.includes('stale navigation'))throw Error('Failed load did not preserve the current flight plan');
 $('planLibraryClose').click();Display.set({coordinates:'DDM',units:'imperial'});CduHelper.restoreInputs({waypoints:expected.waypoints,ipra:expected.ipra,entry:{}});
 $('reviewAccepted').checked=true;await $('reviewAccepted').onchange();
 await $('deskLoad').onclick();return {flightPlanSurvivesRestart:'passed',fullRestore:'passed',freshReviewRequired:'passed',failedLoadPreservesPlan:'passed'};
 })()"""))
        screenshot('saved-flight-plans')
        c.js("document.getElementById('planLibraryClose').click()")
        if '--route-only' in sys.argv:
            c.call('Browser.close');c.sock.close();return
        c.js("(async()=>{const $=id=>document.getElementById(id);await Planner.open('arrival');await MapDesk.setAirport('destination',[...MapDesk.state.points.values()].find(p=>p.ident==='URMO'&&p.kind==='AIRPORT'));for(const [source,cdu] of [['09','10'],['27','28']]){$('arrivalRunway').value=source;await $('arrivalRunway').onchange();if($('arrivalCduRunway').value!==cdu)throw Error('Beslan runway alias not shown for '+source);$('arrivalProcedure').value='atc';$('arrivalProcedure').onchange();const legacy=structuredClone(MapDesk.state.route);legacy.arrival.cdu_runway=source;await MapDesk.restore(legacy,false);if(MapDesk.state.route.arrival.cdu_runway!==cdu)throw Error('Saved runway mapping did not migrate');if($('arrivalRunway').selectedOptions[0].textContent!==source)throw Error('Runway selector shows an alternate designation');if(!$('arrivalCduRunway').hidden&&$('arrivalCduRunway').type!=='hidden')throw Error('Duplicate CDU selector remains visible');if(/ASC RW|ASC course|DCS reference|°T/.test($('mapSelection').textContent))throw Error('Conflicting runway labels remain visible');}await Planner.cancel();if($('planDestination').value!==MapDesk.state.route.destination.id)throw Error('Arrival airport dropdown did not restore on Cancel');})()")
        c.js("(async()=>{const before=JSON.stringify(MapDesk.state.route),confirmed=JSON.stringify(Planner.confirmed);await document.getElementById('refreshAirports').onclick();if(JSON.stringify(MapDesk.state.route)!==before||JSON.stringify(Planner.confirmed)!==confirmed)throw Error('Airport refresh modified the confirmed plan');})()")
        screenshot('planner-workflow')
        c.js("document.getElementById('stepInput').scrollIntoView()")
        screenshot('planner-input')
        c.js("(()=>{const $=id=>document.getElementById(id);$('helperMode').value='auto';$('helperMode').onchange();if(!$('manualChecklist').hidden||$('autoRoutePanel').hidden)throw Error('Automatic mode still exposes manual checklist');if($('autoEntry')||$('entryReady')||$('nextEntry'))throw Error('Old step-by-step controls remain');})()")
        c.js("(()=>{CduHelper.updateStatus({running:true,awaiting_confirmation:true});if(!document.getElementById('autoRoutePhase').textContent.includes('Awaiting')||!document.getElementById('abortRoute').textContent.includes('Deny'))throw Error('Procedure confirmation pause is not visible');CduHelper.updateStatus({running:false,awaiting_confirmation:false});})()")
        c.js("""(async()=>{
 const $=id=>document.getElementById(id);if($('inputRoute').value!=='1'||$('overwriteRoute').checked||$('inputSpeed').value!=='default'||$('inputSpeed').options.length!==2)throw Error('Unsafe route input defaults');
 $('inputRoute').value='2';$('overwriteRoute').checked=true;$('inputSpeed').value='accelerated';
 const real=window.pywebview.api;let captured;
 window.pywebview.api=new Proxy(real,{get:(target,name)=>name==='arm_route'?async(...args)=>{captured=args;return {message:'Simulated arm'}}:target[name]});
 await $('armRoute').onclick();
 if(captured?.[2]?.route!==2||captured?.[2]?.overwrite!==true||captured?.[2]?.speed!=='accelerated')throw Error('Route options were not passed to automatic input');
 if(!$('inputRoute').disabled||!$('overwriteRoute').disabled||!$('inputSpeed').disabled)throw Error('Route options can change while armed');
 await new Promise(r=>setTimeout(r,800));window.pywebview.api=real;
 if($('inputRoute').disabled||$('overwriteRoute').disabled||$('inputSpeed').disabled)throw Error('Route options remained locked after stopping');
 $('inputRoute').value='1';$('overwriteRoute').checked=false;$('inputSpeed').value='default';
 })()""")
        c.js("(()=>{const $=id=>document.getElementById(id);CduHelper.updateStatus({running:true,executing:true,sent:7,total:20});if($('autoRouteProgress').value!==35||$('autoRoutePercent').textContent!=='35%'||$('autoRouteCount').textContent!=='7 / 20 entries')throw Error('Automatic progress does not reflect completed entries');CduHelper.updateStatus({running:true,awaiting_confirmation:true,sent:7,total:20});if($('autoRouteProgress').value!==35)throw Error('Confirmation pause reset progress');CduHelper.updateStatus({running:false,sent:7,total:20});if($('autoRouteProgress').value!==35||$('autoRoutePhase').textContent!=='Stopped')throw Error('Stopped input lost its progress');CduHelper.updateStatus({running:false,sent:20,total:20});if($('autoRouteProgress').value!==100)throw Error('Completed route not at 100%');CduHelper.updateStatus({running:false,sent:0,total:0});})()")
        screenshot('planner-automatic')
        c.js("(()=>{const $=id=>document.getElementById(id);$('helperMode').value='manual';$('helperMode').onchange();if($('manualChecklist').hidden||!$('autoRoutePanel').hidden)throw Error('Manual mode panel failed');})()")
        c.js("Planner.open('arrival')")
        time.sleep(4)
        screenshot('planner-map')
        c.js("""(async()=>{
 const $=id=>document.getElementById(id),saved=structuredClone(MapDesk.state.route),oldConfirmed=Planner.confirmed;
 await Planner.cancel();await Planner.open('arrival');
 const alternate=[...$('arrivalRunway').options].find(o=>o.value!==oldConfirmed.arrival.runway);
 if(!alternate)throw Error('Arrival edit test needs two runway ends');
 const real=window.pywebview.api;let release;const gate=new Promise(r=>release=r);
 window.pywebview.api=new Proxy(real,{get:(target,name)=>name==='airport_procedures'?async(...args)=>{await gate;return target[name](...args)}:target[name]});
 $('arrivalRunway').value=alternate.value;const pending=$('arrivalRunway').onchange();
 if(!$('modalConfirm').disabled||!$('arrivalRunway').disabled)throw Error('Arrival can be confirmed while its runway is loading');
 let blocked=false;try{await Planner.confirm()}catch(e){blocked=true}if(!blocked)throw Error('Loading runway confirmation was accepted');
 release();await pending;window.pywebview.api=real;
 if($('modalConfirm').disabled)throw Error('Arrival runway confirm stayed disabled');
 const expected=$('arrivalCduRunway').value;await Planner.confirm();
 if(Planner.confirmed.arrival.runway!==alternate.value||Planner.confirmed.arrival.cdu_runway!==expected)throw Error('Changed arrival runway did not persist');
 if(Planner.confirmed.star||Planner.confirmed.approach||Planner.confirmed.route)throw Error('Old arrival selections survived runway change');if($('starSummary').classList.contains('confirmed-choice')||$('approachSummary').classList.contains('confirmed-choice')||$('chooseStar').classList.contains('primary')||$('chooseApproach').classList.contains('primary'))throw Error('Changed arrival runway retained green procedure confirmation');
 if(JSON.stringify(MapDesk.state.route.points)!==JSON.stringify(saved.points)||JSON.stringify(MapDesk.state.route.departure)!==JSON.stringify(saved.departure))throw Error('Arrival edit changed departure or en-route fixes');
 await Planner.open('arrival');if($('arrivalCduRunway').value!==expected)throw Error('Arrival runway reverted on reopening');await Planner.cancel();
 await Planner.open('star');if($('arrivalCduRunway').value!==expected)throw Error('Cancelled runway edit reverted the confirmed runway');await Planner.confirm();await document.getElementById('chooseApproach').onclick();
 await Planner.open('route');await Planner.confirm();
 if(MapDesk.state.route.arrival.cdu_runway!==expected)throw Error('STAR uses a different arrival runway');const checked=await real.prepare_database_route(MapDesk.state.route);if(checked.error)throw Error('Changed arrival cannot be handed to CDU: '+checked.error);
 })()""")
        print('Progressive planner browser checks passed')
        c.js("Planner.cancel()")
        for terrain in ['Syria','Nevada','PersianGulf','MarianaIslands','Kola','Sinai','SouthAtlantic','Normandy','TheChannel','Afghanistan','Iraq','GermanyCW','Caucasus']:
            result=c.js("(async()=>{window.confirm=()=>true;const e=document.getElementById('terrainSelect');e.value="+json.dumps(terrain)+";await e.onchange();if(MapDesk.state.data.theatre!==e.value)throw Error('Terrain switch failed');if(document.getElementById('stepDeparture').disabled||document.getElementById('chooseDeparture').matches(':disabled'))throw Error('Departure stayed locked after terrain switch');if(Planner.confirmed.departure||!document.getElementById('stepInput').disabled)throw Error('Terrain switch retained old plan');document.getElementById('chooseDeparture').click();if(!document.getElementById('planningModal').open)throw Error('Departure button did not open selection');await Planner.cancel();return {terrain:MapDesk.state.data.theatre,points:MapDesk.state.data.points.length,charts:MapDesk.state.data.tiles.length};})()")
            print(json.dumps(result))
            if terrain=='Kola':
                c.js("""(async()=>{const $=id=>document.getElementById(id),p=[...MapDesk.state.points.values()].find(p=>p.ident==='EFIV'&&p.kind==='AIRPORT');if(!p?.dcs_airport||p.dcs_airport.name!=='Ivalo')throw Error('Kola DCS airport name is missing');if(!$('planOrigin').textContent.includes('Ivalo'))throw Error('DCS name missing from airport selector');await Planner.open('reference');$('referenceAirport').value=p.id;await $('referenceAirport').onchange();if(!$('referenceFacts').textContent.includes('Ivalo')||!$('referenceFacts').textContent.includes('118.000'))throw Error('Kola airport reference lacks DCS frequencies');await Planner.cancel();const before=JSON.stringify(MapDesk.state.route);await $('refreshAirports').onclick();if(JSON.stringify(MapDesk.state.route)!==before)throw Error('Airport refresh changed the flight plan');})()""")

            if terrain=='Kola':
                print(c.js("""(async()=>{
 const $=id=>document.getElementById(id),p=[...MapDesk.state.points.values()].find(p=>p.ident==='ENBO'&&p.kind==='AIRPORT');
 await Planner.open('departure');await MapDesk.setAirport('origin',p);
 for(const runway of ['07','25']){
  const option=[...$('departureRunway').options].find(o=>Number(o.value)===Number(runway));if(!option)throw Error('Bodo runway missing');
  $('departureRunway').value=option.value;await $('departureRunway').onchange();
  const panel=[...$('mapSelection').querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent==='Navigation aids'),text=panel?.textContent||'';
  for(const value of ['BOO','CH 45X','BDO','117.55 MHz','110.30 MHz','108.70 MHz'])if(!text.includes(value))throw Error('Bodo summary missing '+value+' on runway '+runway);
  if((text.match(/110.30 MHz/g)||[]).length!==1||(text.match(/108.70 MHz/g)||[]).length!==1)throw Error('Duplicate Bodo ILS components');
  const box=$('runwayDirectionBox');if(!box.querySelector('[data-runway-direction=\"07\"]').textContent.includes('ILS BO')||!box.querySelector('[data-runway-direction=\"25\"]').textContent.includes('ILS BD'))throw Error('Bodo direction ILS mismatch');
 }
 const text=$('mapSelection').textContent;await Planner.confirm();
 await Planner.open('arrival');await MapDesk.setAirport('destination',p);await Planner.confirm();await Planner.open('approach');if($('planningModal').open||!$('flightDesk').contains($('approachChoice')))throw Error('Approach selection still opens a map');
 for(const value of ['BOO','BDO','110.30 MHz','108.70 MHz'])if(!$('approachChoice').textContent.includes(value))throw Error('Bodo approach choice missing '+value);
 await Planner.cancel();
 const origin=[...MapDesk.state.points.values()].find(p=>p.ident==='EFIV'&&p.kind==='AIRPORT');
 for(const [runway,ident,frequency] of [['07','BO','110.30'],['25','BD','108.70']]){
  const plan={...MapDesk.state.route,workflow:2,origin,destination:p,points:[],connection:'direct',departure:{mode:'atc',runway:'04'},arrival:{mode:'atc',runway}};
  const checked=await window.pywebview.api.prepare_database_route(plan);if(checked.error)throw Error(checked.error);
  const aids=checked.arrival_radios;
  if(aids.ils?.ident!==ident||aids.ils?.frequency!==frequency||aids.tacan?.channel!=='45X')throw Error('Bodo radio handover mismatch');
  if(!checked.rows.some(r=>r.label==='Arrival ILS / NAV DATA'&&r.value===ident))throw Error('ILS identifier missing from NAV DATA handover');
 }
 return {bodoNavaids:'passed',bodoRadioHandover:'passed',summary:text};
 })()"""))
            if terrain=='Kola':
                print(c.js("""(async()=>{const $=id=>document.getElementById(id);await Planner.open('departure');await MapDesk.setAirport('origin',[...MapDesk.state.points.values()].find(p=>p.ident==='EFIV'&&p.kind==='AIRPORT'));const ids=[...$('runwayDirectionBox').querySelectorAll('[data-runway-direction]')].map(b=>b.dataset.runwayDirection);if(ids.join()!=='04,08,22,26')throw Error('Non-Caucasus multi-runway choices changed');await $('runwayDirectionBox').querySelector('[data-runway-direction="08"]').onclick();if($('departureCduRunway').value!=='08')throw Error('Ivalo runway selection failed');await Planner.cancel();return {kolaMultiRunway:'passed'};})()"""))
            if terrain=='Kola':
                c.js("(async()=>{await Planner.open('reference');document.getElementById('referenceAirport').value=[...MapDesk.state.points.values()].find(p=>p.ident==='EFIV'&&p.kind==='AIRPORT').id;await document.getElementById('referenceAirport').onchange();})()")
                screenshot('kola-airport-reference')
                c.js("Planner.cancel()")
            if terrain=='Kola':
                c.js("(async()=>{if(![32,128,512].every(scale=>MapDesk.state.data.tiles.some(t=>t.scale===scale)))throw Error('Kola overview levels missing');if(!MapDesk.state.data.dcs_navaids?.some(n=>n.id.startsWith('world_')))throw Error('Standalone DCS navaids missing');await Planner.open('departure');MapDesk.state.x=130000;MapDesk.state.y=110000;MapDesk.state.mpp=2500;MapDesk.requestDraw();})()")
                for name,expected,zoom in [('kola-overview',512,2500),('kola-medium',128,100),('kola-detail',32,20)]:
                    c.js('(async()=>{MapDesk.state.mpp='+str(zoom)+';MapDesk.requestDraw();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));})()')
                    deadline=time.monotonic()+100
                    while time.monotonic()<deadline:
                        scale=c.js("document.getElementById('mapScale').textContent")
                        counts=re.search(r'(\d+)/(\d+) chart tiles',scale or '')
                        if counts and counts[1]==counts[2] and int(counts[2])>0 and c.js('MapDesk.state.chartScale')==expected:break
                        time.sleep(.4)
                    else:raise AssertionError('Kola LOD did not finish: '+str(scale))
                    screenshot(name)
                c.js("Planner.cancel()")
            if terrain in ('Syria','MarianaIslands','Sinai'):
                c.js("Planner.open('departure')")
                deadline=time.monotonic()+35
                while time.monotonic()<deadline:
                    scale=c.js("document.getElementById('mapScale').textContent")
                    counts=re.search(r'(\d+)/(\d+) chart tiles',scale or '')
                    if counts and counts[1]==counts[2]:break
                    time.sleep(.3)
                if terrain!='Sinai' and (not counts or counts[1]!=counts[2]):raise AssertionError('Terrain chart tiles did not finish: '+str(scale))
                if c.js("document.getElementById('departureRunway').options.length")!=0:raise AssertionError('Stale runway choices after terrain switch')
                screenshot('terrain-'+terrain)
                c.js("Planner.cancel()")
        print('All 13 terrain selections passed')
        c.call('Browser.close');c.sock.close()
    finally:
        server.shutdown()
        library_temp.cleanup()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate()

if __name__=='__main__':main()
