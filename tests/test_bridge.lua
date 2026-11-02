local queue, replies, actions = {}, {}, {}
local now = 0
local udp = {}
function udp:setsockname() return true end
function udp:settimeout() end
function udp:receivefrom() local s=table.remove(queue,1); if s then return s,'127.0.0.1',45678 end end
function udp:sendto(s) table.insert(replies,s) end
function udp:close() end
package.preload.socket=function() return {udp=function()return udp end,gettime=function()return now end} end
package.preload.lfs=function() return {currentdir=function()return 'M:/DCS/DCS World' end} end
function LoGetSelfData()return {Name='C-130J'}end
function GetDevice(id)return {performClickableAction=function(self,key,value)table.insert(actions,{id,key,value})end}end
local before=0
function LuaExportBeforeNextFrame()before=before+1 end
dofile('assets/C130J_Helper.lua')
local id=string.rep('a',32)
table.insert(queue,id..'|PING');LuaExportBeforeNextFrame()
assert(replies[1]==id..'|OK C-130J bridge connected',replies[1])
table.insert(queue,id..'|KEY|pilot|KBD_A');LuaExportBeforeNextFrame()
assert(#actions==1 and actions[1][1]==25 and actions[1][3]==1)
now=1;LuaExportBeforeNextFrame()
assert(#actions==2 and actions[2][3]==0)
assert(replies[2]==id..'|OK KEY')
table.insert(queue,id..'|KEY|pilot|EXEC');LuaExportBeforeNextFrame()
assert(#actions==2 and replies[3]:find('unsupported'))
LoGetSelfData=function()return {Name='A-10C'}end
table.insert(queue,id..'|KEY|pilot|KBD_A');LuaExportBeforeNextFrame()
assert(#actions==2 and replies[4]:find('C%-130J cockpit'))
assert(before==5)
LoGetSelfData=function()return {Name='C-130J-30'}end
local caps=0
local originalDevice=GetDevice
GetDevice=function(n)
    if n==0 then return {get_argument_value=function(_,arg) assert(arg==1121); return caps end} end
    return originalDevice(n)
end
list_indication=function(n)
    if n==3 then return 'cni_title\nPILOT' elseif n==4 then return 'cni_title\nCOPILOT' end
end
table.insert(queue,id..'|ARM|pilot');LuaExportBeforeNextFrame()
assert(replies[#replies]:find('OK ARMED 0'))
-- Two short taps never trigger.
caps=0;LuaExportBeforeNextFrame()
now=2;caps=1;LuaExportBeforeNextFrame()
now=2.2;caps=0;LuaExportBeforeNextFrame()
now=2.5;caps=1;LuaExportBeforeNextFrame()
now=2.7;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 0')
-- A long hold triggers only after release, exactly once.
now=3;caps=1;LuaExportBeforeNextFrame()
now=4.6;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 0')
now=4.7;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 1')
-- Rearming while already held requires release and a fresh press.
now=5;caps=1;LuaExportBeforeNextFrame()
table.insert(queue,id..'|ARM|pilot');LuaExportBeforeNextFrame()
now=7;LuaExportBeforeNextFrame()
now=7.1;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 1')
now=8;caps=1;LuaExportBeforeNextFrame()
now=9.6;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 2')

-- DOUBLE mode starts/stops on two short releases, never a long hold.
table.insert(queue,id..'|ARM|pilot|DOUBLE');LuaExportBeforeNextFrame()
caps=0;LuaExportBeforeNextFrame()
now=10;caps=1;LuaExportBeforeNextFrame()
now=11.6;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 2')
now=12;caps=1;LuaExportBeforeNextFrame()
now=12.1;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 2')
now=12.4;caps=1;LuaExportBeforeNextFrame()
now=12.5;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 3')
-- Arming HOLD consumes no earlier DOUBLE gesture.
table.insert(queue,id..'|ARM|pilot|HOLD');LuaExportBeforeNextFrame()
caps=0;LuaExportBeforeNextFrame()
now=13;caps=1;LuaExportBeforeNextFrame()
now=13.1;caps=0;LuaExportBeforeNextFrame()
now=13.3;caps=1;LuaExportBeforeNextFrame()
now=13.4;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 3')
now=14;caps=1;LuaExportBeforeNextFrame()
now=15.6;caps=0;LuaExportBeforeNextFrame()
table.insert(queue,id..'|TRIGGER');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK 4')

table.insert(queue,id..'|READ|copilot');LuaExportBeforeNextFrame()
assert(replies[#replies]:find('COPILOT'))
table.insert(queue,id..'|DISARM');LuaExportBeforeNextFrame()
assert(replies[#replies]:find('OK DISARMED'))
table.insert(queue,id..'|CAPABILITIES');LuaExportBeforeNextFrame()
assert(replies[#replies]==id..'|OK DEL NAV_TUNE HOLD_CAPS GESTURE_MODES')
table.insert(queue,id..'|KEY|pilot|DEL');LuaExportBeforeNextFrame()
assert(actions[#actions][3]==1)
now=now+1;LuaExportBeforeNextFrame()
assert(actions[#actions][3]==0)
assert(replies[#replies]==id..'|OK KEY')
table.insert(queue,id..'|KEY|pilot|NAV_TUNE');LuaExportBeforeNextFrame()
assert(actions[#actions][3]==1)
now=now+1;LuaExportBeforeNextFrame()
assert(actions[#actions][3]==0)
assert(replies[#replies]==id..'|OK KEY')
LuaExportStop()
print('PASS: installed controls load, key press/release, exporter chaining, command and aircraft guards')
