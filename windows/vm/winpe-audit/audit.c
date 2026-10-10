/* WinPE Audit: read-only validation of manually deployed Windows 11 Pro.
 * Uses only Win32 APIs; does not open devices with GENERIC_WRITE.
 * No disk formatting, repair, partitioning, registry loading or mounting.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0602
#include <windows.h>
#include <winioctl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>
#ifndef IOCTL_DISK_GET_DISK_ATTRIBUTES
#define IOCTL_DISK_GET_DISK_ATTRIBUTES CTL_CODE(IOCTL_DISK_BASE,0x003c,METHOD_BUFFERED,FILE_ANY_ACCESS)
typedef struct {DWORD Version;DWORD Reserved1;ULONGLONG Attributes;} GET_DISK_ATTRIBUTES;
#define DISK_ATTRIBUTE_OFFLINE 0x0000000000000001ull
#endif
#include <ctype.h>

#define MAX_PARTS 128
#define CHECK(a) do { if (!(a)) {fprintf(stderr,"FATAL %s:%d\n",__FILE__,__LINE__); return 3;} } while(0)
static int pass=0, fail=0, np=0;
static void result(const char *id, const char *status, const char *detail) {
    printf("CHECK %s %s %s\n",id,status,detail);
    if (!strcmp(status,"PASS"))pass++;
    else if (!strcmp(status,"FAIL"))fail++;
    else np++;
    fflush(stdout);
}
static void test(const char *id,int condition,const char *detail) {result(id,condition?"PASS":"FAIL",detail);}
static void disk_test(const char *prefix,const char *what,int condition,const char*detail) {char key[120];snprintf(key,sizeof(key),"%s.%s",prefix,what);test(key,condition,detail);}
static uint16_t le16(const uint8_t*p){return (uint16_t)(p[0]|p[1]<<8);}
static uint32_t le32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t le64(const uint8_t*p){return (uint64_t)le32(p)|((uint64_t)le32(p+4)<<32);}
static uint32_t crc32(const uint8_t*p,size_t n) {
    uint32_t c=~(uint32_t)0;
    for(size_t i=0;i<n;i++){c^=p[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)?0xedb88320u:0);}
    return ~c;
}
static const uint8_t T_ESP[16]={0x28,0x73,0x2a,0xc1,0x1f,0xf8,0xd2,0x11,0xba,0x4b,0x00,0xa0,0xc9,0x3e,0xc9,0x3b};
static const uint8_t T_MSR[16]={0x16,0xe3,0xc9,0xe3,0x5c,0x0b,0xb8,0x4d,0x81,0x7d,0xf9,0x2d,0xf0,0x02,0x15,0xae};
static const uint8_t T_BASIC[16]={0xa2,0xa0,0xd0,0xeb,0xe5,0xb9,0x33,0x44,0x87,0xc0,0x68,0xb6,0xb7,0x26,0x99,0xc7};
static const uint8_t T_RE[16]={0xa4,0xbb,0x94,0xde,0xd1,0x06,0x40,0x4d,0xa1,0x6a,0xbf,0xd5,0x01,0x79,0xd6,0xac};
typedef struct {uint8_t type[16];uint8_t unique[16];uint64_t first,last,attrs;} Part;
typedef struct {
    int number, valid;
    HANDLE file;
    uint64_t bytes, sector, last_usable;
    uint8_t guid[16];
    Part parts[MAX_PARTS];
    int n;
} Disk;
static int pread_disk(Disk*d,uint64_t off,void*b,DWORD size){
    LARGE_INTEGER pos;pos.QuadPart=(LONGLONG)off;
    DWORD got=0;
    return SetFilePointerEx(d->file,pos,NULL,FILE_BEGIN)&&ReadFile(d->file,b,size,&got,NULL)&&got==size;
}
static void disk_guid(const uint8_t*guid,char*out,size_t n){
    snprintf(out,n,"%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",
       (unsigned long)le32(guid),le16(guid+4),le16(guid+6),
       guid[8],guid[9],guid[10],guid[11],guid[12],guid[13],guid[14],guid[15]);
}
static int gpt_header(Disk*d,uint64_t lba,uint8_t *hdr,uint64_t *table_lba,uint32_t *count,uint32_t *entrysize,uint32_t *tablecrc){
    if (!pread_disk(d,lba*d->sector,hdr,(DWORD)d->sector))return 0;
    if (memcmp(hdr,"EFI PART",8))return 0;
    uint32_t len=le32(hdr+12), saved=le32(hdr+16);
    if (len<92||len>d->sector)return 0;
    uint8_t tmp[4096];
    if (len>sizeof(tmp))return 0;
    memcpy(tmp,hdr,len);memset(tmp+16,0,4);
    if(crc32(tmp,len)!=saved)return 0;
    *table_lba=le64(hdr+72);*count=le32(hdr+80);*entrysize=le32(hdr+84);*tablecrc=le32(hdr+88);
    if(!*count||*count>MAX_PARTS||*entrysize!=128)return 0;
    return le64(hdr+24)==lba;
}
static int disk_open(Disk*d,int number,const char*prefix){
    memset(d,0,sizeof(*d));d->number=number;d->file=INVALID_HANDLE_VALUE;
    wchar_t name[80];swprintf(name,80,L"\\\\.\\PhysicalDrive%d",number);
    d->file=CreateFileW(name,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
    if(d->file==INVALID_HANDLE_VALUE){char desc[180];sprintf(desc,"PhysicalDrive%d read-only open error=%lu",number,GetLastError());result(prefix,"FAIL",desc);return 0;}
    DISK_GEOMETRY_EX geometry;
    DWORD used=0;
    if(!DeviceIoControl(d->file,IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,NULL,0,&geometry,sizeof(geometry),&used,NULL)){
        result(prefix,"FAIL","Could not determine disk geometry");return 0;
    }
    d->sector=geometry.Geometry.BytesPerSector;
    d->bytes=(uint64_t)geometry.DiskSize.QuadPart;
    if(d->sector!=512&&d->sector!=4096){result(prefix,"FAIL","Unsupported logical sector size");return 0;}
    d->valid=1;return 1;
}
static int read_gpt(Disk*d,const char*prefix){
    if(!d->valid)return 0;
    uint8_t mbr[4096],hdr[4096],backup[4096];
    uint64_t entries_lba,back_lba;
    uint32_t cnt,es,ec,bc,bes,bec;
    int okay=1;
    if(!pread_disk(d,0,mbr,(DWORD)d->sector)){result(prefix,"FAIL","Cannot read sector zero");return 0;}
    disk_test(prefix,"protective_mbr",mbr[510]==0x55&&mbr[511]==0xaa&&mbr[446+4]==0xee,"Protective MBR");
    int primary=gpt_header(d,1,hdr,&entries_lba,&cnt,&es,&ec);
    disk_test(prefix,"primary_gpt_crc",primary,"GPT header CRC and signature");
    if(!primary)return 0;
    memcpy(d->guid,hdr+56,16);
    d->last_usable=le64(hdr+48);
    uint64_t backup_lba=le64(hdr+32);
    uint64_t disk_lba=d->bytes/d->sector;
    disk_test(prefix,"backup_gpt_location",backup_lba==disk_lba-1,"Backup GPT is physically last sector");
    int back=gpt_header(d,backup_lba,backup,&back_lba,&bc,&bes,&bec);
    disk_test(prefix,"backup_gpt_crc",back&&le64(backup+32)==1&&memcmp(hdr+56,backup+56,16)==0,"Backup GPT CRC/matching disk GUID");
    if(!back)return 0;
    size_t tablebytes=(size_t)cnt*es;
    uint8_t *entries=malloc(tablebytes),*other=malloc(tablebytes);
    if(!entries||!other){result(prefix,"FAIL","Cannot allocate GPT table");free(entries);free(other);return 0;}
    int table=pread_disk(d,entries_lba*d->sector,entries,(DWORD)tablebytes)&&crc32(entries,tablebytes)==ec;
    disk_test(prefix,"primary_entries_crc",table,"Primary GPT entry array CRC");
    int table2=pread_disk(d,back_lba*d->sector,other,(DWORD)tablebytes)&&crc32(other,tablebytes)==bec&&memcmp(entries,other,tablebytes)==0;
    disk_test(prefix,"backup_entries_crc",table2,"Backup GPT entry array CRC and identity");
    if(!table||!table2)okay=0;
    if(table)for(uint32_t i=0;i<cnt;i++){
        uint8_t*e=entries+i*es;
        uint8_t empty[16]={0};
        if(memcmp(e,empty,16)==0)continue;
        Part*p=&d->parts[d->n++];
        memcpy(p->type,e,16);memcpy(p->unique,e+16,16);
        p->first=le64(e+32);p->last=le64(e+40);p->attrs=le64(e+48);
        printf("PART disk=%d index=%d lba=%llu..%llu size_mib=%.3f attrs=%llx\n",
            d->number,d->n,(unsigned long long)p->first,(unsigned long long)p->last,
            (p->last-p->first+1)*d->sector/1048576.0,(unsigned long long)p->attrs);
    }
    free(entries);free(other);
    return okay;
}
static int type_is(const Part*p,const uint8_t*type){return memcmp(p->type,type,16)==0;}
static uint64_t mib(const Disk*d,const Part*p){return (p->last-p->first+1)*d->sector/1048576ull;}
static int probe_fs(Disk*d,Part*p,const char*type){
    uint8_t b[4096];
    if(!pread_disk(d,p->first*d->sector,b,(DWORD)d->sector))return 0;
    if(!strcmp(type,"FAT32"))return memcmp(b+82,"FAT32",5)==0;
    if(!strcmp(type,"NTFS"))return memcmp(b+3,"NTFS    ",8)==0;
    return 0;
}
static int verify_layout(Disk*d){
    int types=d->n==4&&type_is(&d->parts[0],T_ESP)&&type_is(&d->parts[1],T_MSR)&&type_is(&d->parts[2],T_BASIC)&&type_is(&d->parts[3],T_RE);
    test("target.gpt_four_types",types,"Exactly ESP/MSR/BasicData/Recovery in order");
    if(!types)return 0;
    test("target.esp_300",mib(d,&d->parts[0])==300,"ESP exactly 300 MiB");
    test("target.msr_16",mib(d,&d->parts[1])==16,"MSR exactly 16 MiB");
    test("target.winre_2048",mib(d,&d->parts[3])==2048,"Recovery exactly 2048 MiB");
    test("target.winre_attributes",d->parts[3].attrs==0x8000000000000001ull,"Recovery required+hidden GPT attributes");
    int adjacent=1;for(int i=0;i<3;i++)if(d->parts[i].last+1!=d->parts[i+1].first)adjacent=0;
    test("target.contiguous",adjacent,"No gaps between four GPT partitions");
    test("target.windows_rest",mib(d,&d->parts[2])>2048&&adjacent,"Windows occupies space between MSR and tail WinRE");
    uint64_t slack=d->parts[3].last<=d->last_usable ? d->last_usable-d->parts[3].last : UINT64_MAX;
    test("target.winre_disk_tail",d->parts[3].last<=d->last_usable&&slack*d->sector<=1048576ull,
         "Recovery is final partition with <=1 MiB GPT alignment slack");
    test("target.esp_fat32",probe_fs(d,&d->parts[0],"FAT32"),"Target ESP formatted FAT32");
    test("target.windows_ntfs",probe_fs(d,&d->parts[2],"NTFS"),"Target Windows formatted NTFS");
    test("target.recovery_ntfs",probe_fs(d,&d->parts[3],"NTFS"),"Target Recovery formatted NTFS");
    return 1;
}

typedef struct {int found;wchar_t root[MAX_PATH];} Volume;
static Volume vols[4];
static int has_volume(Disk*d,int index){
    if(vols[index].found)return 1;
    wchar_t name[512];
    HANDLE it=FindFirstVolumeW(name,512);
    if(it==INVALID_HANDLE_VALUE)return 0;
    do {
        size_t len=wcslen(name);
        if(len<2||name[len-1]!=L'\\')continue;
        wchar_t dev[512];wcscpy(dev,name);dev[len-1]=L'\0';
        HANDLE h=CreateFileW(dev,0,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
        if(h==INVALID_HANDLE_VALUE)continue;
        uint8_t buf[sizeof(VOLUME_DISK_EXTENTS)+sizeof(DISK_EXTENT)*16];
        DWORD got=0;
        int ok=DeviceIoControl(h,IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,NULL,0,buf,sizeof(buf),&got,NULL);
        if(ok) {
            VOLUME_DISK_EXTENTS*ext=(VOLUME_DISK_EXTENTS*)buf;
            if(ext->NumberOfDiskExtents==1) {
                DISK_EXTENT*e=&ext->Extents[0];
                uint64_t expected=d->parts[index].first*d->sector;
                if(e->DiskNumber==(DWORD)d->number&&e->StartingOffset.QuadPart>=0
                   &&(uint64_t)e->StartingOffset.QuadPart==expected){
                    vols[index].found=1;wcscpy(vols[index].root,name);
                }
            }
        }
        CloseHandle(h);
    } while(FindNextVolumeW(it,name,512));
    FindVolumeClose(it);
    return vols[index].found;
}
static int volume_file(Volume*vol,const wchar_t*rel,const uint8_t*magic,int magiclen,uint64_t*size){
    if(!vol->found)return 0;
    wchar_t path[1024];
    swprintf(path,1024,L"%ls%ls",vol->root,rel);
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,
                            NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return 0;
    LARGE_INTEGER bytes={0};uint8_t head[16]={0};DWORD got=0;
    int ok=GetFileSizeEx(file,&bytes)&&bytes.QuadPart>=magiclen
           &&(!magiclen||(ReadFile(file,head,(DWORD)magiclen,&got,NULL)&&got==(DWORD)magiclen&&!memcmp(head,magic,magiclen)));
    if(size)*size=(uint64_t)bytes.QuadPart;
    CloseHandle(file);
    return ok;
}
static int volume_text(Volume*v,const wchar_t*rel,char*out,size_t limit){
    if(!v->found||limit<5)return 0;
    wchar_t name[1024];swprintf(name,1024,L"%ls%ls",v->root,rel);
    HANDLE f=CreateFileW(name,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
    if(f==INVALID_HANDLE_VALUE)return 0;
    DWORD got=0;int ok=ReadFile(f,out,(DWORD)(limit-1),&got,NULL);
    out[ok?got:0]=0;CloseHandle(f);return ok;
}
static const uint8_t MAGIC_MZ[2]={'M','Z'};
static const uint8_t MAGIC_HIVE[4]={'r','e','g','f'};
static const uint8_t MAGIC_WIM[5]={'M','S','W','I','M'};
static void check_file(const char*id,Volume*vol,const wchar_t*path,const uint8_t*sig,int siglen,uint64_t min_size){
    if(!vol->found){result(id,"NOT_PROVABLE","Matching partition volume is not accessible via WinPE volume GUID");return;}
    uint64_t size=0;int exists=volume_file(vol,path,sig,siglen,&size);
    test(id,exists&&size>=min_size,"File on verified target partition, magic and size");
}
static int strcase_has(const char*txt,const char*term){
    size_t n=strlen(term);
    for(const char*p=txt;*p;p++) {
        size_t i=0;
        for(;i<n&&p[i];i++)if(tolower((unsigned char)p[i])!=tolower((unsigned char)term[i]))break;
        if(i==n)return 1;
    }
    return 0;
}
static int verify_reagent(Disk*d){
    char buf[16384];
    if(!vols[2].found){result("recovery.reagent_registration","NOT_PROVABLE","Windows partition not mapped");return 0;}
    if(!volume_text(&vols[2],L"Windows\\System32\\Recovery\\ReAgent.xml",buf,sizeof(buf))){
        result("recovery.reagent_registration","FAIL","ReAgent.xml missing");return 0;
    }
    char guid[64],off[40];
    disk_guid(d->guid,guid,sizeof(guid));
    snprintf(off,sizeof(off),"offset=\"%llu\"",(unsigned long long)(d->parts[3].first*d->sector));
    int yes=strcase_has(buf,"<ImageLocation")&&strcase_has(buf,"\\Recovery\\WindowsRE")
        &&strcase_has(buf,guid)&&strstr(buf,off);
    test("recovery.reagent_registration",yes,"ReAgent image location references target Recovery partition GUID and byte offset");
    return yes;
}
static int same_canonical_answer(void);
static void query_bcd(void);
static void verify_files(Disk*d){
    if(d->n!=4)return;
    for(int i=0;i<4;i++){
        if(i==1)continue;
        char id[64];snprintf(id,sizeof(id),"target.volume_partition_%d",i+1);
        test(id,has_volume(d,i),"Mounted volume GUID maps to target physical disk and exact GPT byte offset");
    }
    check_file("esp.bcd",&vols[0],L"EFI\\Microsoft\\Boot\\BCD",MAGIC_HIVE,4,512);
    check_file("esp.bootmgfw",&vols[0],L"EFI\\Microsoft\\Boot\\bootmgfw.efi",MAGIC_MZ,2,500000);
    check_file("esp.fallback",&vols[0],L"EFI\\Boot\\bootx64.efi",MAGIC_MZ,2,500000);
    check_file("windows.kernel",&vols[2],L"Windows\\System32\\ntoskrnl.exe",MAGIC_MZ,2,1000000);
    check_file("windows.winload",&vols[2],L"Windows\\System32\\winload.efi",MAGIC_MZ,2,500000);
    check_file("windows.registry",&vols[2],L"Windows\\System32\\config\\SYSTEM",MAGIC_HIVE,4,512);
    check_file("recovery.winre",&vols[3],L"Recovery\\WindowsRE\\Winre.wim",MAGIC_WIM,5,100000000);
    verify_reagent(d);
    query_bcd();
    if(!vols[2].found){
        result("windows.canonical_unattend","NOT_PROVABLE","Windows volume unavailable");
    } else {
        char txt[65536]={0};
        int exists=volume_text(&vols[2],L"Windows\\Panther\\Unattend.xml",txt,sizeof(txt));
        int valid=exists&&strcase_has(txt,"<unattend")&&strcase_has(txt,"oobeSystem")
                  &&strcase_has(txt,"specialize")&&!strcase_has(txt,"<DiskConfiguration>")
                  &&!strcase_has(txt,"<InstallTo>")&&!strcase_has(txt,"<WillWipeDisk>");
        test("windows.canonical_unattend",valid,"Single unattend in Panther, specialize/OOBE passes, no destructive disk directives");
        if(!valid)result("windows.answer_identity","FAIL","First copy the canonical Autounattend.xml to Panther");
        else {
            int equal=same_canonical_answer();
            if(equal<0)result("windows.answer_identity","NOT_PROVABLE","Original Autounattend.xml media unavailable for bytewise comparison");
            else test("windows.answer_identity",equal,"Panther XML byte-for-byte matches canonical answer media");
        }
    }
}
static int attributes_offline(Disk*d){
    GET_DISK_ATTRIBUTES a={0};DWORD got=0;
    a.Version=sizeof(a);
    if(!DeviceIoControl(d->file,IOCTL_DISK_GET_DISK_ATTRIBUTES,NULL,0,&a,sizeof(a),&got,NULL))return -1;
    return !!(a.Attributes&DISK_ATTRIBUTE_OFFLINE);
}

#include <wincrypt.h>
static int full_hash(Disk*d,char out[65]){
    HCRYPTPROV prov=0;HCRYPTHASH hash=0;
    if(!CryptAcquireContextA(&prov,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return 0;
    if(!CryptCreateHash(prov,CALG_SHA_256,0,0,&hash)){CryptReleaseContext(prov,0);return 0;}
    BYTE *buf=malloc(1048576);
    if(!buf){CryptDestroyHash(hash);CryptReleaseContext(prov,0);return 0;}
    int ok=1;
    for(uint64_t off=0;off<d->bytes;off+=1048576) {
        DWORD read=(DWORD)((d->bytes-off)<1048576?d->bytes-off:1048576);
        if(!pread_disk(d,off,buf,read)||!CryptHashData(hash,buf,read,0)){ok=0;break;}
    }
    BYTE digest[32];DWORD sz=32;
    if(ok)ok=CryptGetHashParam(hash,HP_HASHVAL,digest,&sz,0)&&sz==32;
    if(ok)for(int i=0;i<32;i++)sprintf(out+i*2,"%02x",digest[i]);
    if(ok)out[64]=0;
    free(buf);CryptDestroyHash(hash);CryptReleaseContext(prov,0);
    return ok;
}
static int is_hex_hash(const char*p){
    if(strlen(p)!=64)return 0;
    for(int i=0;i<64;i++)if(!isxdigit((unsigned char)p[i]))return 0;
    return 1;
}
static int protect_sentinel(Disk*d,uint64_t lba,const char*expected){
    if(!is_hex_hash(expected))return 0;
    char guid[64],str[256];disk_guid(d->guid,guid,sizeof(guid));
    snprintf(str,sizeof(str),"WINDOWS-BENCH-SSD1-PRESERVATION-DO-NOT-WIPE:%s",guid);
    size_t n=strlen(str);
    uint8_t raw[4096];
    if(!pread_disk(d,lba*d->sector,raw,(DWORD)d->sector))return 0;
    if(memcmp(raw,str,n))return 0;
    HCRYPTPROV prov=0;HCRYPTHASH hash=0;BYTE digest[32];DWORD sz=32;char hex[65]={0};
    if(!CryptAcquireContextA(&prov,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return 0;
    int ok=CryptCreateHash(prov,CALG_SHA_256,0,0,&hash)&&
           CryptHashData(hash,raw,(DWORD)n,0)&&CryptGetHashParam(hash,HP_HASHVAL,digest,&sz,0);
    if(ok)for(int i=0;i<32;i++)sprintf(hex+i*2,"%02x",digest[i]);
    if(hash)CryptDestroyHash(hash);
    CryptReleaseContext(prov,0);
    return ok&&!_stricmp(hex,expected);
}
static int target_booted(Disk*d){
    wchar_t path[MAX_PATH]={0};
    UINT n=GetSystemWindowsDirectoryW(path,MAX_PATH);
    if(!n||n>=MAX_PATH)return 0;
    int drive=iswalpha(path[0])?towupper(path[0])-L'A':-1;
    if(drive<0)return 0;
    wchar_t device[16];swprintf(device,16,L"\\\\.\\%c:",path[0]);
    HANDLE h=CreateFileW(device,0,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,0,NULL);
    if(h==INVALID_HANDLE_VALUE)return 0;
    uint8_t bytes[sizeof(VOLUME_DISK_EXTENTS)+sizeof(DISK_EXTENT)*8];
    DWORD got=0;int ret=0;
    if(DeviceIoControl(h,IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,NULL,0,bytes,sizeof(bytes),&got,NULL)){
        VOLUME_DISK_EXTENTS*e=(VOLUME_DISK_EXTENTS*)bytes;
        ret=(e->NumberOfDiskExtents==1&&e->Extents[0].DiskNumber==(DWORD)d->number
            &&(uint64_t)e->Extents[0].StartingOffset.QuadPart==d->parts[2].first*d->sector);
    }
    CloseHandle(h);return ret;
}
/* Queries built-in Windows utilities, never invokes a mutating command. */
static int read_only_query(wchar_t *cmd,char*out,size_t cap){
    SECURITY_ATTRIBUTES sec={sizeof(sec),NULL,TRUE};
    HANDLE rd=NULL,wr=NULL;
    if(!CreatePipe(&rd,&wr,&sec,0))return -1;
    SetHandleInformation(rd,HANDLE_FLAG_INHERIT,0);
    STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};si.cb=sizeof(si);
    si.dwFlags=STARTF_USESTDHANDLES|STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    si.hStdOutput=wr;si.hStdError=wr;si.hStdInput=GetStdHandle(STD_INPUT_HANDLE);
    if(!CreateProcessW(NULL,cmd,NULL,NULL,TRUE,CREATE_NO_WINDOW,NULL,NULL,&si,&pi)){
        CloseHandle(rd);CloseHandle(wr);return -1;
    }
    CloseHandle(wr);
    DWORD got=0;size_t used=0;
    while(used<cap-1&&ReadFile(rd,out+used,(DWORD)(cap-1-used),&got,NULL)&&got)used+=got;
    out[used]=0;CloseHandle(rd);
    WaitForSingleObject(pi.hProcess,30000);
    DWORD status=0;GetExitCodeProcess(pi.hProcess,&status);
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
    return (int)status;
}
static int same_canonical_answer(void){
    if(!vols[2].found)return -1;
    wchar_t installed[1024];
    swprintf(installed,1024,L"%lsWindows\\Panther\\Unattend.xml",vols[2].root);
    HANDLE actual=CreateFileW(installed,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,
                              NULL,OPEN_EXISTING,0,NULL);
    if(actual==INVALID_HANDLE_VALUE)return 0;
    LARGE_INTEGER sz={0};
    if(!GetFileSizeEx(actual,&sz)||sz.QuadPart<=0||sz.QuadPart>262144){
        CloseHandle(actual);return 0;
    }
    uint8_t *data=malloc((size_t)sz.QuadPart);
    DWORD n=0;
    int loaded=data&&ReadFile(actual,data,(DWORD)sz.QuadPart,&n,NULL)&&n==(DWORD)sz.QuadPart;
    CloseHandle(actual);
    if(!loaded){free(data);return 0;}
    int found=0,match=0;
    for(wchar_t drive=L'A';drive<=L'Z';drive++){
        wchar_t name[]=L"A:\\Autounattend.xml";
        name[0]=drive;
        HANDLE f=CreateFileW(name,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,
                             NULL,OPEN_EXISTING,0,NULL);
        if(f==INVALID_HANDLE_VALUE)continue;
        LARGE_INTEGER other={0};
        if(GetFileSizeEx(f,&other)&&other.QuadPart==sz.QuadPart){
            uint8_t *bytes=malloc((size_t)sz.QuadPart);
            DWORD got=0;found=1;
            if(bytes&&ReadFile(f,bytes,(DWORD)sz.QuadPart,&got,NULL)
               &&got==(DWORD)sz.QuadPart&&!memcmp(data,bytes,(size_t)sz.QuadPart))match=1;
            free(bytes);
        }
        CloseHandle(f);
        if(match)break;
    }
    free(data);
    return match?1:found?0:-1;
}

static void query_bcd(void){
    if(!vols[0].found){result("esp.bcd_semantics","NOT_PROVABLE","ESP GUID volume unavailable");return;}
    wchar_t cmd[1100];char output[32768]={0};
    swprintf(cmd,1100,L"bcdedit.exe /store \"%lsEFI\\Microsoft\\Boot\\BCD\" /enum all",vols[0].root);
    int code=read_only_query(cmd,output,sizeof(output));
    int has_loader=strcase_has(output,"winload.efi");
    int has_winpath=strcase_has(output,"\\Windows");
    test("esp.bcd_semantics",code==0&&has_loader&&has_winpath&&!strcase_has(output,"device unknown"),
         "BCDEdit parses target ESP BCD with Windows EFI loader and OS paths");
}
static void query_reagentc(void){
    char output[16000]={0};
    wchar_t cmd[]=L"reagentc.exe /info";
    int code=read_only_query(cmd,output,sizeof(output));
    test("recovery.winre_enabled",code==0&&strcase_has(output,"Windows RE status:")&&strcase_has(output,"Enabled"),
         "Booted target Windows reports Windows RE status Enabled via reagentc /info");
}

static void postboot_proof(Disk*d,Disk*protected,int phase){
    if(!phase){
        result("boot.independent","NOT_PROVABLE","Requires booting installed Windows with protected disk Offline");
        result("boot.secureboot","NOT_PROVABLE","WinPE Secure Boot describes installer, not target Windows");
        result("windows.edition_pro","NOT_PROVABLE","Verify Windows 11 Pro after first boot");
        result("recovery.winre_enabled","NOT_PROVABLE","ReAgentC activation requires booted target OS");
        return;
    }
    int source=target_booted(d);
    int offline=attributes_offline(protected);
    test("boot.independent",source&&offline==1,"Booted Windows system partition is on target, protected disk Offline");
    HKEY key=NULL;DWORD value=0,size=sizeof(value),type=0;
    LONG code=RegOpenKeyExW(HKEY_LOCAL_MACHINE,L"SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\State",0,KEY_READ,&key);
    if(code==ERROR_SUCCESS){code=RegQueryValueExW(key,L"UEFISecureBootEnabled",NULL,&type,(BYTE*)&value,&size);RegCloseKey(key);}
    test("boot.secureboot",code==ERROR_SUCCESS&&type==REG_DWORD&&value==1,"Booted Windows reports UEFI Secure Boot enabled");
    DWORD edition=0;
    BOOL yes=GetProductInfo(10,0,0,0,&edition);
    test("windows.edition_pro",yes&&edition==PRODUCT_PROFESSIONAL,"Running Windows product SKU is Professional (not N)");
    query_reagentc();
}
int main(int argc,char**argv){
    int target=-1,protected=-1,booted=0,do_hash=0;
    uint64_t sentinel_lba=0;
    const char *expected_hash=NULL,*sentinel_hash=NULL;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--target")&&i+1<argc)target=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--protected")&&i+1<argc)protected=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--phase")&&i+1<argc)booted=!strcmp(argv[++i],"booted");
        else if(!strcmp(argv[i],"--hash-protected"))do_hash=1;
        else if(!strcmp(argv[i],"--expected-protected-sha256")&&i+1<argc)expected_hash=argv[++i];
        else if(!strcmp(argv[i],"--sentinel-lba")&&i+1<argc)sentinel_lba=_strtoui64(argv[++i],NULL,10);
        else if(!strcmp(argv[i],"--sentinel-sha256")&&i+1<argc)sentinel_hash=argv[++i];
        else {fprintf(stderr,"Unknown argument: %s\n",argv[i]);return 2;}
    }
    if(target<0||protected<0||target==protected||target>128||protected>128){
        fprintf(stderr,"USAGE: winpe-audit.exe --target N --protected M [--phase winpe|booted]\n");
        fprintf(stderr,"  Optional: --sentinel-lba LBA --sentinel-sha256 HEX (VM bench)\n");
        fprintf(stderr,"  Optional: --hash-protected [--expected-protected-sha256 HEX] (full disk)\n");
        return 2;
    }
    printf("WINPE_AUDIT_VERSION 1\nPHASE %s\nTARGET %d\nPROTECTED %d\n",booted?"booted":"winpe",target,protected);
    printf("READ_ONLY True\n");
    Disk d,p;
    if(!disk_open(&d,target,"target.device")||!disk_open(&p,protected,"protected.device"))return 2;
    int target_gpt=read_gpt(&d,"target.gpt");
    int protected_gpt=read_gpt(&p,"protected.gpt");
    if(target_gpt)verify_layout(&d);
    int offline=attributes_offline(&p);
    if(!booted)test("protected.offline",offline==1,"Protected disk is Offline (DiskPart + IOCTL)");
    else result("protected.offline",offline==1?"PASS":"FAIL","Protected disk must remain Offline to prove independent boot");
    test("protected.gpt_valid",protected_gpt&&p.n>=3,"Protected disk has valid primary/backup GPT and nonempty table");
    if(sentinel_lba&&sentinel_hash&&protected_gpt)
        test("protected.sentinel_intact",protect_sentinel(&p,sentinel_lba,sentinel_hash),"Expected pre-existing bench sentinel/GPT disk GUID verified");
    else result("protected.sentinel_intact","NOT_PROVABLE","No trusted pre-install sentinel supplied");
    if(do_hash||expected_hash) {
        char got[65]={0};
        int hashed=full_hash(&p,got);
        if(hashed)printf("PROTECTED_DISK_SHA256 %s\n",got);
        if(expected_hash)test("protected.byte_preservation",hashed&&is_hex_hash(expected_hash)&&!_stricmp(expected_hash,got),"Full read-only protected-disk SHA-256 matches pre-install reference");
        else result("protected.byte_preservation",hashed?"NOT_PROVABLE":"FAIL",hashed?"Record this SHA-256 BEFORE installation and compare AFTER":"Protected disk read/hash failed");
    }else result("protected.byte_preservation","NOT_PROVABLE","Provide --expected-protected-sha256 from pre-install full disk read for proof");
    if(target_gpt&&d.n==4){verify_files(&d);postboot_proof(&d,&p,booted);}
    CloseHandle(d.file);CloseHandle(p.file);
    printf("SUMMARY PASS=%d FAIL=%d NOT_PROVABLE=%d\n",pass,fail,np);
    return fail?1:np?4:0;
}
