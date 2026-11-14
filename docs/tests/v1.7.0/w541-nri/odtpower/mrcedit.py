import struct, xxhash, mmap, os, sys, importlib.util
spec=importlib.util.spec_from_file_location("upd","/home/domenico/ourobios-test-v1.6.3/w541-nri/xmp/rc12/tools/update.py"); u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
img=bytearray(open(sys.argv[1],'rb').read())
o,s=u.fmap_areas(bytes(img))["RW_MRC_CACHE"]
r=img[o:o+s]
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC); m=mmap.mmap(fd,0x8000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xfed10000)
live=[struct.unpack_from('<I',m,0x60+0x100*ch+0x200*b)[0] for ch in (0,1) for b in range(8)]
i=0; found=[]
while True:
    i=r.find(b'MRCd',i)
    if i<0: break
    sig,size,dh,hh,ver=struct.unpack_from('<IIIII',r,i)
    if size < len(r):
        d=bytes(r[i+20:i+20+size]); found.append((i,size,xxhash.xxh32(d,0).intdigest()==dh,ver))
    i+=4
for f in found: print("entry at 0x%x size %d hash-ok %s version 0x%x"%f)
i,size,ok,ver=[f for f in found if f[2]][-1]
d=bytearray(r[i+20:i+20+size])
offs=[(ch*9+b)*116+88 for ch in (0,1) for b in range(8)]
cur=[struct.unpack_from('<I',d,x)[0] for x in offs]
print("control_1 in the cache = live registers:", cur==live)
if len(sys.argv)>2 and cur==live:
    MASK=(0xf<<13)|(7<<17)|(0xf<<20)|(7<<24); dd=(-2)&0xf
    for x in offs:
        v=struct.unpack_from('<I',d,x)[0]; struct.pack_into('<I',d,x,(v&~MASK)|(dd<<13)|(7<<17)|(dd<<20)|(7<<24))
    dh=xxhash.xxh32(bytes(d),0).intdigest()
    hdr=struct.pack('<IIIII',0x6443524d,size,dh,0,ver); hh=xxhash.xxh32(hdr,0).intdigest()
    hdr=struct.pack('<IIIII',0x6443524d,size,dh,hh,ver)
    img[o+i:o+i+20]=hdr; img[o+i+20:o+i+20+size]=d
    open(sys.argv[2],'wb').write(img); print("written", sys.argv[2], "with the wide window (-2/7) in the saved training")
