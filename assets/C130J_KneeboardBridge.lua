-- Transactional text publisher; deliberately cannot issue cockpit key commands.
local M = {}
local prefix, capacity = 'C130J_HELPER_KB_', 20
local staged
local function param(name) return get_param_handle(prefix .. name) end
local function available() return type(get_param_handle) == 'function' end
local function ready()
    if not available() then return false end
    local ok,value = pcall(function() return param('READY'):get() end)
    return ok and tonumber(value) == 1
end
local function text(hex,maximum)
    if #hex % 2 ~= 0 or #hex > maximum * 2 or hex:find('[^%x]') then error('invalid kneeboard text') end
    local value = hex:gsub('%x%x',function(byte) return string.char(tonumber(byte,16)) end)
    if value:find('[^\032-\126\010]') then error('unsupported kneeboard characters') end
    return value
end
local function split_lines(value)
    local result = {}
    if value ~= '' then
        for line in (value .. '\n'):gmatch('(.-)\n') do result[#result+1] = line end
    end
    return result
end
local function commit(transaction)
    if not staged or staged.id ~= transaction then error('no matching kneeboard update') end
    if not ready() then error('live kneeboard page is not loaded') end
    local updates = {{'TITLE',staged.title},{'PAGES',tostring(staged.count)}}
    for page = 1,capacity do
        local suffix = string.format('%02d',page)
        local rows = {}
        for _,column in ipairs({'PAGE','FIELD','VALUE'}) do
            local value = ''
            if page <= staged.count then
                value = staged.columns[page] and staged.columns[page][column]
                if value == nil then error('incomplete kneeboard update') end
            end
            updates[#updates+1] = {column .. '_' .. suffix,value}
            rows[column] = split_lines(value)
        end
        local layout = page <= staged.count and staged.columns[page].LAYOUT or nil
        local count = math.max(#rows.PAGE,#rows.FIELD,#rows.VALUE)
        if layout and #layout ~= count then error('invalid kneeboard row layout') end
        local kinds = {}
        for row = 1,24 do
            local mark = layout and layout:sub(row,row)
            -- Older publishers have no explicit continuation metadata.
            local section = (rows.PAGE[row] or '') ~= '' and (rows.FIELD[row] or '') == '' and (rows.VALUE[row] or '') == ''
            kinds[row] = row > count and 0 or (mark == 'S' or (not layout and section)) and 3 or mark == 'C' and 2 or 1
        end
        for row = 1,24 do
            local key = suffix .. '_' .. string.format('%02d',row)
            for _,column in ipairs({'PAGE','FIELD','VALUE'}) do
                updates[#updates+1] = {'ROW_'..column..'_'..key,rows[column][row] or ''}
            end
            updates[#updates+1] = {'ROW_KIND_'..key,kinds[row]}
            updates[#updates+1] = {'ROW_RULE_'..key,kinds[row] > 0 and kinds[row+1] ~= 2 and 1 or 0}
        end
        updates[#updates+1] = {'FOOTER_' .. suffix,page <= staged.count and ('PAGE '..page..' / '..staged.count) or ('END OF PLAN / '..staged.count..' USED PAGES')}
    end
    updates[#updates+1] = {'REVISION',transaction}
    local old = {}
    for i,item in ipairs(updates) do old[i] = param(item[1]):get() end
    local ok,err = pcall(function()
        for _,item in ipairs(updates) do param(item[1]):set(item[2]) end
        for _,item in ipairs(updates) do
            if tostring(param(item[1]):get()) ~= tostring(item[2]) then error('parameter readback mismatch') end
        end
    end)
    local count = staged.count
    staged = nil
    if not ok then
        for i,item in ipairs(updates) do pcall(function() param(item[1]):set(old[i]) end) end
        error('kneeboard text was not verified')
    end
    return 'OK KB_COMMITTED '..transaction..' '..count
end
function M.handle(body,now,busy)
    local ok,result = pcall(function()
        if body == 'KB_STATUS' then
            if not available() then error('DCS export text parameters unavailable') end
            local revision = tostring(param('REVISION'):get())
            if not revision:match('^%x+$') or #revision ~= 32 then revision = '-' end
            local count = tonumber(param('PAGES'):get()) or 0
            return 'OK KB_STATUS 1 '..(ready() and '1' or '0')..' '..count..' '..capacity..' '..revision
        end
        if busy then error('bridge busy with CDU input') end
        if staged and now - staged.started > 30 then staged = nil end
        local transaction,count,hex = body:match('^KB_BEGIN|(%x+)|(%d+)|(%x*)$')
        if transaction then
            count = tonumber(count)
            if #transaction ~= 32 or count < 1 or count > capacity then error('invalid kneeboard update') end
            if not ready() then error('live kneeboard page is not loaded') end
            staged = {id=transaction,count=count,title=text(hex,80),columns={},started=now}
            return 'OK KB_BEGIN '..transaction
        end
        local page,column
        transaction,page,column,hex = body:match('^KB_DATA|(%x+)|(%d+)|([A-Z]+)|(%x*)$')
        if transaction then
            page = tonumber(page)
            if not staged or staged.id ~= transaction or page < 1 or page > staged.count then error('no matching kneeboard update') end
            if column ~= 'PAGE' and column ~= 'FIELD' and column ~= 'VALUE' and column ~= 'LAYOUT' then error('invalid kneeboard column') end
            local value = text(hex,1024)
            if column == 'LAYOUT' and (#value > 24 or value:find('[^SRC]')) then error('invalid kneeboard row layout') end
            local _,breaks = value:gsub('\n','')
            if breaks >= 24 then error('too many kneeboard lines') end
            staged.columns[page] = staged.columns[page] or {}
            staged.columns[page][column] = value
            return 'OK KB_DATA '..transaction..' '..page..' '..column
        end
        transaction = body:match('^KB_COMMIT|(%x+)$')
        if transaction and #transaction == 32 then return commit(transaction) end
        error('invalid kneeboard request')
    end)
    return ok and result or 'ERROR '..tostring(result)
end
return M
