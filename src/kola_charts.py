"""Kola-only overview pyramid built from the installed charts' DDS mipmaps."""
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import struct
import threading
import uuid
import zipfile


def dds_mip(data,level):
    if data[:4]!=b'DDS ' or len(data)<128:raise ValueError('Invalid DDS chart')
    height,width=struct.unpack_from('<2I',data,12)
    count=struct.unpack_from('<I',data,28)[0]
    kind=data[84:88]
    if kind not in (b'DXT1',b'DXT3',b'DXT5') or not (0<width<=4096 and 0<height<=4096):raise ValueError('Unsupported DDS chart')
    if level<0 or level>=count:raise ValueError('DDS chart has no requested mipmap')
    stride=8 if kind==b'DXT1' else 16
    size=lambda w,h:((w+3)//4)*((h+3)//4)*stride
    offset=128
    for _ in range(level):offset+=size(width,height);width=max(1,width//2);height=max(1,height//2)
    length=size(width,height)
    if offset+length>len(data):raise ValueError('Truncated DDS mipmap')
    header=bytearray(data[:128])
    struct.pack_into('<I',header,8,struct.unpack_from('<I',header,8)[0]&~0x20000)
    struct.pack_into('<3I',header,12,height,width,length)
    struct.pack_into('<I',header,28,1)
    struct.pack_into('<I',header,108,0x1000)
    return bytes(header)+data[offset:offset+length]


class KolaChartPyramid:
    factors=(4,16)

    def __init__(self,tiles,cache):
        self.native=list(tiles)
        if not self.native:raise ValueError('No Kola charts')
        self.span=self.native[0]['bounds'][2]-self.native[0]['bounds'][0]
        if any(t['scale']!=32 or t['bounds'][2]-t['bounds'][0]!=self.span or t['bounds'][3]-t['bounds'][1]!=self.span for t in self.native):
            raise ValueError('Unsupported Kola overview chart grid')
        self.origin=(min(t['bounds'][0] for t in self.native),min(t['bounds'][1] for t in self.native))
        xs=sorted({t['bounds'][0] for t in self.native});ys=sorted({t['bounds'][1] for t in self.native})
        self.step_x=xs[1]-xs[0] if len(xs)>1 else self.span
        self.step_y=ys[1]-ys[0] if len(ys)>1 else self.span
        if not all(self.span*.99<=step<=self.span for step in (self.step_x,self.step_y)):raise ValueError('Unsupported Kola chart overlap')
        archives=sorted({t['archive'] for t in self.native})
        signature=[('overview',2)]+[(str(p.resolve()),p.stat().st_mtime_ns,p.stat().st_size) for p in archives]
        self.token=hashlib.sha256(json.dumps(signature).encode()).hexdigest()[:20]
        self.geometry=hashlib.sha256(json.dumps(sorted((t['member'],t['bounds']) for t in self.native)).encode()).hexdigest()[:16]
        self.cache=Path(cache)/self.token;self.cache.mkdir(parents=True,exist_ok=True)
        self._lock=threading.Lock();self._locks={}
        self.tiles={}
        for factor in self.factors:
            groups=defaultdict(list)
            for t in self.native:
                col=(t['bounds'][0]-self.origin[0])/self.step_x;row=(t['bounds'][1]-self.origin[1])/self.step_y
                if abs(col-round(col))>.0001 or abs(row-round(row))>.0001:raise ValueError('Misaligned Kola chart grid')
                col,row=round(col),round(row)
                groups[(col//factor,row//factor)].append((col%factor,row%factor,t))
            for (col,row),members in groups.items():
                x=self.origin[0]+col*factor*self.step_x;y=self.origin[1]+row*factor*self.step_y
                key=f'Kola:overview:{32*factor}:{col}:{row}'
                self.tiles[key]=dict(id=key,name=f'Kola overview {32*factor} m/px',scale=32*factor,
                    bounds=[x,y,x+(factor-1)*self.step_x+self.span,y+(factor-1)*self.step_y+self.span],overview=True,factor=factor,members=members)

    def _key_lock(self,key):
        with self._lock:return self._locks.setdefault(key,threading.Lock())

    def _save(self,image,path):
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:image.save(temp,format='PNG',compress_level=1);temp.replace(path)
        finally:temp.unlink(missing_ok=True)

    def _thumbnail(self,tile,factor):
        from PIL import Image
        key=hashlib.sha256((str(tile['archive'])+'|'+tile['member']).encode()).hexdigest()[:24]
        path=self.cache/f'{key}-{factor}.png'
        with self._key_lock(key):
            if not path.is_file():
                with zipfile.ZipFile(tile['archive']) as archive:data=archive.read(tile['member'])
                # Build both thumbnail sizes from the same decompression pass.
                for f in self.factors:
                    destination=self.cache/f'{key}-{f}.png'
                    if destination.is_file():continue
                    mip=dds_mip(data,{4:2,16:4}[f])
                    with Image.open(io.BytesIO(mip)) as image:self._save(image.convert('RGBA'),destination)
        return path

    def tile(self,key):
        from PIL import Image
        tile=self.tiles[key]
        path=self.cache/('overview-'+self.geometry+'-'+key.replace(':','-')+'.png')
        with self._key_lock(key):
            if not path.is_file():
                factor=tile['factor'];piece=1024//factor
                with Image.new('RGBA',(1024,1024),(0,0,0,0)) as overview:
                    for col,row,source in tile['members']:
                        with Image.open(self._thumbnail(source,factor)) as thumbnail:
                            if thumbnail.size!=(piece,piece):raise ValueError('Kola overview mip dimensions changed')
                            # Native Kola sheets overlap by one pixel. Retain
                            # their world bounds instead of accumulating a seam offset.
                            x0,y0,x1,y1=tile['bounds'];sx0,sy0,sx1,sy1=source['bounds']
                            left=round((sx0-x0)/(x1-x0)*1024);right=round((sx1-x0)/(x1-x0)*1024)
                            top=round((y1-sy1)/(y1-y0)*1024);bottom=round((y1-sy0)/(y1-y0)*1024)
                            if thumbnail.size!=(right-left,bottom-top):
                                with thumbnail.resize((right-left,bottom-top),Image.Resampling.BILINEAR) as fitted:overview.paste(fitted,(left,top))
                            else:overview.paste(thumbnail,(left,top))
                    self._save(overview,path)
        return path.read_bytes()
