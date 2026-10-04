import os, sys, json, time, re, wave, threading, subprocess, urllib.request, urllib.parse, zipfile, tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QIcon, QPixmap, QAction, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QSystemTrayIcon, QMenu, QDialog, QLineEdit, QPushButton, QMessageBox

import requests
import pyperclip
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from piper import PiperVoice, SynthesisConfig
from pynput import keyboard

APP = "JARVIS"
ROOT = Path(os.getenv("LOCALAPPDATA", Path.home())) / "JARVIS"
MODEL = ROOT / "models"
VOICE = MODEL / "en_US-lessac-high.onnx"
VOICE_JSON = MODEL / "en_US-lessac-high.onnx.json"
STT = MODEL / "vosk-model-small-en-us-0.15"
CONFIG = ROOT / "config.json"
TMP = ROOT / "tmp"
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx?download=true"
VOICE_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json?download=true"
STT_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

DEFAULTS = {
    "llm_endpoint": "http://localhost:11434",
    "llm_model": "qwen2.5:1.5b",
    "voice_speed": 0.90
}

def init_dirs():
    for p in (ROOT, MODEL, TMP):
        p.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")

def cfg():
    init_dirs()
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    x = DEFAULTS.copy(); x.update(d); return x

def download(url, dest):
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r, open(part, "wb") as f:
        while True:
            b = r.read(1024*1024)
            if not b: break
            f.write(b)
    part.replace(dest)

def setup_models():
    init_dirs()
    if not VOICE.exists(): download(VOICE_URL, VOICE)
    if not VOICE_JSON.exists(): download(VOICE_JSON_URL, VOICE_JSON)
    if not STT.exists():
        z = MODEL / "vosk.zip"
        if not z.exists(): download(STT_URL, z)
        with zipfile.ZipFile(z) as f: f.extractall(MODEL)
    return VOICE, STT

def open_url(url):
    import webbrowser
    if not re.match(r"^https?://", url, re.I): url = "https://" + url
    webbrowser.open(url)

def search_web(q):
    open_url("https://www.google.com/search?q=" + urllib.parse.quote_plus(q))

def likely_textbox():
    if sys.platform != "win32": return False
    try:
        import ctypes
        h = ctypes.windll.user32.GetForegroundWindow()
        b = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(h, b, 256)
        c = b.value.lower()
        return any(k in c for k in ("edit","richedit","scintilla","textbox","windowsform10","chrome_renderwidgethosthwnd"))
    except Exception:
        return False

def paste(text):
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    pyperclip.copy(text)
    if sys.platform == "win32":
        import ctypes
        U = ctypes.windll.user32
        C, V, UP = 0x11, 0x56, 0x0002
        U.keybd_event(C,0,0,0); U.keybd_event(V,0,0,0); U.keybd_event(V,0,UP,0); U.keybd_event(C,0,UP,0)
    if old is not None:
        QTimer.singleShot(400, lambda: pyperclip.copy(old))

class S(QObject):
    state = Signal(str)
    transcript = Signal(str)
    answer = Signal(str)
    show = Signal()
    hide = Signal()

class Orb(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(132,132); self.s="sleep"; self.t=0
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(30)
    def tick(self): self.t+=0.08; self.update()
    def set_state(self,s): self.s=s; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); cx=cy=66
        import math
        if self.s=="sleep": a=4+4*(.5+.5*math.sin(self.t))
        elif self.s=="speaking": a=9+6*(.5+.5*math.sin(self.t*2.5))
        else: a=7
        for r,al in ((26+a,150),(40+a*.7,95),(54+a*.4,55)):
            p.setPen(QPen(QColor(78,214,255,al),2)); p.setBrush(Qt.NoBrush); p.drawEllipse(QPoint(cx,cy),int(r),int(r))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(105,228,255,230))); p.drawEllipse(QPoint(cx,cy),14,14)
        p.setBrush(QBrush(QColor(231,253,255,230))); p.drawEllipse(QPoint(cx,cy),5,5); p.end()

class Overlay(QWidget):
    def __init__(self,s):
        super().__init__(); self.s=s
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.Tool|Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedSize(520,285)
        box=QVBoxLayout(self); box.setContentsMargins(24,18,24,18)
        title=QLabel("J A R V I S"); title.setAlignment(Qt.AlignCenter); title.setStyleSheet("color:#9cecff;letter-spacing:6px")
        title.setFont(QFont("Segoe UI",10,QFont.Bold)); box.addWidget(title)
        row=QHBoxLayout(); self.orb=Orb(); row.addWidget(self.orb,0,Qt.AlignLeft|Qt.AlignVCenter)
        rhs=QVBoxLayout(); self.status=QLabel("STANDBY"); self.status.setStyleSheet("color:#7de3ff;font-weight:bold")
        self.trans=QLabel("Hold Ctrl+Shift and speak"); self.trans.setWordWrap(True); self.trans.setStyleSheet("color:#e9fbff;font-size:15px")
        self.ans=QTextEdit(); self.ans.setReadOnly(True); self.ans.setStyleSheet("QTextEdit{background:rgba(6,15,26,210);color:#e3f8ff;border:1px solid rgba(90,220,255,90);border-radius:10px;padding:8px}")
        rhs.addWidget(self.status); rhs.addWidget(self.trans); rhs.addWidget(self.ans,1); row.addLayout(rhs,1); box.addLayout(row,1)
        hint=QLabel("Hold Ctrl+Shift to talk  •  text fields receive cleaned dictation automatically")
        hint.setAlignment(Qt.AlignCenter); hint.setStyleSheet("color:#7897a7;font-size:10px"); box.addWidget(hint)
        s.state.connect(self.state); s.transcript.connect(self.trans.setText); s.answer.connect(self.ans.setPlainText)
    def state(self,x):
        self.orb.set_state(x); self.status.setText({"sleep":"STANDBY","listen":"LISTENING","think":"THINKING","speaking":"SPEAKING"}.get(x,x.upper()))
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setBrush(QBrush(QColor(3,9,17,247))); p.setPen(QPen(QColor(82,217,255,100),1.2)); p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),18,18); p.end()
    def show_center(self):
        g=QGuiApplication.primaryScreen().availableGeometry(); self.move(g.center().x()-260,g.bottom()-355); self.show(); self.raise_(); self.activateWindow()

class TTS:
    def __init__(self,s):
        self.s=s; self.voice=None
    def say(self,text):
        threading.Thread(target=self._say,args=(text,),daemon=True).start()
    def _say(self,text):
        self.s.state.emit("speaking")
        try:
            if self.voice is None:
                v,_=setup_models(); self.voice=PiperVoice.load(str(v))
            out=TMP / ("voice_%d.wav"%int(time.time()*1000))
            with wave.open(str(out),"wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                sc=SynthesisConfig(length_scale=max(.75,min(1.18,1/cfg()["voice_speed"])))
                self.voice.synthesize_wav(text,w,syn_config=sc)
            import winsound; winsound.PlaySound(str(out),winsound.SND_FILENAME)
            out.unlink(missing_ok=True)
        except Exception:
            try:
                ps='Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate=-2; $s.Speak('+json.dumps(text)+');'
                subprocess.run(["powershell","-NoProfile","-Command",ps],check=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except Exception: pass
        self.s.state.emit("sleep")

class STT:
    def __init__(self): self.model=None
    def text(self,raw):
        try:
            if self.model is None: _,m=setup_models(); self.model=Model(str(m))
            r=KaldiRecognizer(self.model,16000)
            for i in range(0,len(raw),4000): r.AcceptWaveform(raw[i:i+4000])
            t=json.loads(r.FinalResult()).get("text","").strip()
            return t[:1].upper()+t[1:] if t else ""
        except Exception: return ""

class Recorder:
    def __init__(self,s):
        self.s=s; self.frames=[]; self.run=False; self.stream=None
    def start(self):
        if self.run: return
        self.frames=[]; self.run=True; self.s.state.emit("listen")
        self.stream=sd.RawInputStream(samplerate=16000,blocksize=8000,dtype="int16",channels=1,callback=self.cb); self.stream.start()
    def cb(self,indata,frames,t,status):
        if self.run: self.frames.append(bytes(indata))
    def stop(self):
        if not self.run: return b""
        self.run=False
        try: self.stream.stop(); self.stream.close()
        except Exception: pass
        self.s.state.emit("think"); return b"".join(self.frames)

class Brain:
    def __init__(self,s,tts): self.s=s; self.tts=tts
    def act(self,text):
        l=text.lower().strip()
        if l in ("open notepad","launch notepad"): subprocess.Popen(["notepad.exe"]); return "Notepad is open."
        if l in ("open calculator","launch calculator"): subprocess.Popen(["calc.exe"]); return "Calculator is open."
        if l in ("open file explorer","open explorer"): subprocess.Popen(["explorer.exe"]); return "File Explorer is open."
        if l in ("lock the pc","lock my pc"):
            subprocess.run(["rundll32.exe","user32.dll,LockWorkStation"],check=False); return "The PC is locked."
        if l.startswith(("open ","go to ","launch ")):
            u=re.sub(r"^(open|go to|launch)\s+","",text,flags=re.I).strip()
            if "." in u or u.startswith("www"): open_url(u); return f"Opening {u}."
        if l.startswith(("search ","search for ","google ")):
            q=re.sub(r"^(search for|search|google)\s+","",text,flags=re.I); search_web(q); return f"Searching for {q}."
        if l in ("what time is it","tell me the time"): return time.strftime("It is %I:%M %p.").lstrip("0")
        if "today" in l and "date" in l: return time.strftime("Today is %A, %d %B %Y.")
        try:
            ep=cfg()["llm_endpoint"].rstrip("/"); model=cfg()["llm_model"]
            q={"model":model,"prompt":"You are JARVIS, a concise, calm, precise Windows AI assistant. Answer naturally and do not claim actions you did not perform. User: "+text,"stream":False}
            r=requests.post(ep+"/api/generate",json=q,timeout=3)
            if r.ok:
                out=r.json().get("response","").strip()
                if out: return out
        except Exception: pass
        if any(k in l for k in ("latest","news","who is","what is","when did","where is","why is","how does")):
            search_web(text); return "I opened a current web search for that."
        return "My local language model is not connected yet. I can still control common Windows actions, search the web, open pages, and dictate text."

class Hotkey:
    def __init__(self,cb):
        self.cb=cb; self.c=False; self.sh=False; self.active=False
        self.l=keyboard.Listener(on_press=self.press,on_release=self.release); self.l.start()
    def press(self,k):
        if k in (keyboard.Key.ctrl,keyboard.Key.ctrl_l,keyboard.Key.ctrl_r): self.c=True
        if k in (keyboard.Key.shift,keyboard.Key.shift_l,keyboard.Key.shift_r): self.sh=True
        if self.c and self.sh and not self.active: self.active=True; self.cb("down")
    def release(self,k):
        if k in (keyboard.Key.ctrl,keyboard.Key.ctrl_l,keyboard.Key.ctrl_r): self.c=False
        if k in (keyboard.Key.shift,keyboard.Key.shift_l,keyboard.Key.shift_r): self.sh=False
        if self.active and not(self.c and self.sh): self.active=False; self.cb("up")

class App:
    def __init__(self):
        self.app=QApplication.instance(); self.app.setQuitOnLastWindowClosed(False); self.s=S(); self.overlay=Overlay(self.s); self.tts=TTS(self.s); self.stt=STT(); self.rec=Recorder(self.s); self.brain=Brain(self.s,self.tts)
        self.hot=Hotkey(self.hotkey); self.tray()
        self.s.show.connect(self.overlay.show_center); self.s.hide.connect(self.overlay.hide)
        self.s.state.emit("sleep")
    def hotkey(self,x):
        if x=="down":
            self.s.show.emit(); self.s.transcript.emit("Listening…"); self.s.answer.emit(""); QTimer.singleShot(0,self.rec.start)
        else:
            raw=self.rec.stop(); threading.Thread(target=self.process,args=(raw,),daemon=True).start()
    def process(self,raw):
        text=self.stt.text(raw)
        if not text: self.s.transcript.emit("I didn't catch that."); self.s.state.emit("sleep"); return
        self.s.transcript.emit(text)
        if likely_textbox():
            try: paste(text); self.s.answer.emit("Inserted the cleaned speech into the active text field."); self.tts.say("Inserted."); return
            except Exception: pass
        ans=self.brain.act(text); self.s.answer.emit(ans); self.tts.say(ans)
    def tray(self):
        px=QPixmap(64,64); px.fill(Qt.transparent); p=QPainter(px); p.setPen(Qt.NoPen); p.setBrush(QColor(83,220,255)); p.drawEllipse(8,8,48,48); p.setBrush(QColor(225,252,255)); p.drawEllipse(23,23,18,18); p.end()
        self.tr=QSystemTrayIcon(QIcon(px),self.app); self.tr.setToolTip("JARVIS")
        m=QMenu(); a=m.addAction("Show JARVIS"); a.triggered.connect(self.overlay.show_center); b=m.addAction("Test voice"); b.triggered.connect(lambda:self.tts.say("JARVIS online. Systems initialized. Standing by.")); m.addSeparator(); q=m.addAction("Exit"); q.triggered.connect(self.app.quit)
        self.tr.setContextMenu(m); self.tr.show()
    def run(self): return self.app.exec()

if __name__=="__main__":
    init_dirs(); sys.exit(App().run())
