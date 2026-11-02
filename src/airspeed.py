"""ISA pressure-altitude / subsonic calibrated-airspeed conversions.

SFTE Flight Test Engineering Reference Handbook, sections 4.1 and 4.6:
https://society-of-flight-test-engineers.github.io/quarto-handbook/04-pitot-statics.html
Altitude is pressure altitude; speed is CAS, not TAS or aircraft-corrected IAS.
"""
import math

A0_KT=math.sqrt(1.4*287.05287*288.15)/(.3048*6076.115485564304/3600)

def pressure_ratio(altitude_ft):
    if isinstance(altitude_ft,bool) or not isinstance(altitude_ft,(int,float)) or not math.isfinite(altitude_ft) or not -1500<=altitude_ft<=60000:
        raise ValueError('Enter pressure altitude before converting Mach')
    h=altitude_ft*.3048
    exponent=9.80665/(287.05287*.0065)
    if h<=11000:return (1-.0065*h/288.15)**exponent
    return (216.65/288.15)**exponent*math.exp(-9.80665*(h-11000)/(287.05287*216.65))

def mach_to_knots(mach,altitude_ft):
    if isinstance(mach,bool) or not isinstance(mach,(int,float)) or not math.isfinite(mach) or not 0<mach<1:
        raise ValueError('Mach must be greater than 0 and below 1')
    impact=pressure_ratio(altitude_ft)*((1+.2*mach*mach)**3.5-1)
    return A0_KT*math.sqrt(5*((1+impact)**(2/7)-1))

def knots_to_mach(knots,altitude_ft):
    if isinstance(knots,bool) or not isinstance(knots,(int,float)) or not math.isfinite(knots) or not 0<knots<=999:
        raise ValueError('Speed must be greater than 0 and at most 999 kt')
    impact=(1+.2*(knots/A0_KT)**2)**3.5-1
    mach=math.sqrt(5*((1+impact/pressure_ratio(altitude_ft))**(2/7)-1))
    if mach>=1:raise ValueError('Mach conversion supports subsonic values below 1')
    return mach
