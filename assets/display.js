(()=>{'use strict';
let config={coordinates:'DDM',units:'imperial'};
try{const saved=JSON.parse(localStorage.getItem('c130j-display')||'null');if(saved)config={coordinates:saved.coordinates==='DD'?'DD':'DDM',units:saved.units==='metric'?'metric':'imperial'}}catch{}
function part(value,lat){const h=lat?(value<0?'S':'N'):(value<0?'W':'E');const total=Math.round(Math.abs(value)*6000),d=Math.floor(total/6000),m=(total%6000)/100;return h+String(d).padStart(lat?2:3,'0')+'° '+m.toFixed(2).padStart(5,'0')+'′'}
function ddmValue(value,lat){return part(value,lat).replace(/[°′ ]/g,'')}
function parse(text,lat){const s=String(text).trim().toUpperCase();if(/^[+-]?\d+(?:\.\d+)?$/.test(s)){const v=Number(s);if(Math.abs(v)>(lat?90:180))throw Error('Coordinate outside bounds');return v}const compact=s.replace(/[°′'\s]/g,'');const re=lat?/^([NS])(\d{2})(\d{2}(?:\.\d+)?)$/:/^([EW])(\d{3})(\d{2}(?:\.\d+)?)$/;const m=compact.match(re);if(!m||Number(m[3])>=60)throw Error('Use decimal degrees or DDM such as N4230.00 / E04143.00');const v=Number(m[2])+Number(m[3])/60;if(v>(lat?90:180))throw Error('Coordinate outside bounds');return /[SW]/.test(m[1])?-v:v}
const valid=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
function measure(value,type){if(!valid(value)||Number(value)===99999&&type==='alt')return '—';value=Number(value);const metric=config.units==='metric';let unit;
 if(type==='alt'){if(metric)value*=.3048;unit=metric?'m':'ft'}
 if(type==='metres'){if(!metric)value/=.3048;unit=metric?'m':'ft'}
 if(type==='distance'){if(metric)value*=1.852;unit=metric?'km':'NM'}
 if(type==='speed'){if(metric)value*=1.852;unit=metric?'km/h':'kt'}
 return value.toLocaleString('en-GB',{maximumFractionDigits:type==='distance'?1:0})+' '+unit;
}
function update(next){const previous={...config};config={coordinates:next.coordinates==='DD'?'DD':'DDM',units:next.units==='metric'?'metric':'imperial'};try{localStorage.setItem('c130j-display',JSON.stringify(config))}catch{}window.dispatchEvent(new CustomEvent('displaychange',{detail:{previous,current:{...config}}}));buttons()}
function buttons(){const c=document.getElementById('coordinateToggle'),u=document.getElementById('unitToggle');if(c)c.textContent='Coordinates: '+config.coordinates;if(u)u.textContent='Units: '+(config.units==='metric'?'Metric':'Imperial / aviation')}
window.Display={get settings(){return {...config}},get metric(){return config.units==='metric'},coordinates:(lat,lon)=>valid(lat)&&valid(lon)?config.coordinates==='DD'?Number(lat).toFixed(6)+'°, '+Number(lon).toFixed(6)+'°':part(Number(lat),true)+'  '+part(Number(lon),false):'Not collected',coordinate:ddmValue,parse,measure,set:update};
window.addEventListener('DOMContentLoaded',()=>{buttons();document.getElementById('coordinateToggle').onclick=()=>update({...config,coordinates:config.coordinates==='DDM'?'DD':'DDM'});document.getElementById('unitToggle').onclick=()=>update({...config,units:config.units==='metric'?'imperial':'metric'})});
})();
