"""Save current VirtualBox console through SOAP, without GUI input."""
import base64
from config import Config
from vbox import VBox
cfg=Config()
box=VBox(cfg,require_machine=True)
try:
    session=box.lock("Shared")
    try:
        c=box.session_console(session)
        display=box._vals("IConsole_getDisplay",[("_this",c)])[0]
        res=box._raw("IDisplay_getScreenResolution",[("_this",display),("screenId","0")])
        w=int(res.findtext(".//width") or 0)
        h=int(res.findtext(".//height") or 0)
        scale=min(1.0, 960/max(1,w))
        w=max(1,int(w*scale)); h=max(1,int(h*scale))
        response=box._raw("IDisplay_takeScreenShotToArray",[
            ("_this",display),("screenId","0"),("width",str(w)),("height",str(h)),("bitmapFormat","PNG")])
        values=[x.text or "" for x in response.findall(".//returnval")]
        out=cfg.cache/"guest-diag"/"current"/"console.png"
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_bytes(base64.b64decode(values[0]))
        print("SCREENSHOT",out,"SIZE",w,h,"BYTES",out.stat().st_size)
    finally:
        box.unlock(session)
finally:
    box.logoff()
