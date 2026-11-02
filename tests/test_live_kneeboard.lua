local values,elements = {},{}
local corrupt
function get_param_handle(name)
    return {get=function()return values[name] or 0 end,set=function(_,value)
        values[name]=(name==corrupt and value=='TRUNCATE') and 'TRUNC' or value
    end}
end
local prefix='C130J_HELPER_KB_'
local module=dofile('assets/C130J_KneeboardBridge.lua')
local now=0
local function send(body,busy)return module.handle(body,now,busy or false)end
local function hex(value)return (value:gsub('.',function(c)return string.format('%02x',c:byte())end))end
local tx=string.rep('a',32)
assert(send('KB_STATUS')=='OK KB_STATUS 1 0 0 20 -')
assert(send('KB_BEGIN|'..tx..'|1|'..hex('First')):find('ERROR'))
-- Load the actual page script with mocked DCS drawing primitives.
local originalDofile=dofile
function dofile(path)
    if path:find('KNEEBOARD/indicator/definitions.lua',1,true) then return end
    if path=='mock-profile/Scripts/C130J_KneeboardBridge.lua' then return originalDofile('assets/C130J_KneeboardBridge.lua') end
    return originalDofile(path)
end
LockOn_Options={common_script_path='mock-common/'}
FOV=1;DEFAULT_LEVEL=16;h_clip_relations={COMPARE=1}
function SetScale()end
function GetAspect()return 1.5 end
function CreateElement()return {}end
function MakeMaterial()return 'material'end
function MakeFont()return 'font'end
function Add(element)elements[element.name]=element end
C130J_HELPER_KB_PAGE=1;dofile('assets/C130J_KneeboardPage.lua')
assert(values[prefix..'READY']==1)
assert(elements[prefix..'ROW_VALUE_1_01'].controllers[1][1]=='text_using_parameter')
assert(elements[prefix..'SECTION_1_01'].controllers[1][1]=='parameter_in_range')
assert(elements[prefix..'COLUMN_1_1_01'].controllers[1][4]==2.5)
assert(send('KB_STATUS')=='OK KB_STATUS 1 1 0 20 -')
assert(send('KB_BEGIN|'..tx..'|1|'..hex('First'))=='OK KB_BEGIN '..tx)
assert(send('KB_DATA|'..tx..'|1|PAGE|'..hex('RTE 1')):find('OK'))
assert(send('KB_COMMIT|'..tx):find('incomplete'))
assert(values[prefix..'TITLE']=='NO PLAN SENT')
local function publish(id,title,value,count)
    assert(send('KB_BEGIN|'..id..'|'..(count or 1)..'|'..hex(title)):find('OK'))
    for page=1,(count or 1) do
        for _,item in ipairs({{'PAGE','RTE 1'},{'FIELD','Origin'},{'VALUE',value}}) do
            assert(send('KB_DATA|'..id..'|'..page..'|'..item[1]..'|'..hex(item[2])):find('OK'))
        end
    end
    return send('KB_COMMIT|'..id)
end
assert(publish(tx,'First','UGKO',2)=='OK KB_COMMITTED '..tx..' 2')
assert(values[prefix..'VALUE_02']=='UGKO')
local nextTx=string.rep('b',32)
assert(publish(nextTx,'Changed while cockpit remains loaded','UGSB')=='OK KB_COMMITTED '..nextTx..' 1')
assert(values[prefix..'VALUE_01']=='UGSB' and values[prefix..'VALUE_02']=='')
assert(values[prefix..'FOOTER_01']=='PAGE 1 / 1')
assert(values[prefix..'FOOTER_02']:find('END OF PLAN'))
-- Explicit row metadata preserves wrapped cells and gives headings full-width bands.
assert(send('KB_BEGIN|'..tx..'|1|'..hex('Table')):find('OK'))
for _,item in ipairs({{'PAGE','DEPARTURE\nDEP/ARR DEP\n'}, {'FIELD','\nSID\n'},
                     {'VALUE','\nTABA2A\ncontinued'}, {'LAYOUT','SRC'}}) do
    assert(send('KB_DATA|'..tx..'|1|'..item[1]..'|'..hex(item[2])):find('OK'))
end
assert(send('KB_COMMIT|'..tx):find('OK KB_COMMITTED'))
assert(values[prefix..'ROW_KIND_01_01']==3)
assert(values[prefix..'ROW_KIND_01_02']==1 and values[prefix..'ROW_KIND_01_03']==2)
assert(values[prefix..'ROW_RULE_01_02']==0 and values[prefix..'ROW_RULE_01_03']==1)
assert(values[prefix..'ROW_VALUE_01_03']=='continued')
assert(values[prefix..'ROW_KIND_01_04']==0 and values[prefix..'ROW_VALUE_02_01']=='')
assert(publish(nextTx,'Changed while cockpit remains loaded','UGSB'):find('OK KB_COMMITTED'))
-- A lazily loaded page cannot reset a published plan.
C130J_HELPER_KB_PAGE=2;dofile('assets/C130J_KneeboardPage.lua')
assert(values[prefix..'TITLE']=='Changed while cockpit remains loaded')
corrupt=prefix..'VALUE_01'
assert(publish(tx,'Unverified update','TRUNCATE'):find('not verified'))
assert(values[prefix..'TITLE']=='Changed while cockpit remains loaded')
assert(values[prefix..'VALUE_01']=='UGSB' and values[prefix..'REVISION']==nextTx)
corrupt=nil
assert(send('KB_BEGIN|'..tx..'|21|'):find('ERROR'))
assert(send('KB_BEGIN|'..tx..'|1|'..hex('Expired')):find('OK'))
now=31
assert(send('KB_DATA|'..tx..'|1|VALUE|41'):find('no matching'))
assert(send('KB_BEGIN|'..tx..'|1|'):find('OK'))
assert(send('KB_DATA|'..tx..'|1|VALUE|00'):find('ERROR'))
assert(send('KB_DATA|'..tx..'|1|VALUE|1'):find('ERROR'))
assert(send('KB_DATA|'..tx..'|1|LAYOUT|'..hex('BAD')):find('ERROR'))
assert(send('KB_DATA|'..tx..'|1|VALUE|'..string.rep('41',1025)):find('ERROR'))
assert(send('KB_BEGIN|'..tx..'|1|',true):find('busy'))
-- Install the module into a mocked real bridge: only KB_* may exceed 160 bytes.
local queue,replies,actions={},{},{}
local udp={}
function udp:setsockname()return true end
function udp:settimeout()end
function udp:receivefrom()local body=table.remove(queue,1);if body then return body,'127.0.0.1',1234 end end
function udp:sendto(message)replies[#replies+1]=message end
function udp:close()end
package.preload.socket=function()return {udp=function()return udp end,gettime=function()return now end}end
package.preload.lfs=function()return {writedir=function()return 'mock-profile/'end}end
function LoGetSelfData()return {Name='C-130J-30'}end
function GetDevice()error('Kneeboard must not access CDU keys')end
LuaExportBeforeNextFrame=nil;LuaExportStop=nil
dofile('assets/C130J_Helper.lua')
local id=string.rep('c',32)
local function bridge(body)queue[#queue+1]=id..'|'..body;LuaExportBeforeNextFrame();return replies[#replies] end
assert(bridge('KB_STATUS'):find('OK KB_STATUS 1 1'))
assert(bridge('CAPABILITIES'):find('LIVE_KNEEBOARD'))
assert(bridge('KB_BEGIN|'..tx..'|1|'..hex('Bridge')):find('OK KB_BEGIN'))
assert(bridge('KB_DATA|'..tx..'|1|VALUE|'..hex(string.rep('A',200))):find('OK KB_DATA'))
assert(values[prefix..'VALUE_01']=='UGSB') -- still staged
local previous=#replies
bridge('KEY|pilot|'..string.rep('A',200))
assert(#replies==previous)
LoGetSelfData=function()return {Name='A-10C'}end
assert(bridge('KB_STATUS'):find('C%-130J cockpit'))
LuaExportStop()
print('PASS: live parameters, page controllers, staging, readback, rollback, bounds, stale clearing and bridge isolation')
