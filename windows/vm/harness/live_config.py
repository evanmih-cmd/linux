"""One-shot supported WinGet Configuration orchestration over VBox SOAP.

Only stock Windows WinGet/DSC manifest applies configuration. Guest Properties
transport the result; no Guest Control, bench account or password is required.
"""
import base64
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from datetime import datetime,timezone
from config import Config
from vbox import VBox
from live_audit import guest_property,mount_media,type_one_command,restore_media

PREFIX="/desktopwindows/postinstall/"

def make_iso(cfg,d,runid):
    p=d/"media";p.mkdir()
    shutil.copyfile(cfg.workstation_configuration,p/"workstation.winget")
    shutil.copyfile(cfg.configuration_launcher,p/"apply-configuration.ps1")
    # Official stable DSC 3.3.0 from Microsoft, exact upstream SHA-256 pinned
    # by the common Windows launcher. No VM-specific alternate manifest.
    archive=cfg.cache/"tools"/"official-dsc"/"DSC-3.3.0-x86_64-pc-windows-msvc.zip"
    expected="3f8b27f648661903d066cc19d5a6e7a8c13bd07eb738d4d765ce7239619b8b5f"
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
        raise RuntimeError("Official DSC archive checksum mismatch")
    shutil.copyfile(archive,p/archive.name)
    shutil.copyfile(Path(__file__).with_name("guest_config_report.ps1"),p/"REPORT.PS1")
    (p/"RUN.CMD").write_bytes(("@echo off\r\n"+
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "+
        f'"%~dp0REPORT.PS1" -RunId {runid}\r\n').encode("ascii"))
    iso=d/"postinstall.iso"
    env=os.environ.copy();env["LD_LIBRARY_PATH"]=str(cfg.xorriso_lib)
    subprocess.run([str(cfg.xorriso),"-as","mkisofs","-quiet","-J","-joliet-long","-V","WINDESK",
        "-o",str(iso),str(p)],check=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return iso

def wait_log(box,runid,timeout=900):
    base=PREFIX+runid
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        state=guest_property(box,base+"/state")
        if state!=last:
            print("GUEST_CONFIG_STATE",state or "not-started",flush=True)
            last=state
        if state=="failed":
            raise RuntimeError("Guest transport failed: "+guest_property(box,base+"/error"))
        if state=="ready":
            count_s=guest_property(box,base+"/count")
            if not count_s.isdigit() or not 1<=int(count_s)<=120:
                raise RuntimeError("Invalid log chunk count")
            compressed="".join(guest_property(box,base+f"/part{i:03}") for i in range(int(count_s)))
            raw=gzip.decompress(base64.b64decode(compressed,validate=True))
            if len(raw)>524288:raise RuntimeError("Oversize log")
            if hashlib.sha256(raw).hexdigest()!=guest_property(box,base+"/sha256"):
                raise RuntimeError("Log integrity check failed")
            outcome=guest_property(box,base+"/outcome")
            if outcome not in ("PASS","FAIL"):raise RuntimeError("Invalid config outcome")
            return outcome,raw
        if box.state()!="Running":raise RuntimeError("Guest stopped during config")
        time.sleep(3)
    raise TimeoutError("Config report not returned; inspect live console or guest log")

def main():
    cfg=Config()
    if cfg.vm_name!="Desktop-Windows-11-Pro-TwoDisk":
        raise RuntimeError("Wrong VM")
    runid=secrets.token_hex(6)
    dest=cfg.cache/"postinstall-runs"/(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")+"-"+runid)
    dest.mkdir(parents=True)
    iso=make_iso(cfg,dest,runid)
    print("RUN_DIR",dest,"NONCE",runid,"MEDIA",iso,flush=True)
    box=VBox(cfg,require_machine=True)
    try:
        if box.state()!="Running":raise RuntimeError("VM not running")
        if not box.network_config()["enabled"]:raise RuntimeError("NAT disabled")
        original=mount_media(box,iso)
        completed=False
        try:
            print("MOUNTED; opening Windows Run dialog",flush=True)
            type_one_command(box,"F:\\RUN.CMD",open_run_dialog=True)
            print("COMMAND_SUBMITTED; UAC consent might be required",flush=True)
            outcome,raw=wait_log(box,runid,900)
            (dest/"configuration.log").write_bytes(raw)
            print("OUTCOME",outcome,"LOG_PATH",dest/"configuration.log",flush=True)
            print("LOG_TAIL",raw.decode("utf-8-sig",errors="replace")[-7500:],flush=True)
            completed=True
            return outcome
        finally:
            if completed:
                try:
                    restore_media(box,original)
                    print("ORIGINAL_MEDIA_RESTORED",flush=True)
                except Exception as e:
                    print("RESTORE_MEDIA_ERROR",str(e)[:230],flush=True)
            else:
                print("NONTERMINAL_GUEST: DVD LEFT ATTACHED; DO NOT RESTART OVER LIVE INSTALL",flush=True)
    finally:box.logoff()

if __name__=="__main__":
    cfg=Config()
    lock=cfg.cache/"postinstall-runs"/".controller.lock"
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open("a+") as fd:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another postinstall controller is active: refusing concurrent VM media/keyboard operations")
        result=main()
    if result!="PASS":raise SystemExit(1)
