"""DCS projections and geographic planning windows (not playable-area borders).

Projection references:
https://github.com/JonathanTurnock/dcs-projections
https://github.com/dharmab/skyeye/blob/main/pkg/encyclopedia/terrains/terrains.go
"""

# name: central meridian, false easting, false northing, lat/lon window, home
TERRAINS = {
    'Caucasus': (33,-99517,-4998115,(37,48,27,51),(42.5,41.8)),
    'Nevada': (-117,-193996.81,-4410028.064,(30,42,-125,-108),(36.3,-115.5)),
    'PersianGulf': (57,75756,-2894933,(19,34,44,64),(26,55.5)),
    'Syria': (39,282801,-3879866,(28,39,28,44),(34.8,36.5)),
    'Sinai': (33,169222,-3325313,(25,35,26,39),(30,33)),
    'MarianaIslands': (147,238418,-1491840,(10,23,137,151),(15,145.5)),
    'Kola': (21,-62702,-7543625,(60,75,10,43),(68,26)),
    'SouthAtlantic': (-57,147640,5815417,(-57,-44,-80,-50),(-52,-64)),
    'Normandy': (-3,-195526,-5484813,(46,53,-8,5),(49.5,0)),
    'TheChannel': (3,99376,-5636889,(48,53,-3,5),(50.7,1.5)),
    'Afghanistan': (63,-300150,-3759657,(28,40,54,76),(34,65)),
    'Iraq': (45,72290,-3680057,(27,39,37,51),(33,44)),
    'GermanyCW': (21,35427.62,-6061633.13,(47,56,4,20),(51.5,12)),
}

LABELS={'PersianGulf':'Persian Gulf','MarianaIslands':'Mariana Islands',
        'SouthAtlantic':'South Atlantic / Falklands','TheChannel':'The Channel',
        'GermanyCW':'Cold War Germany'}
NAVAID_NAMES={'SouthAtlantic':'Falklands'}
