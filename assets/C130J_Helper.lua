-- Local-only CNI key bridge. Installed alongside (not instead of) other exporters.
local socket = require('socket')
local lfs = require('lfs')
local liveKneeboard
do
    local ok,module = pcall(function() return dofile(lfs.writedir() .. 'Scripts/C130J_KneeboardBridge.lua') end)
    if ok and type(module) == 'table' and type(module.handle) == 'function' then liveKneeboard = module end
end
local udp = assert(socket.udp())
assert(udp:setsockname('127.0.0.1', 31330))
udp:settimeout(0)
local pending
local definitions
local armedSeat, triggerCount, lastDown, heldSince, readyForPress = nil, 0, false, nil, false
local holdSeconds = 1.5
local gestureMode,lastTap='HOLD',nil
local function cockpitTrigger()
    if not armedSeat then return end
    local ok, value = pcall(function() return GetDevice(0):get_argument_value(armedSeat == 'pilot' and 1121 or 1188) end)
    if not ok then return end
    local down = value > 0.5
    if not down then
        if lastDown and heldSince then
            local now=socket.gettime()
            local duration=now-heldSince
            if gestureMode=='HOLD' and duration>=holdSeconds then
                triggerCount=triggerCount+1; armedSeat=nil
            elseif gestureMode=='DOUBLE' and duration<0.6 then
                if lastTap and now-lastTap<=2 then
                    triggerCount=triggerCount+1; armedSeat=nil
                else lastTap=now end
            else lastTap=nil end
        end
        heldSince=nil; readyForPress=true
    elseif not lastDown and readyForPress then
        heldSince=socket.gettime()
    end
    lastDown=down
end
local function display(seat)
    for i=0,100 do
        local ok, data = pcall(list_indication, i)
        if ok and data and data:find('cni_title',1,true) then
            if seat=='pilot' then return data end
            seat='pilot'
        end
    end
    error('CDU display export unavailable')
end
local function loadDefinitions()
    local root = lfs.currentdir() .. '/Mods/aircraft/C130J/Cockpit/Scripts/'
    local env = setmetatable({}, {__index = _G})
    local commands = assert(loadfile(root .. 'command_defs.lua'))
    setfenv(commands, env)()
    local devicesFile = assert(loadfile(root .. 'devices.lua'))
    setfenv(devicesFile, env)()
    assert(env.P_CNI and env.C_CNI and env.devices)
    definitions = env
end
local function reply(id, text, ip, port)
    udp:sendto(id .. '|' .. text, ip, port)
end
local function aircraftReady()
    local own = LoGetSelfData()
    return own and (own.Name == 'C-130J' or own.Name == 'C130J' or own.Name == 'C-130J-30')
end
local oldBefore = LuaExportBeforeNextFrame
LuaExportBeforeNextFrame = function()
    if oldBefore then oldBefore() end
    if aircraftReady() then cockpitTrigger() end
    if pending and socket.gettime() >= pending.release then
        local ok = pcall(function() pending.device:performClickableAction(pending.command, 0) end)
        reply(pending.id, ok and 'OK KEY' or 'ERROR key release failed', pending.ip, pending.port)
        pending = nil
    end
    for _ = 1, 8 do
        local packet, ip, port = udp:receivefrom()
        if not packet then break end
        if ip == '127.0.0.1' and #packet <= 4096 then
            local id, body = packet:match('^(%x+)|(.+)$')
            if id and #id == 32 and (#packet <= 160 or body:sub(1,3) == 'KB_') then
                if not aircraftReady() then
                    local own = LoGetSelfData()
                    reply(id, 'ERROR C-130J cockpit required; detected aircraft: '..tostring(own and own.Name or 'none'), ip, port)
                elseif body:sub(1,3) == 'KB_' and liveKneeboard then
                    reply(id,liveKneeboard.handle(body,socket.gettime(),pending ~= nil or armedSeat ~= nil),ip,port)
                elseif body == 'PING' then
                    local ok = pcall(function() if not definitions then loadDefinitions() end end)
                    reply(id, ok and 'OK C-130J bridge connected' or 'ERROR cannot load installed C-130J controls', ip, port)
                elseif body == 'CAPABILITIES' then
                    reply(id,'OK DEL NAV_TUNE HOLD_CAPS GESTURE_MODES'..(liveKneeboard and ' LIVE_KNEEBOARD' or ''),ip,port)
                elseif body:match('^ARM|') then
                    local seat,mode=body:match('^ARM|(%a+)|(%u+)$')
                    if not seat then seat=body:match('^ARM|(%a+)$'); mode='HOLD' end
                    if (seat=='pilot' or seat=='copilot') and (mode=='HOLD' or mode=='DOUBLE') then
                        armedSeat=seat; lastDown=false; heldSince=nil; readyForPress=false
                        gestureMode=mode;lastTap=nil
                        reply(id,'OK ARMED '..triggerCount,ip,port)
                    else reply(id,'ERROR invalid seat',ip,port) end
                elseif body=='DISARM' then
                    armedSeat=nil; reply(id,'OK DISARMED',ip,port)
                elseif body=='TRIGGER' then
                    reply(id,'OK '..triggerCount,ip,port)
                elseif body:match('^READ|') then
                    local seat=body:match('^READ|(%a+)$')
                    local ok,data=pcall(display,seat)
                    reply(id,ok and ('OK DISPLAY\n'..data) or 'ERROR CDU display export unavailable',ip,port)
                elseif pending then
                    reply(id, 'ERROR bridge busy', ip, port)
                else
                    local seat, key = body:match('^KEY|(%a+)|([A-Z0-9_]+)$')
                    local allowed = key and (key:match('^KBD_[A-Z0-9]$') or key == 'KBD_DOT' or key == 'KBD_SLASH'
                        or key == 'KBD_SPACE' or key == 'KBD_PLUSMINUS' or key:match('^SELECT_[1-9]$') or key:match('^SELECT_1[0-2]$')
                        or key=='INDEX' or key=='NEXT' or key=='PREV' or key=='CLR' or key=='DEL' or key=='NAV_TUNE')
                    if allowed and (seat == 'pilot' or seat == 'copilot') then
                        local ok, err = pcall(function()
                            if not definitions then loadDefinitions() end
                            local command = (seat == 'pilot' and definitions.P_CNI or definitions.C_CNI)[key]
                            assert(type(command) == 'number')
                            local device = GetDevice(seat == 'pilot' and definitions.devices.P_CNI or definitions.devices.C_CNI)
                            device:performClickableAction(command, 1)
                            pending = {device=device, command=command, id=id, ip=ip, port=port, release=socket.gettime()+0.10}
                        end)
                        if not ok then reply(id, 'ERROR CNI key could not be pressed', ip, port) end
                    else
                        reply(id, 'ERROR unsupported request', ip, port)
                    end
                end
            end
        end
    end
end
local oldStop = LuaExportStop
LuaExportStop = function()
    if pending then pcall(function() pending.device:performClickableAction(pending.command, 0) end) end
    udp:close()
    if oldStop then oldStop() end
end
