"""User-confirmed Caucasus DCS/ASC runway pairs from the annotated airfield sheet.

Source: CaucasusAirfields (1).pdf, supplied 2026-10-29, SHA256
1c0533442b4e9fb7a70f00a0c326dba19869fc721a499f392d22a4480608887b.
source preserves ASC procedure-table keys; map is the DCS label; cdu is the
observed ASC CDU choice. Reference keys identify the same physical runway end.
"""


def pair(source,map_label,cdu,reference,true_heading):
    return dict(source=source,map=map_label,cdu=cdu,reference=reference,true_heading=true_heading)


CONFIRMED={
 'URKA':[pair('04','04','04','04',42),pair('22','22','22','22',222)],
 'UGSB':[pair('13','12','13','13',126),pair('31','30','31','31',306)],
 'URMO':[pair('09','09','10','10',94),pair('27','27','28','28',274)],
 'URKG':[pair('01','04','01','01',40),pair('19','22','19','19',220)],
 'UG23':[pair('15','15','15','15',151),pair('33','33','33','33',331)],
 'UG5X':[pair('07','07','07','07',70),pair('25','25','25','25',250)],
 'URKL':[pair('09','09','09','09',87),pair('27','27','27','27',267)],
 'URKK':[pair('05R','05','05','05',47),pair('23L','23','23','23',227)],
 'URKW':[pair('04','04','04','04',39),pair('22','22','22','22',219)],
 'UGKO':[pair('07','08','07','07',74),pair('25','26','25','25',254)],
 'URKH':[pair('04','04','04','04',39),pair('22','22','22','22',219)],
 'URMM':[pair('12','12','12','12',115),pair('30','30','30','30',295)],
 'XRMF':[pair('08','08','08','08',82),pair('26','26','26','26',262)],
 'URMN':[pair('06','06','06','06',55),pair('24','24','24','24',235)],
 'URKN':[pair('04','04','04','04',40),pair('22','22','22','22',220)],
 'UGKS':[pair('09','09','09','09',94),pair('27','27','27','27',274)],
 'URSS':[pair('06','06','06','06',61),pair('24','24','24','24',241)],
 'UGSS':[pair('12','12','12','12',116),pair('30','30','30','30',296)],
 'UGTB':[pair('13R','13R','13R','13',127),pair('31L','31L','31L','31',307)],
 # The old reference's Soganlug end labels are reversed against its courses.
 'UG24':[pair('14','13','14','32',132),pair('32','31','32','14',312)],
 'UG27':[pair('14','13','13','13',135),pair('32','31','31','31',315)],
}

AIRFIELDS=dict(zip(CONFIRMED,[
 'cau_anapa_vityazevo','cau_batumi','cau_beslan','cau_gelendzhik','cau_gudauta',
 'cau_kobuleti','cau_krasnodar_center','cau_krasnodar_pashkovsky','cau_krymsk',
 'cau_kutaisi','cau_maykop_khanskaya','cau_mineralnye_vody','cau_mozdok',
 'cau_nalchik','cau_novorossiysk','cau_senaki_kolkhi','cau_sochi_adler',
 'cau_sukhumi_babushara','cau_tbilisi_lochini','cau_soganlug','cau_vaziani']))


def confirmed_runway(airport,source):
    return next((r for r in CONFIRMED.get(airport,[]) if r['source']==source),None)


def map_runway_for(airport,source):
    row=confirmed_runway(airport,source)
    return row['map'] if row else source


def reference_runway_for(airport,source,cdu=None):
    row=confirmed_runway(airport,source)
    return row['reference'] if row else cdu or source
