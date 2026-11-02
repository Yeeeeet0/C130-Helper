/* Progressive flight planner. Map selections remain drafts until confirmed. */
(()=>{'use strict';
const $=id=>document.getElementById(id),desk=MapDesk,db=JSON.parse($('db').textContent),modal=$('planningModal');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const copy=v=>structuredClone(v),note=t=>$('deskStatus').textContent=t;
let mode=null,snapshot=null,confirmed={departure:null,arrival:null,sid:null,star:null,approach:null,route:null},history=[],future=[],lastDraft='',restoring=false,insert=null,reviewToken='',connectionBusy=false,terrainLoading=false;
let runwayBoxKey='',runwayBoxSignature='';
const ready=()=>!!(confirmed.departure&&confirmed.arrival&&confirmed.sid&&confirmed.star&&confirmed.approach);
const act=fn=>async()=>{try{await fn()}catch(e){$('modalValidation').textContent=e.message;note(e.message)}};
function installPdfHelp(){
 const button=(topic,label,id)=>{
  const b=document.createElement('button');b.type='button';b.className='pdf-help';
  b.textContent='Help';b.dataset.helpTopic=topic;b.setAttribute('aria-label','Help: '+label);
  if(id)b.id=id;return b;
 };
 document.querySelector('.plan-library-actions').prepend(button('all','full user guide','deskHelp'));
 for(const [id,topic,label] of [['stepDeparture','airports','departure'],['stepArrival','airports','arrival'],
   ['stepProcedures','airports','procedures'],['stepRoute','map','en-route editing'],
   ['stepReview','review','review'],['stepInput','manual','CDU input']]){
  $(id).querySelector('legend').append(button(topic,label,id==='stepInput'?'inputHelp':undefined));
 }
 for(const [id,label] of [['sidSummary','SID'],['starSummary','STAR'],['approachSummary','approach']]){
  const heading=$(id).previousElementSibling;heading.classList.add('help-heading');heading.append(button('airports',label));
 }
 const terrain=document.createElement('div');terrain.className='help-heading terrain-heading';
 const label=document.querySelector('label[for=terrainSelect]');label.before(terrain);terrain.append(label,button('data','terrain and data'));
 const library=$('planLibrary').querySelector('header');library.insertBefore(button('data','saved flight plans'),$('planLibraryClose'));
 const close=$('modalClose'),actions=document.createElement('div');actions.className='help-actions';
 close.before(actions);actions.append(button('map','map selection','mapHelp'),close);
 const extra=document.querySelector('#flightDesk>details');extra.append(button('data','reference and data'));
 document.querySelector('.planner-help').append(button('troubleshooting','troubleshooting'));
 const update=()=>{
  const advanced=$('helperKind').value!=='navigation',automatic=$('helperMode').value==='auto';
  $('inputHelp').dataset.helpTopic=advanced?'advanced':automatic?'automatic':'manual';
 };
 for(const id of ['helperMode','helperKind'])$(id).addEventListener('change',update);
 update();
 document.addEventListener('click',async event=>{
  const b=event.target.closest('button[data-help-topic]');if(!b)return;
  if(b.id==='inputHelp')update();
  event.preventDefault();b.disabled=true;
  try{
   const result=await window.pywebview.api.open_help(b.dataset.helpTopic);
   if(result.error)throw Error(result.error);
  }catch(e){note(e.message);if(modal.open)$('modalValidation').textContent=e.message;}
  finally{b.disabled=false;}
 });
}
const airport=side=>desk.state.route[side==='departure'?'origin':'destination'];
const choice=side=>desk.state.route[side];
const reference=p=>{
 if(!p)return null;
 const current=desk.state.points.get(p.id),info=current?current.dcs_airport:p.dcs_airport;
 const exact=db.airfields.find(a=>a.icao_code===p.ident);
 const nearby=db.airfields.filter(a=>a.reference_lat_deg!=null&&a.reference_lon_deg!=null).map(a=>({field:a,distance:desk.distance([p,{lat:a.reference_lat_deg,lon:a.reference_lon_deg}])})).sort((a,b)=>a.distance-b.distance);
 const match=exact||(nearby[0]?.distance<3&&(nearby.length===1||nearby[1].distance>=3||nearby[0].distance<1&&nearby[1].distance-nearby[0].distance>.5)?nearby[0].field:null);
 if(match)return {...match,dcs_name:info?.name||match.dcs_name};
 return info?{airfield_id:'dcs:'+info.terrain+':'+info.dcs_airfield_id,dcs_name:info.name,airfield_elevation_m:p.elevation_ft!=null?p.elevation_ft*.3048:null,reference_lat_deg:p.lat,reference_lon_deg:p.lon}:null;
};
const dcsInfo=side=>{const p=airport(side),current=desk.state.points.get(p?.id);return current?current.dcs_airport:p?.dcs_airport;};
function radioText(info){return (info?.radios||[]).map(r=>`${esc(r.band.replace('_HI','').replace('_LOW',' low'))} ${Number(r.frequency_hz/1e6).toFixed(3)} MHz`).join(' · ');}

function runwayInfo(side){
 const a=reference(airport(side)),options=desk.state.options[side],source=$(side+'Runway').value||choice(side)?.runway,cdu=$(side+'CduRunway').value||choice(side)?.cdu_runway||source,direction=options?.runway_directions?.find(r=>r.source===source),rw=direction?.designation||options?.runway_choices?.find(r=>r.source===source)?.designation||source;
 const stripIds=db.runways.filter(r=>r.airfield_id===a?.airfield_id).map(r=>r.runway_id),end=db.runway_ends.find(e=>stripIds.includes(e.runway_id)&&e.designator===(direction?.reference_designator||cdu)),strip=db.runways.find(r=>r.runway_id===end?.runway_id);
 const native=options?.runway_details?.find(r=>r.name===source),nativeAirport=options?.airport_details,alignment=options?.runway_alignment?.find(r=>r.asc_runway===source);
 return {a:a||{airfield_elevation_m:nativeAirport?.elevation!=null?nativeAirport.elevation*.3048:null},end,strip:strip||(native?{length_m:native.length_ft>0?native.length_ft*.3048:null,surface:native.surface}:null),native,rw,cdu,source,alignment};
}
function aids(side){
 const {a,end}=runwayInfo(side),info=dcsInfo(side),imported=info?.aids||[];
 const associated=db.navaids.filter(n=>n.airfield_id===a?.airfield_id&&(!n.runway_end_id||n.runway_end_id===end?.runway_end_id));
 const kind=k=>({ILS_LOCALIZER:'ILS',LOC:'ILS',VOR_DME:'VOR/DME'}[k]||k);
 const dcs=imported.filter(n=>n.kind!=='ILS_GLIDESLOPE'||!imported.some(loc=>loc.kind==='ILS_LOCALIZER'&&loc.ident===n.ident&&loc.frequency_hz===n.frequency_hz)).map(n=>({
  navaid_id:'dcs:'+info.terrain+':'+n.id,ident:n.ident,aid_type:kind(n.kind),
  frequency_value:n.frequency_hz!=null?(n.frequency_hz/(n.kind==='NDB'?1000:1000000)).toFixed(n.kind==='NDB'?0:2):null,
  frequency_unit:n.frequency_hz!=null?(n.kind==='NDB'?'kHz':'MHz'):null,
  channel:/TACAN|VORTAC/.test(n.kind)&&n.channel!=null?String(n.channel)+(n.band||''):null,lat_deg:n.lat,lon_deg:n.lon
 }));
 const result=associated.map(n=>({...n}));
 for(const n of dcs){const existing=result.find(x=>x.ident===n.ident&&kind(x.aid_type)===n.aid_type&&(x.frequency_value==null||n.frequency_value==null||Number(x.frequency_value)===Number(n.frequency_value)));if(existing){for(const [key,value] of Object.entries(n))if(existing[key]==null)existing[key]=value;}else result.push(n);}
 for(const n of desk.state.options[side]?.nearby_navaids||[]){if(!result.some(a=>a.ident===n.point.ident&&kind(a.aid_type)===kind(n.point.kind)))result.push({navaid_id:n.point.id,ident:n.point.ident,aid_type:kind(n.point.kind),tuning_raw:n.point.asc_tuning,nearby_nm:n.distance_nm,lat_deg:n.point.lat,lon_deg:n.point.lon});}
 return result;
}
function aidText(n){return [n.aid_type,n.ident,n.frequency_value!=null?n.frequency_value+' '+(n.frequency_unit||''):'',n.channel?'CH '+n.channel:'',n.course_deg!=null?n.course_deg+'° '+(n.course_reference||''):'',n.tuning_raw?'ASC tuning '+n.tuning_raw:'',n.nearby_nm!=null?'nearby '+Display.measure(n.nearby_nm,'distance')+' (association unverified)':''].filter(Boolean).join(' · ');}
function summary(side){
 const p=airport(side);if(!p)return '<p>No airport selected</p>';
 const {a,strip,native,rw}=runwayInfo(side);
 const length=native?.length_ft!=null?native.length_ft*.3048:strip?.length_m;
 return `<strong>${esc(a?.dcs_name||p.ident)} · ${esc(p.ident)} · Runway ${esc(rw||'unknown')}</strong><p>${length!=null?esc(Display.measure(length,'metres')):'Length not available'} · Elev ${a?.airfield_elevation_m!=null?esc(Display.measure(a.airfield_elevation_m,'metres')):'not available'}${native?.surface||strip?.surface?' · '+esc(native?.surface||strip?.surface):''}</p><details><summary>Navigation aids</summary><p>${aids(side).map(a=>esc(aidText(a))).join('<br>')||'None listed'}</p></details>${dcsInfo(side)?.radios?.length?'<details><summary>Airport frequencies</summary><p>'+radioText(dcsInfo(side))+'</p></details>':''}`;
}
function procName(side){const c=choice(side),p=desk.terminalPreview(side);return p?`${p.name}${c?.runway?' · RW'+runwayInfo(side).rw:''}${p.transition?' · '+p.transition:''}`:c?.mode==='atc'?'ATC-cleared routing / vectors':c?.mode==='visual'?'Visual / VMC planning':'Not selected';}
function routeLabel(){const r=desk.state.route;return [r.origin?.ident,confirmed.sid?procName('departure'):null,...r.points.map((p,i)=>p.via&&p.via!==r.points[i-1]?.via?p.via+' → '+p.ident:p.ident),confirmed.star?procName('arrival'):null,confirmed.approach?.label,r.destination?.ident].filter(Boolean).join(' → ');}
function invalidateReview(){reviewToken='';$('reviewAccepted').checked=false;}
function render(){
 $('stepDeparture').disabled=terrainLoading||!desk.state.data;
 $('deskSave').disabled=terrainLoading||!confirmed.route;$('deskLoad').disabled=terrainLoading;
 for(const id of ['planOrigin','planDestination'])for(const option of $(id).options){const p=desk.state.points.get(option.value);if(p){const a=reference(p);option.textContent=p.ident+(a?' · '+a.dcs_name:'');}}
 $('stepArrival').disabled=!confirmed.departure;$('stepProcedures').disabled=!(confirmed.departure&&confirmed.arrival);$('stepRoute').disabled=!ready();$('stepReview').disabled=!confirmed.route;
 $('departureSummary').innerHTML=confirmed.departure?summary('departure'):'<p>Choose airport and runway.</p>';$('arrivalSummary').innerHTML=confirmed.arrival?summary('arrival'):'<p>Choose departure first.</p>';
 $('chooseDeparture').textContent=confirmed.departure?'Edit departure':'Select departure';$('chooseArrival').textContent=confirmed.arrival?'Edit arrival':'Select arrival';
 $('sidSummary').textContent=confirmed.sid?procName('departure'):'Not selected';$('starSummary').textContent=confirmed.star?procName('arrival'):'Not selected';$('approachSummary').textContent=confirmed.approach?.label||'Not selected';
 for(const [key,summaryId,buttonId] of [['sid','sidSummary','chooseSid'],['star','starSummary','chooseStar'],['approach','approachSummary','chooseApproach']]){const valid=!!confirmed[key];$(summaryId).classList.toggle('confirmed-choice',valid);$(buttonId).classList.toggle('primary',valid);}
 $('chooseSid').textContent=confirmed.sid?'Edit departure routing':'Choose departure routing';$('chooseStar').textContent=confirmed.star?'Edit arrival routing':'Choose arrival routing';$('chooseApproach').textContent=confirmed.approach?'Approach confirmed':'Confirm approach';
 $('chooseRoute').textContent=confirmed.route?'Edit route':'Choose route';$('compactRoute').textContent=routeLabel();
 $('routeOverview').textContent=confirmed.route?`${desk.state.route.points.length} en-route fixes · ${Display.measure(desk.distance(desk.routeAll()),'distance')} preview`:'Choose fixes or airways.';
 const parts=[['Departure',summary('departure'),'departure'],['Arrival',summary('arrival'),'arrival'],['SID / departure routing',esc(procName('departure')),'sid'],['STAR / arrival routing',esc(procName('arrival')),'star'],['Approach',esc(confirmed.approach?.label||'Not selected'),'approach'],['En-route',esc(desk.state.route.points.map(p=>p.ident+(constraintSummary(p)?' ['+constraintSummary(p)+']':'')).join(' → ')||'Explicit direct connection'),'route']];
 $('reviewSections').innerHTML=parts.map(([label,text,stage])=>`<div><small>${label}</small>${text}<p><button data-review-edit="${stage}">Edit ${label.toLowerCase()}</button></p></div>`).join('');$('reviewSections').querySelectorAll('[data-review-edit]').forEach(b=>b.onclick=act(()=>open(b.dataset.reviewEdit)));
 setupApproach();
 $('reviewWarnings').textContent='Verify in the CDU before EXEC.'+(desk.state.route.points.some(p=>p.constraint)?' Automatic includes speed / altitude; altitude applies forward.':'');
 $('stepInput').disabled=!confirmed.route||!$('reviewAccepted').checked||!reviewToken;if(terrainLoading)document.querySelectorAll('.flight-step').forEach(f=>f.disabled=true);
}
function airportDetails(side){const p=airport(side);if(!p)return;const {a,rw}=runwayInfo(side),opts=desk.state.options[side];const runways=opts?.runway_choices||opts?.runways.map(r=>({source:r,designation:r}))||[];$('mapSelection').innerHTML=`<div class="overline">${side} airport / runway</div><p class="map-title">${esc(a?.dcs_name||p.ident)} · ${esc(p.ident)}</p>${summary(side)}<div class="airport-detail"><p>Available runways: ${runways.map(r=>'RW'+esc(r.designation)).join(' · ')||'Loading…'}</p><p>${esc(Display.coordinates(p.lat,p.lon))}</p><p>${!opts?.runways.length&&!desk.state.runwayLoading[side]?'No ASC runway data; select the runway in the cockpit.':desk.state.runwayLoading[side]?'Loading runway procedures…':'Selected runway '+esc(rw||'unknown')+'. Confirm to save this selection.'}</p></div>`;}
function setupApproach(){
 const options=[{mode:'atc',label:'ATC vectors / approach clearance required'},{mode:'visual',label:'Visual approach planning — suitable VMC required'},...aids('arrival').filter(n=>/ILS|TACAN|VOR|NDB|LOC/.test(n.aid_type)).map(n=>({mode:'aid',navaid_id:n.navaid_id,label:aidText(n)+' · aid briefing only'}))];
 const select=$('approachChoice'),saved=desk.state.route.approach;
 select.innerHTML=options.map((o,i)=>`<option value="${i}">${esc(o.label)}</option>`).join('');
 select.value=String(Math.max(0,options.findIndex(o=>o.mode===saved?.mode&&o.navaid_id===saved?.navaid_id)));
 const details=()=>{$('approachDetails').textContent=options[Number(select.value)].mode==='aid'?'Navigation aid briefing only; select the published approach and minima using cockpit charts.':'Obtain the appropriate clearance or confirm suitable visual conditions.';};
 select.onchange=()=>{desk.state.route.approach=copy(options[Number(select.value)]);confirmed.approach=null;confirmed.route=null;invalidateReview();render();};
 $('chooseApproach').onclick=act(()=>{desk.state.route.approach=copy(options[Number(select.value)]);confirmed.approach=copy(desk.state.route.approach);confirmed.route=null;invalidateReview();render();});
 details();
}
function positionRunwayBox(){
 const box=$('runwayDirectionBox'),direction=desk.state.runwayDirection;
 if(!['departure','arrival'].includes(mode)||!direction||desk.state.runwayLoading[mode]){box.hidden=true;return;}
 const p=desk.screen(direction.centre);
 if(p[0]<0||p[1]<0||p[0]>desk.state.width||p[1]>desk.state.height){box.hidden=true;return;}
 box.hidden=false;
 $('runwayDirectionChoices').style.maxHeight=Math.max(90,Math.min(300,desk.state.height-100))+'px';
 const width=box.offsetWidth,height=box.offsetHeight;
 let left=p[0]+28;if(left+width>desk.state.width-10)left=p[0]-width-28;
 box.style.left=Math.max(10,Math.min(left,desk.state.width-width-10))+'px';
 box.style.top=Math.max(10,Math.min(p[1]+24,desk.state.height-height-34))+'px';
}
function runwayBox(side){
 const box=$('runwayDirectionBox'),opts=desk.state.options[side],source=$(side+'Runway').value;
 const selected=opts?.runway_directions?.find(r=>r.source===source),other=opts?.runway_directions?.find(r=>r.source===selected?.opposite);
 if(desk.state.runwayLoading[side]||!selected){box.hidden=true;desk.state.runwayDirection=null;runwayBoxSignature='';return;}
 const start=selected.threshold||airport(side),end=selected.threshold?other?.threshold:null;
 const centre=end?{x:(start.x+end.x)/2,y:(start.y+end.y)/2}:start;
 desk.state.runwayDirection={start,end,centre};
 const options=[...opts.runway_directions].sort((a,b)=>a.source.localeCompare(b.source));
 const key=side+':'+airport(side)?.id+':'+[selected.source,other?.source].filter(Boolean).sort().join('/');
 if(key!==runwayBoxKey){runwayBoxKey=key;desk.state.x=centre.x;desk.state.y=centre.y;desk.state.mpp=Math.min(desk.state.mpp,30);}
 const signature=JSON.stringify([key,source,options]);
 if(signature!==runwayBoxSignature){
  runwayBoxSignature=signature;
  $('runwayDirectionChoices').innerHTML=options.map(r=>{
   const opposite=opts.runway_directions.find(p=>p.source===r.opposite)?.threshold;
   const angle=opposite&&r.threshold?Math.atan2(-(opposite.y-r.threshold.y),opposite.x-r.threshold.x)*180/Math.PI:null;
   const heading=r.heading!=null?Number(r.heading).toFixed(1).padStart(5,'0')+'°':'';
   return `<button type="button" data-runway-direction="${esc(r.source)}" aria-pressed="${r.source===source}" aria-label="Runway ${esc(r.designation)}${r.ils?' · ILS '+esc(r.ils.ident):' · ILS not listed'}"><span class="direction-icon" aria-hidden="true" style="transform:rotate(${angle??0}deg)">${angle!=null?'<svg viewBox="0 0 32 32" focusable="false"><path d="M3 12H19V5L30 16 19 27V20H3Z" fill="#00d9ff" stroke="#071725" stroke-width="2" stroke-linejoin="round"/></svg>':'·'}</span><strong>RW ${esc(r.designation)}</strong><small>${esc(heading||'Heading not listed')}</small><small class="${r.ils?'ils-present':''}">${r.ils?'ILS '+esc(r.ils.ident)+' · '+esc(r.ils.frequency):'ILS not listed'}</small></button>`;
  }).join('');
  box.querySelectorAll('[data-runway-direction]').forEach(button=>button.onclick=act(async()=>{
   if(mode!==side||desk.state.runwayLoading[side]||$(side+'Runway').value===button.dataset.runwayDirection)return;
   box.querySelectorAll('button').forEach(b=>b.disabled=true);
   $(side+'Runway').value=button.dataset.runwayDirection;await $(side+'Runway').onchange();
  }));
 }
 positionRunwayBox();desk.requestDraw();
}
async function open(stage){closeConstraint();
 if(!desk.state.data)throw Error('DCS navigation data is still loading. Use Locate DCS if necessary.');
 if(stage==='approach'){if(!(confirmed.departure&&confirmed.arrival))throw Error('Confirm both runways first');$('approachEditor').scrollIntoView({behavior:'smooth',block:'center'});$('approachChoice').focus();return;}
 if(stage==='arrival'&&!confirmed.departure)throw Error('Confirm departure first');if(['sid','star','approach'].includes(stage)&&!(confirmed.departure&&confirmed.arrival))throw Error('Confirm both runways first');if(stage==='route'&&!ready())throw Error('Confirm SID, STAR and approach planning first');
 desk.state.confirmedProcedures=['departure','arrival'].map(side=>desk.terminalPreview(side)).filter(Boolean).map(copy);snapshot={route:copy(desk.state.route),ready:desk.state.terminalReady,confirmed:copy(confirmed)};mode=stage;insert=null;history=[];future=[];lastDraft=JSON.stringify(desk.state.route);modal.dataset.mode=stage;
 runwayBoxKey='';runwayBoxSignature='';desk.state.runwayDirection=null;$('runwayDirectionBox').hidden=true;
 $('modalValidation').textContent='Preview';$('modalTitle').textContent={departure:'Departure',arrival:'Arrival',sid:'SID',star:'STAR',approach:'Approach planning',route:'En-route',reference:'Airfield & runway reference'}[stage];
 $('modalCancel').textContent=stage==='reference'?'Close':'Cancel';if(stage==='reference')$('modalValidation').textContent='Read-only';
 $('modalSubtitle').textContent=stage==='reference'?'Current terrain · ASC identifiers':stage==='route'?'Click to add · Right-click to edit':stage==='sid'||stage==='star'?'Choose a procedure.':'Confirm when ready.';
 $('modalConfirm').hidden=stage==='reference';
 $('mapHelp').dataset.helpTopic=stage==='reference'?'data':stage==='route'?'map':'airports';
 $('mapSearch').disabled=false;
 const panel=$('terminalPanel');panel.open=true;const side=stage==='sid'?'departure':stage==='star'?'arrival':stage;
 if(['sid','star'].includes(stage)){$(side+'Runway').disabled=true;if(!choice(side)?.mode){const opts=desk.state.options[side],select=$(side+'Procedure');if(opts?.procedures.length){select.value='proc:'+opts.procedures[0].id;select.onchange()}else{select.value='terminal';select.onchange();const candidate=opts?.terminal_fixes.find(c=>c.associated);if(candidate)desk.addTerminalFix(side,candidate.point);else{select.value='atc';select.onchange()}}}desk.showTerminalPreview(side,true)}
 if(stage==='reference')await setupReference();
 if(stage==='route'){if(!desk.state.terminalReady)await desk.buildTerminals();desk.setRouteMode('fixes');desk.fit(desk.routeAll());}
 $('modalSettings').append($('coordinateToggle'),$('unitToggle'));modal.showModal();desk.resize();if(stage==='departure'||stage==='arrival')airportDetails(stage);syncModal();
}
function syncModal(){if(!mode)return;const side=mode==='sid'?'departure':mode==='star'?'arrival':mode;
 if(['departure','arrival'].includes(mode))runwayBox(side);else{$('runwayDirectionBox').hidden=true;desk.state.runwayDirection=null;}
 if(['departure','arrival'].includes(mode)){$(side+'Procedure').disabled=true;$(side+'Runway').disabled=desk.state.runwayLoading[side]||!desk.state.options[side]?.runways.length;airportDetails(side);}
 if(['departure','arrival'].includes(mode)){$('mapSearch').placeholder='Search a departure / arrival airport';}else $('mapSearch').placeholder='Search a waypoint, airport or airway';
 $('modalConfirm').disabled=['departure','arrival'].includes(mode)?desk.state.runwayLoading[mode]||!desk.state.options[mode]||!airport(mode)||!!desk.state.options[mode]?.runways.length&&!$(mode+'Runway').value:['sid','star'].includes(mode)?!choice(side)||(choice(side).mode==='terminal'&&!choice(side).fixes?.length):mode==='route'?desk.state.customBusy||(!desk.state.route.points.length&&desk.state.route.connection!=='direct'):false;
 $('routeUndo').disabled=!history.length;$('routeRedo').disabled=!future.length;
}
async function cancel(){if(!mode)return;restoring=true;try{confirmed=copy(snapshot.confirmed);await desk.restore(snapshot.route,snapshot.ready)}finally{restoring=false;closeConstraint();mode=null;desk.state.confirmedProcedures=[];modal.close();$('deskSettings').append($('coordinateToggle'),$('unitToggle'));$('routeContext').hidden=true;render();}}
async function confirm(){
 const r=desk.state.route,side=mode==='sid'?'departure':mode==='star'?'arrival':mode;
 if(['departure','arrival'].includes(mode)){
  if(desk.state.runwayLoading[mode]||!desk.state.options[mode]||desk.state.options[mode].runways.length&&!$(mode+'Runway').value)throw Error('Wait for the runway choices to finish loading');
  const previous=snapshot.confirmed[mode],selected={airport:airport(mode).id,runway:$(mode+'Runway').value,cdu_runway:$(mode+'CduRunway').value};confirmed[mode]=selected;
  const changed=previous&&(previous.airport!==selected.airport||previous.runway!==selected.runway||previous.cdu_runway!==selected.cdu_runway);
  if(!choice(mode)){const old=snapshot.route[mode],opts=desk.state.options[mode];if(old&&old.runway===selected.runway&&snapshot.route[mode==='departure'?'origin':'destination']?.id===selected.airport&&(!old.procedure_id||opts.procedures.some(p=>p.id===old.procedure_id))){r[mode]={...copy(old),cdu_runway:selected.cdu_runway}}else{confirmed[mode==='departure'?'sid':'star']=null;}}
  if(previous&&!changed){await desk.restore(snapshot.route,snapshot.ready);}
  if(changed){r[mode]={runway:selected.runway,cdu_runway:selected.cdu_runway};confirmed[mode==='departure'?'sid':'star']=null;confirmed.route=null;if(mode==='arrival'){confirmed.approach=null;delete r.approach;}note('Runway updated. Reconfirm the procedure.');}
  desk.state.route[mode]??={runway:selected.runway,cdu_runway:selected.cdu_runway};
 }else if(mode==='sid'||mode==='star'){confirmed[mode]=copy(choice(side));confirmed.route=null;}
 else if(mode==='approach'){confirmed.approach=copy(r.approach);confirmed.route=null;}
 else if(mode==='route'){if(!r.points.length&&r.connection!=='direct')throw Error('Choose fixes or explicitly select a direct connection');await window.pywebview.api.prepare_database_route(r).then(x=>{if(x.error)throw Error(x.error)});confirmed.route=copy(r);}
 invalidateReview();closeConstraint();mode=null;desk.state.confirmedProcedures=[];modal.close();$('deskSettings').append($('coordinateToggle'),$('unitToggle'));$('routeContext').hidden=true;render();
}
function record(){if(mode==='route'&&!restoring){const now=JSON.stringify(desk.state.route);if(now!==lastDraft){history.push(JSON.parse(lastDraft));if(history.length>100)history.shift();future=[];lastDraft=now;invalidateReview();if($('constraintForm')){const current=desk.state.route.points.indexOf(constraintTarget);if(current<0){$('mapSelection').textContent='Select a route fix to edit speed / altitude.';closeConstraint();}else if(current!==Number($('constraintForm').dataset.index))editConstraint(current);}}}if(mode)syncModal();else render();}
function restoreHistory(from,to){if(!from.length)return;const selected=$('constraintForm')?.dataset.index,target=selected!=null?desk.state.route.points[Number(selected)]:null,ordinal=target?desk.state.route.points.slice(0,Number(selected)).filter(p=>p.id===target.id).length:0;to.push(copy(desk.state.route));const route=from.pop();restoring=true;desk.replace(route);restoring=false;lastDraft=JSON.stringify(route);if(selected!=null){const matches=route.points.map((p,i)=>p.id===target?.id?i:-1).filter(i=>i>=0);if(matches[ordinal]!=null)editConstraint(matches[ordinal]);else{$('mapSelection').textContent='Select a route waypoint.';closeConstraint();}}syncModal();}
function mutate(fn){fn();desk.state.route.connection=desk.state.route.points.length?'fixes':null;desk.renderRoute();}
function constraintSummary(p){
 const c=p?.constraint;if(!c)return '';
 let kt=c.speed_kt;if(c.speed_mach!=null){try{kt=Airspeed.machToKnots(c.speed_mach,c.altitude_ft);}catch{}}
 return [kt!=null?Display.measure(kt,'speed'):'',c.altitude_ft!=null?Display.measure(c.altitude_ft,'alt'):''].filter(Boolean).join(' / ');
}
function closeConstraint(){const box=$('fixConstraintBox');if(box)box.remove();constraintUnits=null;constraintTarget=null;}
function positionConstraintBox(){
 const box=$('fixConstraintBox');if(!box)return;
 const point=constraintTarget,visible=mode==='route'&&modal.open&&point&&desk.state.route.points.includes(point);
 if(!visible){box.hidden=true;return;}const [x,y]=desk.screen(point);
 box.hidden=x<0||y<0||x>desk.state.width||y>desk.state.height;if(box.hidden)return;
 box.style.left=Math.max(8,Math.min(x+16,desk.state.width-box.offsetWidth-8))+'px';
 box.style.top=Math.max(8,Math.min(y-box.offsetHeight/2,desk.state.height-box.offsetHeight-8))+'px';
}
function editConstraint(index){
 if(mode!=='route'||!Number.isInteger(index)||!desk.state.route.points[index])return;
 const point=desk.state.route.points[index],pending=copy(point.constraint||{});constraintTarget=point;let metric=Display.metric,altMode=point.constraint_view?.altitude||pending.altitude_type||'altitude',speedMode=point.constraint_view?.speed||pending.speed_mode||'knots',speedError='',altError='';desk.state.selected={type:'point',id:point.id};
 if(speedMode==='mach'&&pending.speed_mach==null&&pending.speed_kt!=null&&pending.altitude_ft!=null){try{pending.speed_mach=Airspeed.knotsToMach(pending.speed_kt,pending.altitude_ft);}catch{}}
 let box=$('fixConstraintBox');if(!box){box=document.createElement('div');box.id='fixConstraintBox';box.className='fix-constraint-box';box.setAttribute('role','group');box.setAttribute('aria-label','Selected fix speed and altitude');$('mapStage').append(box);}
 box.innerHTML=`<div class="constraint-head"><strong>${esc(point.ident)}</strong><button id="closeConstraint" type="button" aria-label="Close speed and altitude">×</button></div><p class="constraint-hint">Scroll or type · saved as kt / ft</p><form id="constraintForm" data-index="${index}"><div class="constraint-modes" role="group" aria-label="Altitude reference" title="ISA conversion uses pressure altitude"><button type="button" id="fixAltitudeMode">Altitude (ft)</button><button type="button" id="fixFlightLevelMode">FL</button></div><div class="constraint-spin"><button type="button" data-spin="altitude:-1" aria-label="Decrease altitude">−</button><input id="fixAltitude" type="text" inputmode="decimal" aria-label="Altitude" placeholder="Optional"><button type="button" data-spin="altitude:1" aria-label="Increase altitude">+</button></div><div class="constraint-modes" role="group" aria-label="Speed reference" title="Speed is calibrated airspeed (CAS), not TAS; conversion uses ISA"><button type="button" id="fixSpeedMode">Speed (kt)</button><button type="button" id="fixMachMode">Mach</button></div><div class="constraint-spin"><button type="button" data-spin="speed:-1" aria-label="Decrease speed">−</button><input id="fixSpeed" type="text" inputmode="decimal" aria-label="Speed" placeholder="Optional"><button type="button" data-spin="speed:1" aria-label="Increase speed">+</button></div><p id="conversionHint" class="constraint-hint"></p><p id="constraintError" role="status" class="small"></p><div class="map-actions"><button id="applyConstraint" class="primary" type="submit">Apply</button><button id="clearConstraint" type="button">Clear</button></div></form>`;
 $('closeConstraint').onclick=closeConstraint;
 const speed=$('fixSpeed'),altitude=$('fixAltitude'),format=(n,d=6)=>String(Number(n.toFixed(d)));
 const hasSpeed=()=>pending.speed_kt!=null||pending.speed_mach!=null;
 const knots=()=>pending.speed_mach!=null?Airspeed.machToKnots(pending.speed_mach,pending.altitude_ft):pending.speed_kt;
 const mach=()=>pending.speed_mach!=null?pending.speed_mach:Airspeed.knotsToMach(pending.speed_kt,pending.altitude_ft);
 const modes=()=>{
  for(const [id,on] of [['fixAltitudeMode',altMode==='altitude'],['fixFlightLevelMode',altMode==='flight_level'],['fixSpeedMode',speedMode==='knots'],['fixMachMode',speedMode==='mach']])$(id).setAttribute('aria-pressed',String(on));
  $('fixAltitudeMode').textContent='Altitude ('+(metric?'m':'ft')+')';$('fixSpeedMode').textContent='Speed ('+(metric?'km/h':'kt')+')';
  altitude.setAttribute('aria-label',altMode==='flight_level'?'Flight level':'Altitude in '+(metric?'metres':'feet'));
  speed.setAttribute('aria-label',speedMode==='mach'?'Mach number':'Speed in '+(metric?'km/h':'knots'));
 };
 const problem=()=>{
  if(altError||speedError)return altError||speedError;
  if(pending.altitude_ft!=null){const a=pending.altitude_ft;if(!Number.isFinite(a)||a<(altMode==='flight_level'?0:-1500)||a>60000)return 'Altitude: -1,500–60,000 ft or FL000–FL600.';}
  if(hasSpeed()){
   if((speedMode==='mach'||pending.speed_mach!=null)&&pending.altitude_ft==null)return 'Set altitude for Mach conversion.';
   try{const kt=knots();if(!Number.isFinite(kt)||kt<1||kt>999)return 'Speed: 1–999 kt.';if(speedMode==='mach')mach();}catch(e){return e.message;}
  }
  return '';
 };
 const status=()=>{
  modes();const error=problem();$('applyConstraint').disabled=!!error;$('constraintError').textContent=altError||speedError;
  let hint='ISA · calibrated airspeed';
  if(error)hint=error;else if(hasSpeed()&&pending.altitude_ft==null)hint='Enter altitude for Mach conversion.';
  else if(hasSpeed()){try{hint=speedMode==='mach'?'≈ '+Display.measure(knots(),'speed')+' CAS · ISA':'M'+format(mach(),3)+' · ISA CAS';}catch(e){hint='ISA · Mach conversion unavailable';}}
  $('conversionHint').textContent=hint;positionConstraintBox();
 };
 const fillSpeed=()=>{try{speed.value=!hasSpeed()?'':speedMode==='mach'?format(mach(),3):format(knots()*(metric?1.852:1),1);}catch{speed.value='';}};
 const fillAltitude=()=>{altitude.value=pending.altitude_ft==null?'':format(pending.altitude_ft*(altMode==='flight_level'?.01:metric?.3048:1));};
 const fill=()=>{fillAltitude();fillSpeed();status();};
 altitude.oninput=()=>{
  let value=altitude.value.trim();altError='';
  if(/^FL/i.test(value)){altMode='flight_level';value=value.replace(/^FL\s*/i,'');}
  if(!value&&altitude.value.trim())altError='Enter a numeric altitude.';
  else if(!value){delete pending.altitude_ft;delete pending.altitude_type;}
  else if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value))altError='Enter a numeric altitude.';
  else{pending.altitude_ft=Number(value)*(altMode==='flight_level'?100:metric?1/.3048:1);pending.altitude_type=altMode;}
  if(!altError)fillSpeed();status();
 };
 speed.oninput=()=>{
  let value=speed.value.trim();speedError='';
  if(/^M|M$/i.test(value)){speedMode='mach';value=value.replace(/^M\s*|\s*M$/gi,'');}
  if(!value&&speed.value.trim())speedError='Enter a numeric Mach value.';
  else if(!value){delete pending.speed_kt;delete pending.speed_mach;}
  else if(!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value))speedError='Enter a numeric speed or Mach.';
  else if(speedMode==='mach'){const m=Number(value);if(!Number.isFinite(m)||m<=0||m>=1)speedError='Use Mach greater than 0 and below 1.';else{pending.speed_mach=m;delete pending.speed_kt;}}
  else{pending.speed_kt=Number(value)/(metric?1.852:1);delete pending.speed_mach;}
  status();
 };
 for(const [id,value] of [['fixAltitudeMode','altitude'],['fixFlightLevelMode','flight_level']])$(id).onclick=()=>{altMode=value;pending.altitude_type=value;altError='';fill();};
 for(const [id,value] of [['fixSpeedMode','knots'],['fixMachMode','mach']])$(id).onclick=()=>{if(hasSpeed()){try{if(value==='mach'){pending.speed_mach=mach();delete pending.speed_kt;}else{pending.speed_kt=knots();delete pending.speed_mach;}}catch{}}speedMode=value;speedError='';fill();};
 const adjust=(field,direction,fine=false)=>{
  if(field==='altitude'){const step=altMode==='flight_level'?100:fine?10:100;pending.altitude_ft=Math.min(60000,Math.max(altMode==='flight_level'?0:-1500,(pending.altitude_ft??0)+direction*step));pending.altitude_type=altMode;altError='';}
  else{try{if(speedMode==='mach'){pending.speed_mach=Math.min(.999,Math.max(.001,(hasSpeed()?mach():0)+direction*(fine?.001:.01)));delete pending.speed_kt;}else{pending.speed_kt=Math.min(999,Math.max(1,(hasSpeed()?knots():0)+direction*(fine?1:5)));delete pending.speed_mach;}speedError='';}catch(e){$('conversionHint').textContent=e.message;return;}}
  fill();
 };
 for(const [input,field] of [[speed,'speed'],[altitude,'altitude']])input.addEventListener('wheel',event=>{event.preventDefault();event.stopPropagation();if(event.deltaY)adjust(field,event.deltaY<0?1:-1,event.shiftKey);},{passive:false});
 box.querySelectorAll('[data-spin]').forEach(button=>button.onclick=()=>{const [field,direction]=button.dataset.spin.split(':');adjust(field,Number(direction));});
 constraintUnits=()=>{metric=Display.metric;fill();};
 $('constraintForm').onsubmit=event=>{
  event.preventDefault();const current=desk.state.route.points.indexOf(point);if(current<0)return;
  const error=problem();if(error){$('constraintError').textContent=error;positionConstraintBox();return;}
  const c={};if(hasSpeed())c.speed_kt=knots();
  if(pending.altitude_ft!=null)c.altitude_ft=pending.altitude_ft;
  mutate(()=>{if(Object.keys(c).length){point.constraint=c;point.constraint_view={speed:speedMode,altitude:altMode};}else{delete point.constraint;delete point.constraint_view;}});
  editConstraint(current);note('Speed / altitude saved for '+point.ident+'. Manual entry only.');
 };
 $('clearConstraint').onclick=()=>{const current=desk.state.route.points.indexOf(point);if(current<0)return;mutate(()=>{delete point.constraint;delete point.constraint_view;});editConstraint(current);};
 fill();desk.requestDraw();
}
let constraintUnits=null,constraintTarget=null;
function context(index,x,y){const box=$('routeContext');box.innerHTML='';for(const [label,action] of [['Speed / altitude',()=>editConstraint(index)],['Remove waypoint',()=>mutate(()=>desk.state.route.points.splice(index,1))],['Insert before',()=>setInsert(index,false)],['Insert after',()=>setInsert(index+1,false)],['Replace waypoint',()=>setInsert(index,true)],['Start reroute from here',()=>setInsert(index+1,false,true)]]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>{box.hidden=true;action()};box.append(b)}box.hidden=false;box.style.left=Math.min(x,innerWidth-230)+'px';box.style.top=Math.min(y,innerHeight-240)+'px';}
function setInsert(index,replace,reroute=false){insert={index,replace,reroute};$('routeEditHint').textContent=(replace?'Select replacement':reroute?'Select the first new fix; the downstream route will be preserved':'Select a fix to insert')+' · Escape cancels this action';}
window.Planner={get airportMode(){return ['departure','arrival'].includes(mode)},get mode(){return mode},get confirmed(){return copy(confirmed)},editConstraint,constraintSummary,closeConstraint,positionConstraintBox,airportName:p=>reference(p)?.dcs_name||'',open,cancel,confirm,positionRunwayBox,insertCustom(p){if(insert){const {index,replace,reroute}=insert;mutate(()=>desk.state.route.points.splice(index,replace?1:0,copy(p)));insert=reroute?{index:index+1,replace:false,reroute:true}:null;}else desk.addPoints([p]);},selectPoint(id,focus){
 const p=desk.state.points.get(id);if(!mode||!p)return false;
 if(['departure','arrival'].includes(mode)){if(p.kind==='AIRPORT'){const side=mode;desk.setAirport(side==='departure'?'origin':'destination',p).then(()=>{if(mode===side){airportDetails(side);syncModal()}}).catch(e=>note(e.message));if(focus)desk.fit([p]);}return true;}
 if(mode==='approach')return true;
 if(mode==='route'){
  const index=desk.state.route.points.findIndex(r=>r.id===id);
  if(p.kind==='CUSTOM'&&index>=0){desk.customDetails(id);editConstraint(index);return true;}
  if(desk.state.routeMode!=='fixes')return true;
  if(insert&&p.cdu_compatible===false){note('This ASC field identifier is not supported by the CDU. Choose a compatible fix.');return true;}if(insert){const {index:i,replace,reroute}=insert;mutate(()=>desk.state.route.points.splice(i,replace?1:0,copy(p)));insert=reroute?{index:i+1,replace:false,reroute:true}:null;$('routeEditHint').textContent='Route updated. Continue editing or confirm changes.';return true;}
  if(index>=0){const r=desk.state.route.points[index],before=desk.state.route.points[index-1]||desk.terminalPreview('departure')?.anchor||desk.state.route.origin;const airways=[...desk.state.airways.values()].filter(a=>a.legs.some(l=>l.point===id)).map(a=>a.name);$('mapSelection').innerHTML=`<div class="overline">Route waypoint ${index+1}</div><p class="map-title">${esc(p.ident)}</p><p>${esc(p.kind)} · ${esc(Display.coordinates(p.lat,p.lon))}</p><p>${esc(Display.measure(desk.distance([before,p]),'distance'))} from previous · ${esc(Display.measure(desk.distance([desk.state.route.origin,...desk.state.route.points.slice(0,index+1)]),'distance'))} cumulative</p><p>Airways: ${esc([...new Set(airways)].join(', ')||'none listed')}</p><button id="editSelectedFix">Edit waypoint</button>`;$('editSelectedFix').onclick=e=>context(index,e.clientX,e.clientY);desk.state.selected={type:'point',id};editConstraint(index);desk.requestDraw();return true;}
  if(p.kind!=='AIRPORT'&&p.cdu_compatible!==false){desk.addPoints([p]);return true;}
 }
 return false;
 }};
 // Mount the existing map, entry tools and reference into the progressive desk.
 modal.append($('routeContext'));const modalSettings=document.createElement('div');modalSettings.id='modalSettings';modalSettings.className='desk-settings';$('modalClose').before(modalSettings);$('deskSettings').append($('coordinateToggle'),$('unitToggle'));$('modalMapHost').append(document.querySelector('.map-workspace'));$('modalReferenceHost').append(document.querySelector('.reference-workspace'));$('inputHost').append(document.querySelector('.entry-workspace'));$('routePoints').parentElement.id='routePointsBox';
 const referencePanel=document.createElement('section');referencePanel.id='terrainAirportReference';referencePanel.innerHTML='<label for="referenceAirport">Airport</label><select id="referenceAirport"></select><div id="referenceFacts"></div><details><summary id="terrainNavaidsSummary">DCS navaids</summary><input id="navaidFilter" placeholder="Find aid"><div id="terrainNavaids"></div></details>';$('modalReferenceHost').append(referencePanel);
 document.querySelector('.reference-workspace').style.setProperty('display','none','important');
 let referenceRevision=0;
 async function showReference(){
  const revision=++referenceRevision,p=desk.state.points.get($('referenceAirport').value);if(!p)return;
  const result=await window.pywebview.api.airport_procedures(p.ident,'SID');if(revision!==referenceRevision)return;if(result.error)throw Error(result.error);
  const info=desk.state.points.get(p.id)?.dcs_airport,ref=reference(p),a=result.airport_details;
  const runways=(result.runway_choices||[]).map(r=>{const row=result.runway_details.find(n=>n.name===r.source);return `<tr><td>${esc(r.designation)}</td><td>${row?.length_ft!=null?esc(Display.measure(row.length_ft*.3048,'metres')):'—'}</td><td>${row?.width_ft!=null?esc(Display.measure(row.width_ft*.3048,'metres')):'—'}</td><td>${row?.hdg!=null&&String(row.hdg).trim()!==''&&Number.isFinite(Number(row.hdg))?Number(row.hdg).toFixed(1)+'°':'—'}</td><td>${esc(row?.surface||'—')}</td></tr>`}).join('');
  $('referenceFacts').innerHTML=`<h2>${esc(ref?.dcs_name||p.ident)} · ${esc(p.ident)}</h2><p>${esc(Display.coordinates(p.lat,p.lon))}${a.elevation!=null?' · '+esc(Display.measure(a.elevation*.3048,'metres')):''}</p><h3>Runways · ASC CDU</h3><table><thead><tr><th>Runway</th><th>Length</th><th>Width</th><th>ASC course</th><th>Surface</th></tr></thead><tbody>${runways||'<tr><td colspan="5">Not available</td></tr>'}</tbody></table><h3>Airport frequencies</h3><p>${radioText(info)||'Not available'}</p><h3>DCS beacons</h3><p>${(info?.aids||[]).map(n=>esc(n.kind.replaceAll('_',' '))+' · '+esc(n.ident)+(n.frequency_hz?' · '+Number(n.frequency_hz/1e6).toFixed(3)+' MHz':'')+(n.channel?' · CH '+esc(n.channel):'')+(n.tuning_issue?' · '+esc(n.tuning_issue):'')).join('<br>')||'Not available'}</p><details><summary>Sources</summary><p>Identifiers, runways and procedures: ASC CDU. ${info?'Names, frequencies and beacons: '+(info.bundled?'bundled':'local')+' DCS reference; matched by '+esc(info.match_method)+'.':'No matching DCS reference.'} Beacon listings do not establish a runway approach or CDU tuning compatibility.</p></details>`;
 }
 function showNavaids(){const all=desk.state.data.dcs_navaids||[],query=$('navaidFilter').value.toUpperCase();$('terrainNavaidsSummary').textContent='DCS navaids · '+all.length;const selected=all.filter(n=>(n.name+' '+n.ident+' '+n.kind).toUpperCase().includes(query));$('terrainNavaids').innerHTML='<table><thead><tr><th>Name</th><th>Ident</th><th>Aid</th><th>Tuning</th></tr></thead><tbody>'+selected.map(n=>'<tr><td>'+esc(n.name||n.id)+'</td><td>'+esc(n.ident||'—')+'</td><td>'+esc(n.kind.replaceAll('_',' '))+'</td><td>'+esc(n.frequency_hz?(n.frequency_hz/(n.frequency_hz<1e6?1e3:1e6)).toFixed(3)+(n.frequency_hz<1e6?' kHz':' MHz'):'')+(n.channel?' · CH '+esc(n.channel):'')+(n.tuning_issue?' · '+esc(n.tuning_issue):'')+'</td></tr>').join('')+'</tbody></table><p>Reference data; identifiers may differ from the CDU.</p>';}
 function setupReference(){const points=[...desk.state.points.values()].filter(p=>p.kind==='AIRPORT').sort((a,b)=>a.ident.localeCompare(b.ident));$('referenceAirport').innerHTML=points.map(p=>`<option value="${esc(p.id)}">${esc(p.ident)}${reference(p)?.dcs_name?' · '+esc(reference(p).dcs_name):''}</option>`).join('');$('referenceAirport').value=desk.state.route.destination?.id||desk.state.route.origin?.id||points[0]?.id||'';$('referenceAirport').onchange=act(showReference);showNavaids();$('navaidFilter').oninput=showNavaids;return showReference();}

 const oldShow=window.showWorkspace;window.showWorkspace=name=>{if(name==='map')return open('route');if(name==='reference')return open('reference');if(name==='entry'){$('stepInput').scrollIntoView({behavior:'smooth'});return;}};
 for(const [id,stage] of [['chooseDeparture','departure'],['chooseArrival','arrival'],['chooseSid','sid'],['chooseStar','star'],['chooseRoute','route'],['deskReference','reference']])$(id).onclick=act(()=>open(stage));
 $('modalClose').onclick=$('modalCancel').onclick=act(cancel);$('modalConfirm').onclick=act(confirm);modal.addEventListener('cancel',e=>{e.preventDefault();cancel()});
 $('routeUndo').onclick=()=>restoreHistory(history,future);$('routeRedo').onclick=()=>restoreHistory(future,history);
 document.querySelectorAll('[data-route-mode]').forEach(button=>button.onclick=()=>desk.setRouteMode(button.dataset.routeMode));
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('fixConstraintBox')){e.preventDefault();e.stopPropagation();closeConstraint();return;}if(e.key==='Escape'){if(insert||!$('routeContext').hidden){e.preventDefault();e.stopPropagation();}insert=null;$('routeContext').hidden=true;}if(mode==='route'&&e.ctrlKey&&e.key.toLowerCase()==='z'){e.preventDefault();restoreHistory(e.shiftKey?future:history,e.shiftKey?history:future)}});
 $('routeMap').addEventListener('contextmenu',e=>{e.preventDefault();if(mode!=='route')return;const rect=$('routeMap').getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;const index=desk.state.route.points.findIndex(p=>{const s=desk.screen(p);return Math.hypot(x-s[0],y-s[1])<15});if(index>=0)context(index,e.clientX,e.clientY)});
 window.addEventListener('routechange',record);window.addEventListener('displaychange',()=>{render();if($('constraintForm'))constraintUnits?.();if(['departure','arrival'].includes(mode))airportDetails(mode);if(mode==='reference')showReference().catch(e=>note(e.message));});
 // Runway changes are independent of confirmed procedures; preserve compatible choices.
 for(const side of ['departure','arrival']){const select=$(side+'Runway');select.onchange=act(async()=>{await desk.loadOptions(side,null,select.value);syncModal()});const sel=$(side+'Procedure'),handler=sel.onchange;sel.onchange=()=>{handler();syncModal()};}
 $('reviewAccepted').onchange=act(async()=>{if($('reviewAccepted').checked){await CduHelper.useNavigationPlan(desk.state.route);reviewToken=JSON.stringify(desk.state.route);note('Ready for CDU input.');}else reviewToken='';render()});
 const library=$('planLibrary');let storedPlans=[],selectedPlan=null,activePlan=null,libraryWorking=false;
 const libraryApi=async(name,...args)=>{const result=await window.pywebview.api[name](...args);if(result.error)throw Error(result.error);return result;};
 const libraryAction=fn=>async()=>{if(libraryWorking)return;libraryWorking=true;drawLibrary();try{await fn();}catch(error){$('planLibraryStatus').textContent=error.message;note(error.message);}finally{libraryWorking=false;drawLibrary();}};
 function flightSnapshot(){if(!confirmed.route)throw Error('Finish and confirm the complete route before saving.');return {version:1,...CduHelper.snapshot(),navigation:copy(desk.state.route),display:Display.settings};}
 function drawLibrary(){
  const filter=$('planLibrarySearch').value.toLocaleLowerCase(),selected=storedPlans.find(p=>p.id===selectedPlan),name=$('planLibraryName').value.trim();
  const visible=storedPlans.filter(p=>(p.name+' '+p.origin+' '+p.destination+' '+p.terrain).toLocaleLowerCase().includes(filter));
  $('planLibraryList').innerHTML=visible.map(p=>`<button type="button" data-saved-plan="${esc(p.id)}" aria-pressed="${p.id===selectedPlan}" ${libraryWorking?'disabled':''}>${esc(p.name)}<small>${esc(p.origin)} → ${esc(p.destination)} · ${esc(p.terrain)} · ${p.fixes} fixes · ${esc(new Date(p.updated_utc).toLocaleDateString('en-GB'))}</small></button>`).join('')||'<p>No saved plans'+(filter?' match.':' yet.')+'</p>';
  $('planLibraryList').querySelectorAll('[data-saved-plan]').forEach(button=>button.onclick=()=>{selectedPlan=button.dataset.savedPlan;$('planLibraryName').value=storedPlans.find(p=>p.id===selectedPlan).name;$('planLibraryStatus').textContent='';drawLibrary();});
  $('planLibrarySave').textContent=selected&&name.toLocaleLowerCase()===selected.name.toLocaleLowerCase()?'Update selected':'Save new plan';
  $('planLibrarySave').disabled=libraryWorking||!confirmed.route||!name;$('planLibraryLoad').disabled=libraryWorking||!selected;
  $('planLibraryName').disabled=$('planLibrarySearch').disabled=libraryWorking;$('planLibraryClose').disabled=libraryWorking;
 }
 async function openLibrary(saving=false){
  if(mode)throw Error('Confirm or cancel map editing first.');
  const result=await libraryApi('list_flight_plans');storedPlans=result.plans;selectedPlan=storedPlans.some(p=>p.id===activePlan?.id)?activePlan.id:null;
  $('planLibrarySearch').value='';$('planLibraryName').value=selectedPlan?activePlan.name:saving&&confirmed.route?(desk.state.route.origin.ident+' → '+desk.state.route.destination.ident):'';
  $('planLibraryStatus').textContent=result.unavailable?'Some saved plans could not be read.':'';drawLibrary();library.showModal();
  (saving?$('planLibraryName'):$('planLibrarySearch')).focus();
 }
 async function applyFlightPlan(plan,saved=null){
  const route=plan.navigation;if(!route||route.workflow!==2)throw Error('Choose a saved complete map flight plan.');
  const activity=await libraryApi('status');if(activity.running||activity.kneeboard_sending)throw Error('Finish CDU input or the kneeboard update before loading another flight plan.');
  const previous={route:copy(desk.state.route),confirmed:copy(confirmed),ready:desk.state.terminalReady,display:Display.settings,inputs:CduHelper.snapshot(),active:activePlan,terrain:desk.state.data.theatre};
  restoring=true;terrainLoading=true;render();
  try{
   await libraryApi('prepare_database_route',route);
   await desk.loadTerrain(route.terrain||'Caucasus');await desk.restore(route,true);Display.set(plan.display||{coordinates:'DDM',units:'imperial'});CduHelper.restoreInputs(plan);
   confirmed={departure:{airport:route.origin.id,runway:route.departure.runway,cdu_runway:desk.state.route.departure.cdu_runway},arrival:{airport:route.destination.id,runway:route.arrival.runway,cdu_runway:desk.state.route.arrival.cdu_runway},sid:copy(desk.state.route.departure),star:copy(desk.state.route.arrival),approach:copy(route.approach||{mode:'atc',label:'ATC vectors / approach clearance required'}),route:copy(desk.state.route)};
   desk.state.route.approach=copy(confirmed.approach);activePlan=saved;invalidateReview();note((saved?'Loaded '+saved.name+'.':'Plan imported.')+' Review before CDU entry.');
  }catch(error){
   try{await desk.loadTerrain(previous.terrain);await desk.restore(previous.route,previous.ready);Display.set(previous.display);CduHelper.restoreInputs(previous.inputs);confirmed=previous.confirmed;activePlan=previous.active;invalidateReview();}
   catch(recovery){note('Could not restore the previous preview: '+recovery.message);}
   throw error;
  }finally{restoring=false;terrainLoading=false;render();}
 }
 $('deskSave').onclick=$('saveHelper').onclick=act(()=>openLibrary(true));
 $('deskLoad').onclick=$('loadHelper').onclick=act(()=>openLibrary(false));
 $('planLibrarySearch').oninput=$('planLibraryName').oninput=drawLibrary;
 $('planLibraryClose').onclick=()=>library.close();library.addEventListener('cancel',event=>{if(libraryWorking)event.preventDefault();});
 $('planLibrarySave').onclick=libraryAction(async()=>{
  const name=$('planLibraryName').value.trim(),selected=storedPlans.find(p=>p.id===selectedPlan),key=selected&&selected.name.toLocaleLowerCase()===name.toLocaleLowerCase()?selected.id:null;
  const result=await libraryApi('save_flight_plan',name,flightSnapshot(),key);activePlan=result.saved;selectedPlan=result.saved.id;storedPlans=(await libraryApi('list_flight_plans')).plans;$('planLibraryName').value=result.saved.name;$('planLibraryStatus').textContent='Saved in the app.';note('Saved '+result.saved.name+'.');
 });
 $('planLibraryLoad').onclick=libraryAction(async()=>{const result=await libraryApi('load_flight_plan',selectedPlan);await applyFlightPlan(result.plan,result.saved);library.close();});
 $('deskLoadAny').onclick=act(async()=>{const result=await window.pywebview.api.load_plan();if(result.error)throw Error(result.error);if(!result.cancelled)await applyFlightPlan(result.plan);});
 $('refreshAirports').onclick=act(async()=>{const button=$('refreshAirports');button.disabled=true;note('Refreshing DCS airports…');try{const result=await window.pywebview.api.refresh_airport_reference();if(result.error)throw Error(result.error);desk.state.data.dcs_navaids=result.navaids||[];for(const row of result.airports){const p=desk.state.points.get(row.id);if(p){delete p.dcs_airport;if(row.reference)p.dcs_airport=row.reference;}}render();if(mode==='reference')await setupReference();else if(['departure','arrival'].includes(mode))airportDetails(mode);note(result.updated+' DCS airport references updated.');}finally{button.disabled=false;}});

 $('terrainSelect').after($('mapChooseDcs'));const locateDcs=$('mapChooseDcs').onclick;$('mapChooseDcs').onclick=act(async()=>{await locateDcs();if(!desk.state.route.origin){confirmed={departure:null,arrival:null,sid:null,star:null,approach:null,route:null};invalidateReview();render();}});
 function terrainCoverage(data){$('terrainSelect').innerHTML=data.terrain_catalog.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');$('terrainSelect').value=data.theatre;$('terrainCoverage').textContent=data.points.filter(p=>p.kind==='AIRPORT').length+' airports · '+data.points.length.toLocaleString()+' fixes · '+(data.tiles.length?'Local charts':'No local charts');}
 window.addEventListener('terrainloaded',e=>terrainCoverage(e.detail));if(desk.state.data)terrainCoverage(desk.state.data);
 $('terrainSelect').onchange=act(async()=>{const name=$('terrainSelect').value,old=desk.state.data?.theatre;if(confirmed.departure&&!window.confirm('Change terrain and start a new plan? Save the current plan first if you want to keep it.')){$('terrainSelect').value=old;return;}$('terrainSelect').disabled=true;terrainLoading=true;render();note('Loading '+name+' ASC navigation…');try{await desk.loadTerrain(name);confirmed={departure:null,arrival:null,sid:null,star:null,approach:null,route:null};invalidateReview();render();note('Loaded '+name+' ASC navigation. Select your departure.');}finally{terrainLoading=false;$('terrainSelect').disabled=false;render();}});
 // Connection state comes from the bridge, never from UI focus or a timer alone.
 const light=(id,value)=>{$(id).classList.toggle('good',!!value);$(id).setAttribute('aria-label',$(id).textContent.trim()+': '+(value?'ready':'inactive'))};
 async function connection(){if(connectionBusy||!window.pywebview?.api)return;connectionBusy=true;try{const s=await window.pywebview.api.status();$('terrainSelect').disabled=terrainLoading||s.running;$('mapChooseDcs').disabled=s.running;$('refreshAirports').disabled=s.running;CduHelper.updateStatus(s);light('connectedLight',s.connected);light('armedLight',s.armed);light('executingLight',s.executing);$('armRoute').disabled=$('stepInput').disabled||s.running||CduHelper.busy||!s.connected;if(!s.running&&$('helperMode').value==='auto'){const result=await window.pywebview.api.connection($('helperSeat').value);light('connectedLight',!result.error&&result.connected);$('armRoute').disabled=$('stepInput').disabled||CduHelper.busy||!!result.error||!result.connected;}}catch{light('connectedLight',false);light('armedLight',false);light('executingLight',false);$('armRoute').disabled=true;}finally{connectionBusy=false;}}
 setInterval(connection,2000);$('helperMode').addEventListener('change',connection);$('checkBridge').onclick=act(async()=>{const r=await window.pywebview.api.connection($('helperSeat').value);$('helperStatus').textContent=r.error||r.message;$('helperStatus').hidden=false;connection()});
 $('helperKind').closest('.editor').querySelector('label[for=helperKind]').textContent='Entry data';$('prepareHelper').hidden=true;$('editMapRoute').onclick=act(()=>open('route'));
 installPdfHelp();
 render();
})();
