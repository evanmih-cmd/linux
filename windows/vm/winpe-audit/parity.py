"""Parallel host-side VDI fact audit, not a replacement for WinPE audit.

Example:
  PYTHONPATH=~/.cache/desktop-windows/diag-libs python3 parity.py \
       --bench ~/.cache/desktop-windows-two-disk/vbox-bench
Optional: --winpe-report path/to/audit.txt copied from USB.
Only opens VDI images read-only.  Does not call VirtualBox.
"""
import argparse
import json
import struct
import uuid
import zlib
from pathlib import Path
from dissect.hypervisor.disk.vdi import VDI
from dissect.util.stream import RangeStream
from dissect.ntfs import NTFS

GPT_TYPES = {
    "c12a7328-f81f-11d2-ba4b-00a0c93ec93b": "ESP",
    "e3c9e316-0b5c-4db8-817d-f92df00215ae": "MSR",
    "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7": "BASIC",
    "de94bba4-06d1-4d40-a16a-bfd50179d6ac": "RECOVERY",
}
def check_gpt(f):
    f.seek(0)
    mbr=f.read(512)
    f.seek(512)
    h=f.read(512)
    size=struct.unpack_from("<I", h, 12)[0]
    expect=struct.unpack_from("<I", h, 16)[0]
    check=bytearray(h[:size]);check[16:20]=bytes(4)
    assert mbr[510:512] == b"\x55\xaa" and mbr[450]==0xee
    assert h[:8] == b"EFI PART" and zlib.crc32(check)==expect
    usable=struct.unpack_from("<Q",h,48)[0]
    sector=512
    table_lba,count,esize,crc=struct.unpack_from("<QIII",h,72)
    f.seek(table_lba*sector)
    table=f.read(count*esize)
    assert zlib.crc32(table)==crc
    back_lba=struct.unpack_from("<Q",h,32)[0]
    f.seek(back_lba*sector);back=f.read(sector)
    check=bytearray(back[:size]);check[16:20]=bytes(4)
    assert back[:8]==b"EFI PART" and zlib.crc32(check)==struct.unpack_from("<I",back,16)[0]
    alt_lba,ac,ae,crc2=struct.unpack_from("<QIII",back,72)
    f.seek(alt_lba*sector);alt=f.read(ac*ae)
    assert zlib.crc32(alt)==crc2 and alt==table
    parts=[]
    for i in range(count):
        e=table[i*esize:(i+1)*esize]
        if not any(e[:16]):continue
        first,last,attrs=struct.unpack_from("<QQQ",e,32)
        parts.append(dict(kind=GPT_TYPES.get(str(uuid.UUID(bytes_le=e[:16])),"OTHER"),
                          start=first,end=last,attrs=attrs,mib=(last-first+1)*sector//1048576))
    return parts,usable,str(uuid.UUID(bytes_le=h[56:72]))
def fat32_has(f,start,path):
    # Existing legacy FAT inspection, independent of WinPE volume enumeration.
    off=start*512
    f.seek(off);boot=f.read(512)
    bps=struct.unpack_from("<H",boot,11)[0];spc=boot[13]
    res=struct.unpack_from("<H",boot,14)[0];nfats=boot[16]
    fatsize=struct.unpack_from("<I",boot,36)[0]
    root=struct.unpack_from("<I",boot,44)[0]
    datastart=(res+nfats*fatsize)*bps
    clusterbytes=bps*spc
    def read(pos,size):
        f.seek(off+pos);return f.read(size)
    def getchain(first):
        seen=set()
        while 2<=first<0x0ffffff8 and first not in seen:
            seen.add(first);yield first
            first=struct.unpack("<I",read(res*bps+first*4,4))[0]&0x0fffffff
    def body(cluster):
        return b"".join(read(datastart+(n-2)*clusterbytes,clusterbytes) for n in getchain(cluster))
    def contents(cluster):
        raw=body(cluster)
        lfn=[]
        for i in range(0,len(raw),32):
            e=raw[i:i+32]
            if len(e)!=32 or e[0]==0:break
            if e[0]==0xe5:lfn.clear();continue
            if e[11]==0x0f:
                words=e[1:11]+e[14:26]+e[28:32]
                lfn.append((e[0]&31,"".join(chr(n) for (n,) in struct.iter_unpack("<H",words) if n not in (0,0xffff))))
                continue
            name=("".join(x[1] for x in sorted(lfn)) or e[:8].decode("ascii","replace").strip()+"."+e[8:11].decode("ascii","replace").strip()).strip(".")
            lfn.clear()
            if e[11]&8:continue
            cl=struct.unpack_from("<H",e,20)[0]<<16|struct.unpack_from("<H",e,26)[0]
            yield name,cl,struct.unpack_from("<I",e,28)[0]
    cl=root
    for part in path.split("/"):
        found=next((x for x in contents(cl) if x[0].casefold()==part.casefold()),None)
        if not found:return False
        cl=found[1]
    raw=body(cl)[:found[2]]
    return raw.startswith(b"regf") if path.endswith("/BCD") else raw.startswith(b"MZ")
def ntfs_info(f,p):
    v=RangeStream(f,p["start"]*512,(p["end"]-p["start"]+1)*512)
    return NTFS(v)
def ntfs_has(ntfs,path,prefix=None):
    try:
        rec=ntfs.mft.get(path)
        head=rec.open().read(8)
        return rec.size()>0 and (prefix is None or head.startswith(prefix))
    except FileNotFoundError:return False
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bench",type=Path,required=True)
    p.add_argument("--winpe-report",type=Path)
    a=p.parse_args()
    checks={}
    def test(key,yes):
        checks[key]="PASS" if yes else "FAIL"
    with (a.bench/"windows11-pro.vdi").open("rb",buffering=0) as fh:
        f=VDI(fh).open()
        pts,usable,guid=check_gpt(f)
        kinds=[x["kind"] for x in pts]
        test("target.gpt_four_types",kinds==["ESP","MSR","BASIC","RECOVERY"])
        e,m,w,r=pts
        test("target.esp_300",e["mib"]==300)
        test("target.msr_16",m["mib"]==16)
        test("target.winre_2048",r["mib"]==2048)
        test("target.winre_attributes",r["attrs"]==0x8000000000000001)
        contiguous=all(pts[i]["end"]+1==pts[i+1]["start"] for i in range(3))
        test("target.contiguous",contiguous)
        test("target.windows_rest",w["mib"]>2048 and contiguous)
        test("target.winre_disk_tail",r["end"]<=usable and (usable-r["end"])*512<=1048576)
        f.seek(e["start"]*512);esp=f.read(512)
        f.seek(w["start"]*512);win=f.read(512)
        f.seek(r["start"]*512);re=f.read(512)
        test("target.esp_fat32",esp[82:87]==b"FAT32")
        test("target.windows_ntfs",win[3:11]==b"NTFS    ")
        test("target.recovery_ntfs",re[3:11]==b"NTFS    ")
        test("esp.bcd",fat32_has(f,e["start"],"EFI/Microsoft/Boot/BCD"))
        test("esp.bootmgfw",fat32_has(f,e["start"],"EFI/Microsoft/Boot/bootmgfw.efi"))
        test("esp.fallback",fat32_has(f,e["start"],"EFI/Boot/bootx64.efi"))
        ntfs=ntfs_info(f,w);recovery=ntfs_info(f,r)
        test("windows.kernel",ntfs_has(ntfs,r"\Windows\System32\ntoskrnl.exe",b"MZ"))
        test("windows.winload",ntfs_has(ntfs,r"\Windows\System32\winload.efi",b"MZ"))
        test("windows.registry",ntfs_has(ntfs,r"\Windows\System32\config\SYSTEM",b"regf"))
        test("recovery.winre",ntfs_has(recovery,r"\Recovery\WindowsRE\Winre.wim",b"MSWIM"))
        xml=ntfs_has(ntfs,r"\Windows\Panther\Unattend.xml")
        test("windows.canonical_unattend",xml)
        source=a.bench/"answer-media"/"Autounattend.xml"
        if xml and source.is_file():
            installed=ntfs.mft.get(r"\Windows\Panther\Unattend.xml").open().read()
            test("windows.answer_identity",installed==source.read_bytes())
        else:
            test("windows.answer_identity",False)
        reg=ntfs.mft.get(r"\Windows\System32\Recovery\ReAgent.xml").open().read().decode("utf-8-sig")
        test("recovery.reagent_registration",
             ("offset=\""+str(r["start"]*512)+"\"") in reg and guid in reg and "\\Recovery\\WindowsRE" in reg)
    with (a.bench/"protected-home.vdi").open("rb",buffering=0) as fh:
        f=VDI(fh).open()
        protected,unused,dguid=check_gpt(f)
        test("protected.gpt_valid",len(protected)>=3)
        state=json.loads((a.bench/"protected-ssd1.json").read_text())
        f.seek(state["sentinel_lba"]*512)
        import hashlib
        marker=b"WINDOWS-BENCH-SSD1-PRESERVATION-DO-NOT-WIPE:"+dguid.encode("ascii")
        test("protected.sentinel_intact",hashlib.sha256(f.read(len(marker))).hexdigest()==state["sentinel_sha256"])
    print("PARITY_HOST_FACTS",json.dumps(checks,sort_keys=True,indent=2))
    if a.winpe_report:
        guest={}
        for line in a.winpe_report.read_text().splitlines():
            if line.startswith("CHECK "):
                parts=line.split(" ",3)
                guest[parts[1]]=parts[2]
        common=set(checks)&set(guest)
        mismatches={k:(checks[k],guest[k]) for k in common if checks[k]!=guest[k]}
        print("COMMON",len(common),"MISMATCHES",len(mismatches),mismatches)
        if len(common)<len(checks)-1 or mismatches:raise SystemExit(1)
    if any(v=="FAIL" for k,v in checks.items() if k!="windows.canonical_unattend"):raise SystemExit(1)
if __name__=="__main__":main()
