/* ISA pressure altitude and subsonic CAS. Equations: SFTE handbook 4.1 / 4.6. */
(()=>{'use strict';
const a0=Math.sqrt(1.4*287.05287*288.15)/(.3048*6076.115485564304/3600);
function pressureRatio(ft){
 if(typeof ft!=='number'||!Number.isFinite(ft)||ft< -1500||ft>60000)throw Error('Enter altitude for Mach conversion.');
 const h=ft*.3048,e=9.80665/(287.05287*.0065);
 return h<=11000?(1-.0065*h/288.15)**e:(216.65/288.15)**e*Math.exp(-9.80665*(h-11000)/(287.05287*216.65));
}
function machToKnots(m,ft){
 if(typeof m!=='number'||!Number.isFinite(m)||m<=0||m>=1)throw Error('Use Mach greater than 0 and below 1.');
 const q=pressureRatio(ft)*((1+.2*m*m)**3.5-1);
 return a0*Math.sqrt(5*((1+q)**(2/7)-1));
}
function knotsToMach(kt,ft){
 if(typeof kt!=='number'||!Number.isFinite(kt)||kt<=0||kt>999)throw Error('Use speed from 1 to 999 kt.');
 const q=(1+.2*(kt/a0)**2)**3.5-1,m=Math.sqrt(5*((1+q/pressureRatio(ft))**(2/7)-1));
 if(m>=1)throw Error('Mach conversion supports values below 1.');
 return m;
}
window.Airspeed={machToKnots,knotsToMach,pressureRatio};
})();
