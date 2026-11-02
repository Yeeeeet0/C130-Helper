-- Original Helper live page. Loaded by wrappers in Saved Games/Kneeboard/C-130J-30.
dofile(LockOn_Options.common_script_path .. 'KNEEBOARD/indicator/definitions.lua')
SetScale(FOV)
local page = assert(tonumber(C130J_HELPER_KB_PAGE))
assert(page >= 1 and page <= 20)
local suffix = string.format('%02d', page)
local prefix = 'C130J_HELPER_KB_'
local aspect = GetAspect()
local background = CreateElement 'ceMeshPoly'
background.name = prefix .. 'BACKGROUND_' .. suffix
background.primitivetype = 'triangles'
background.vertices = {{-1,aspect},{1,aspect},{1,-aspect},{-1,-aspect}}
background.indices = {0,1,2,0,2,3}
background.material = MakeMaterial(nil,{11,20,30,255})
background.h_clip_relation = h_clip_relations.COMPARE
background.level = DEFAULT_LEVEL
background.additive_alpha = false
Add(background)
local font = MakeFont({used_DXUnicodeFontData='font_dejavu_lgc_sans_22'},{220,235,244,255})
local accent = MakeFont({used_DXUnicodeFontData='font_dejavu_lgc_sans_22'},{159,241,218,255})
local grid = MakeMaterial(nil,{54,79,96,255})
local band = MakeMaterial(nil,{24,44,57,255})
local function rectangle(name,left,top,right,bottom,material,parameter,low,high)
    local element = CreateElement 'ceMeshPoly'
    element.name = prefix .. name .. '_' .. suffix
    element.primitivetype = 'triangles'
    element.vertices = {{left,top},{right,top},{right,bottom},{left,bottom}}
    element.indices = {0,1,2,0,2,3}
    element.material = material
    element.h_clip_relation = h_clip_relations.COMPARE
    element.level = DEFAULT_LEVEL
    element.additive_alpha = false
    if parameter then
        element.element_params = {prefix .. parameter}
        element.controllers = {{'parameter_in_range',0,low,high}}
    end
    Add(element)
end
local function text(name,value,x,y,size,parameter,material)
    local element = CreateElement 'ceStringPoly'
    element.name = prefix .. name .. '_' .. suffix
    element.material = material or font
    element.init_pos = {x,y,0}
    element.alignment = 'LeftTop'
    element.stringdefs = {size,size*0.25,0,0}
    element.use_mipfilter = true
    element.h_clip_relation = h_clip_relations.COMPARE
    element.level = DEFAULT_LEVEL
    element.additive_alpha = false
    if parameter then
        element.formats = {'%s'}
        element.element_params = {prefix .. parameter}
        element.controllers = {{'text_using_parameter',0,0}}
    else element.value = value end
    Add(element)
end
text('HEADING','CDU PLAN',-0.93,aspect-0.08,0.007,nil,accent)
text('TITLE','',-0.93,aspect-0.24,0.0045,'TITLE')
local left,right = -0.96,0.96
local bodyTop,pitch = aspect-0.50,0.063
rectangle('HEADER_BAND',left,aspect-0.37,right,bodyTop,band)
rectangle('HEADER_TOP',left,aspect-0.37,right,aspect-0.372,grid)
rectangle('HEADER_BOTTOM',left,bodyTop,right,bodyTop-0.002,grid)
for index,x in ipairs({left,-0.31,0.12,right}) do
    rectangle('HEADER_COLUMN_'..index,x,aspect-0.37,x+0.002,bodyTop,grid)
end
text('PAGE_LABEL','PAGE',-0.93,aspect-0.40,0.0045,nil,accent)
text('FIELD_LABEL','FIELD',-0.28,aspect-0.40,0.0045,nil,accent)
text('VALUE_LABEL','CDU VALUE',0.15,aspect-0.40,0.0045,nil,accent)
for row = 1,24 do
    local key = suffix .. '_' .. string.format('%02d',row)
    local kind = 'ROW_KIND_' .. key
    local top = bodyTop-(row-1)*pitch
    local bottom = top-pitch
    rectangle('SECTION_'..row,left,top,right,bottom,band,kind,2.5,3.5)
    for index,x in ipairs({left,right}) do
        rectangle('EDGE_'..row..'_'..index,x,top,x+0.002,bottom,grid,kind,0.5,3.5)
    end
    for index,x in ipairs({-0.31,0.12}) do
        rectangle('COLUMN_'..row..'_'..index,x,top,x+0.002,bottom,grid,kind,0.5,2.5)
    end
    rectangle('RULE_'..row,left,bottom+0.002,right,bottom,grid,'ROW_RULE_'..key,0.5,1.5)
    text('ROW_PAGE_'..row,'',-0.93,top-0.014,0.0040,'ROW_PAGE_'..key)
    text('ROW_FIELD_'..row,'',-0.28,top-0.014,0.0040,'ROW_FIELD_'..key)
    text('ROW_VALUE_'..row,'',0.15,top-0.014,0.0040,'ROW_VALUE_'..key,accent)
end
text('FOOTER','',-0.93,-aspect+0.13,0.0040,'FOOTER_'..suffix)
local revision = get_param_handle(prefix .. 'REVISION'):get()
if type(revision) ~= 'string' or #revision ~= 32 then
    get_param_handle(prefix .. 'TITLE'):set('NO PLAN SENT')
    for row = 1,24 do
        local key = suffix .. '_' .. string.format('%02d',row)
        for _,column in ipairs({'PAGE','FIELD','VALUE'}) do
            get_param_handle(prefix .. 'ROW_'..column..'_'..key):set(column == 'PAGE' and row == 1 and page == 1 and 'Send from helper' or '')
        end
        get_param_handle(prefix .. 'ROW_KIND_'..key):set(row == 1 and page == 1 and 1 or 0)
        get_param_handle(prefix .. 'ROW_RULE_'..key):set(row == 1 and page == 1 and 1 or 0)
    end
    get_param_handle(prefix .. 'FOOTER_' .. suffix):set('LIVE CDU PLAN / READY')
end
-- A real page must load before the bridge can acknowledge a successful send.
get_param_handle(prefix .. 'READY'):set(1)
