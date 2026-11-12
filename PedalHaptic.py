# -*- coding: utf-8 -*-
"""
Pedal Haptic - ACC icin bagimsiz pedal titresim yazilimi (SimHub gerekmez)
Arduino Uno + L293D Motor Shield ile calisir. Motor 1 = FREN, Motor 2 = GAZ.
"""
import copy
import ctypes
import json
import os
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(APP_DIR, "profiller")
SETTINGS_FILE = os.path.join(APP_DIR, "ayarlar.json")
os.makedirs(PROFILE_DIR, exist_ok=True)

# ----------------------------------------------------------------------------
# Windows ayarlari (1 ms zamanlayici, shared memory erisimi)
# ----------------------------------------------------------------------------
if os.name == "nt":
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    k32.OpenFileMappingW.restype = ctypes.c_void_p
    k32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_uint32, ctypes.c_size_t]
    k32.MapViewOfFile.restype = ctypes.c_void_p
    k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
    except Exception:
        pass

F = ctypes.c_float
I = ctypes.c_int


class Physics(ctypes.Structure):
    """ACC physics sayfasi (Local\\acpmf_physics) - sadece ihtiyacimiz olan kisma kadar."""
    _pack_ = 4
    _fields_ = [
        ("packetId", I), ("gas", F), ("brake", F), ("fuel", F), ("gear", I), ("rpms", I),
        ("steerAngle", F), ("speedKmh", F), ("velocity", F * 3), ("accG", F * 3),
        ("wheelSlip", F * 4), ("wheelLoad", F * 4), ("wheelsPressure", F * 4),
        ("wheelAngularSpeed", F * 4), ("tyreWear", F * 4), ("tyreDirtyLevel", F * 4),
        ("tyreCoreTemperature", F * 4), ("camberRAD", F * 4), ("suspensionTravel", F * 4),
        ("drs", F), ("tc", F), ("heading", F), ("pitch", F), ("roll", F), ("cgHeight", F),
        ("carDamage", F * 5), ("numberOfTyresOut", I), ("pitLimiterOn", I),
        ("abs", F), ("kersCharge", F), ("kersInput", F), ("autoShifterOn", I),
        ("rideHeight", F * 2), ("turboBoost", F), ("ballast", F), ("airDensity", F),
        ("airTemp", F), ("roadTemp", F), ("localAngularVel", F * 3), ("finalFF", F),
        ("performanceMeter", F), ("engineBrake", I), ("ersRecoveryLevel", I),
        ("ersPowerLevel", I), ("ersHeatCharging", I), ("ersIsCharging", I),
        ("kersCurrentKJ", F), ("drsAvailable", I), ("drsEnabled", I),
        ("brakeTemp", F * 4), ("clutch", F), ("tyreTempI", F * 4), ("tyreTempM", F * 4),
        ("tyreTempO", F * 4), ("isAIControlled", I), ("tyreContactPoint", F * 12),
        ("tyreContactNormal", F * 12), ("tyreContactHeading", F * 12), ("brakeBias", F),
        ("localVelocity", F * 3), ("P2PActivations", I), ("P2PStatus", I),
        ("currentMaxRpm", I), ("mz", F * 4), ("fx", F * 4), ("fy", F * 4),
        ("slipRatio", F * 4), ("slipAngle", F * 4),
    ]


PHYS_SIZE = ctypes.sizeof(Physics)


class MapSource:
    """Windows paylasimli bellegini (sadece MEVCUTSA) acan taban sinif. Oyun yokken hicbir sey olusturmaz."""
    NAME = "?"
    MAP = ""
    SIZE = 0

    def __init__(self):
        self.handle = None
        self.ptr = None
        self.last_try = 0.0

    def close(self):
        if os.name != "nt":
            return
        if self.ptr:
            k32.UnmapViewOfFile(self.ptr)
        if self.handle:
            k32.CloseHandle(self.handle)
        self.ptr = None
        self.handle = None

    def _ensure(self):
        if os.name != "nt":
            return None
        if not self.ptr:
            if time.time() - self.last_try < 0.5:
                return None
            self.last_try = time.time()
            h = k32.OpenFileMappingW(0x4, False, self.MAP)
            if not h:
                return None
            p = k32.MapViewOfFile(h, 0x4, 0, 0, self.SIZE)  # SIZE=0 -> tamamini esle
            if not p:
                k32.CloseHandle(h)
                return None
            self.handle, self.ptr = h, p
        return self.ptr

    def raw(self):
        p = self._ensure()
        if p is None:
            return None
        return ctypes.string_at(p, self.SIZE)


class ACCSource(MapSource):
    NAME = "ACC"
    MAP = "Local\\acpmf_physics"
    SIZE = PHYS_SIZE

    def read(self):
        raw = self.raw()
        if raw is None:
            return None
        d = Physics.from_buffer_copy(raw)
        valid = (-0.01 <= d.gas <= 1.01) and (-0.01 <= d.brake <= 1.01) and (0 <= d.speedKmh < 600)
        return {
            "packetId": d.packetId, "gas": d.gas, "brake": d.brake, "speed": d.speedKmh,
            "abs": d.abs, "tc": d.tc, "slipRatio": list(d.slipRatio), "valid": valid,
        }


# --- LMU (rFactor 2 paylasimli bellek eklentisi yapisi, DENEYSEL) ---
D = ctypes.c_double
U8 = ctypes.c_ubyte


class RF2Wheel(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("mSuspensionDeflection", D), ("mRideHeight", D), ("mSuspForce", D), ("mBrakeTemp", D),
        ("mBrakePressure", D), ("mRotation", D), ("mLateralPatchVel", D),
        ("mLongitudinalPatchVel", D), ("mLateralGroundVel", D), ("mLongitudinalGroundVel", D),
        ("mCamber", D), ("mLateralForce", D), ("mLongitudinalForce", D), ("mTireLoad", D),
        ("mGripFract", D), ("mPressure", D), ("mTemperature", D * 3), ("mWear", D),
        ("mTerrainName", ctypes.c_char * 16), ("mSurfaceType", U8), ("mFlat", U8),
        ("mDetached", U8), ("mStaticUndeflectedRadius", U8), ("mVerticalTireDeflection", D),
        ("mWheelYLocation", D), ("mToe", D), ("mTireCarcassTemperature", D),
        ("mTireInnerLayerTemperature", D * 3), ("mExpansion", U8 * 24),
    ]


class RF2Vehicle(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("mID", I), ("mDeltaTime", D), ("mElapsedTime", D), ("mLapNumber", I), ("mLapStartET", D),
        ("mVehicleName", ctypes.c_char * 64), ("mTrackName", ctypes.c_char * 64),
        ("mPos", D * 3), ("mLocalVel", D * 3), ("mLocalAccel", D * 3), ("mOri", D * 9),
        ("mLocalRot", D * 3), ("mLocalRotAccel", D * 3), ("mGear", I), ("mEngineRPM", D),
        ("mEngineWaterTemp", D), ("mEngineOilTemp", D), ("mClutchRPM", D),
        ("mUnfilteredThrottle", D), ("mUnfilteredBrake", D), ("mUnfilteredSteering", D),
        ("mUnfilteredClutch", D), ("mFilteredThrottle", D), ("mFilteredBrake", D),
        ("mFilteredSteering", D), ("mFilteredClutch", D), ("mSteeringShaftTorque", D),
        ("mFront3rdDeflection", D), ("mRear3rdDeflection", D), ("mFrontWingHeight", D),
        ("mFrontRideHeight", D), ("mRearRideHeight", D), ("mDrag", D), ("mFrontDownforce", D),
        ("mRearDownforce", D), ("mFuel", D), ("mEngineMaxRPM", D),
        ("mScheduledStops", U8), ("mOverheating", U8), ("mDetached", U8), ("mHeadlights", U8),
        ("mDentSeverity", U8 * 8), ("mLastImpactET", D), ("mLastImpactMagnitude", D),
        ("mLastImpactPos", D * 3), ("mEngineTorque", D), ("mCurrentSector", I),
        ("mSpeedLimiter", U8), ("mMaxGears", U8), ("mFrontTireCompoundIndex", U8),
        ("mRearTireCompoundIndex", U8), ("mFuelCapacity", D),
        ("mFrontFlapActivated", U8), ("mRearFlapActivated", U8), ("mRearFlapLegalStatus", U8),
        ("mIgnitionStarter", U8), ("mFrontTireCompoundName", ctypes.c_char * 18),
        ("mRearTireCompoundName", ctypes.c_char * 18), ("mSpeedLimiterAvailable", U8),
        ("mAntiStallActivated", U8), ("mUnused", U8 * 2), ("mVisualSteeringWheelRange", F),
        ("mRearBrakeBias", D), ("mTurboBoostPressure", D), ("mPhysicsToGraphicsOffset", F * 3),
        ("mPhysicalSteeringWheelRange", F), ("mExpansion", U8 * 152), ("mWheels", RF2Wheel * 4),
    ]


class RF2Telemetry1(ctypes.Structure):
    """Baslik + ilk arac."""
    _pack_ = 4
    _fields_ = [("begin", ctypes.c_uint32), ("end", ctypes.c_uint32), ("hint", I),
                ("num", I), ("veh", RF2Vehicle)]


class LMUSource(MapSource):
    NAME = "LMU"
    MAP = "$rFactor2SMMP_Telemetry$"
    SIZE = ctypes.sizeof(RF2Telemetry1)

    def __init__(self):
        super().__init__()
        self.last = None

    def read(self):
        d = None
        for _ in range(4):  # surum sayaci ile tutarli okuma
            raw = self.raw()
            if raw is None:
                return None
            d = RF2Telemetry1.from_buffer_copy(raw)
            if d.begin == d.end:
                break
        else:
            return self.last
        empty = {"packetId": 0, "gas": 0.0, "brake": 0.0, "speed": 0.0, "abs": 0.0, "tc": 0.0,
                 "slipRatio": [0.0] * 4, "valid": True}
        if d.num <= 0:
            return empty
        v = d.veh
        v_ms = sum(x * x for x in v.mLocalVel) ** 0.5
        sr = []
        for w in v.mWheels:  # sira: SOL-ON, SAG-ON, SOL-ARKA, SAG-ARKA
            r = w.mStaticUndeflectedRadius / 100.0
            if v_ms > 3.0 and r > 0.1:
                sr.append(max(-1.5, min(1.5, (abs(w.mRotation) * r - v_ms) / v_ms)))
            else:
                sr.append(0.0)
        gas, brake = v.mUnfilteredThrottle, v.mUnfilteredBrake
        # LMU'da ABS/TC bayragi bu yapida yok: hafif kaymayi ABS/TC gibi sayiyoruz
        abs_v = max(0.0, -min(sr[0], sr[1]) - 0.10) if brake > 0.2 else 0.0
        tc_v = max(0.0, max(sr[2], sr[3]) - 0.10) if gas > 0.2 else 0.0
        valid = (-0.01 <= gas <= 1.01) and (-0.01 <= brake <= 1.01) and v_ms < 250
        self.last = {"packetId": int(v.mElapsedTime * 1000), "gas": gas, "brake": brake,
                     "speed": v_ms * 3.6, "abs": abs_v, "tc": tc_v, "slipRatio": sr,
                     "valid": valid}
        return self.last


# --- iRacing (resmi irsdk paylasimli bellegi) ---
class IRacingSource(MapSource):
    NAME = "iRacing"
    MAP = "Local\\IRSDKMemMapFileName"
    SIZE = 0
    NEEDED = ("Throttle", "Brake", "Speed", "BrakeABSactive", "LFspeed", "RFspeed", "LRspeed", "RRspeed")

    def __init__(self):
        super().__init__()
        self.vars = None
        self.vars_key = None
        self.last = None

    def close(self):
        super().close()
        self.vars = None

    def _parse_vars(self, p, num, off):
        raw = ctypes.string_at(p + off, num * 144)
        out = {}
        for i in range(num):
            vtype, voff, _cnt = struct.unpack_from("<3i", raw, i * 144)
            name = raw[i * 144 + 16:i * 144 + 48].split(b"\0", 1)[0].decode("ascii", "ignore")
            if name in self.NEEDED:
                out[name] = (vtype, voff)
        return out

    def read(self):
        p = self._ensure()
        if p is None:
            return None
        empty = {"packetId": 0, "gas": 0.0, "brake": 0.0, "speed": 0.0, "abs": 0.0, "tc": 0.0,
                 "slipRatio": [0.0] * 4, "valid": True}
        for _ in range(4):
            h = ctypes.string_at(p, 112)
            (_ver, status, _tr, _siu, _sil, _sio, num, voff, nbuf, blen) = struct.unpack_from("<10i", h, 0)
            if not (status & 1) or nbuf < 1 or nbuf > 4 or num <= 0 or blen <= 0:
                return empty
            bufs = [struct.unpack_from("<4i", h, 48 + 16 * i) for i in range(nbuf)]
            tick, boff = max((b[0], b[1]) for b in bufs)
            key = (num, voff)
            if self.vars is None or self.vars_key != key:
                self.vars = self._parse_vars(p, num, voff)
                self.vars_key = key
            data = ctypes.string_at(p + boff, blen)
            h2 = ctypes.string_at(p, 112)
            if max((struct.unpack_from("<4i", h2, 48 + 16 * i)[0]) for i in range(nbuf)) == tick:
                break
        else:
            return self.last

        def val(name, fmt, default=0.0):
            v = self.vars.get(name)
            if not v:
                return default
            return struct.unpack_from(fmt, data, v[1])[0]

        speed = val("Speed", "<f")
        gas = val("Throttle", "<f")
        brake = val("Brake", "<f")
        absa = 1.0 if val("BrakeABSactive", "<?", False) else 0.0
        ws = [val("LFspeed", "<f"), val("RFspeed", "<f"), val("LRspeed", "<f"), val("RRspeed", "<f")]
        have_ws = all(n in self.vars for n in ("LFspeed", "RFspeed", "LRspeed", "RRspeed"))
        if have_ws and speed > 3.0:
            sr = [max(-1.5, min(1.5, (abs(w) - speed) / speed)) for w in ws]
        else:
            sr = [0.0] * 4
        tc_v = max(0.0, max(sr[2], sr[3]) - 0.10) if gas > 0.2 else 0.0  # iRacing'de TC bayragi yok
        valid = ("Throttle" in self.vars and "Brake" in self.vars and "Speed" in self.vars
                 and -0.01 <= gas <= 1.01 and -0.01 <= brake <= 1.01 and speed < 250)
        self.last = {"packetId": tick, "gas": gas, "brake": brake, "speed": speed * 3.6,
                     "abs": absa, "tc": tc_v, "slipRatio": sr, "valid": valid}
        return self.last


SOURCES = {"ACC": ACCSource, "LMU": LMUSource, "iRacing": IRacingSource}


# ----------------------------------------------------------------------------
# Efekt ayarlari
# ----------------------------------------------------------------------------
EFFECTS = {
    "abs":  {"name": "ABS (fren)",          "motor": 0},
    "lock": {"name": "Tekerlek kilitlenme (fren)", "motor": 0},
    "tc":   {"name": "Traction Control (gaz)", "motor": 1},
    "slip": {"name": "Kayma (gaz)",       "motor": 1},
}

DEFAULTS = {
    "abs":  {"enabled": True, "intensity": 80, "freq": 12, "thr": 0.01, "hold": 60},
    "lock": {"enabled": True, "intensity": 90, "freq": 0,  "thr": 0.25, "hold": 50},
    "tc":   {"enabled": True, "intensity": 70, "freq": 10, "thr": 0.01, "hold": 60},
    "slip": {"enabled": True, "intensity": 60, "freq": 0,  "thr": 0.25, "hold": 50},
}


class Engine(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.src = ACCSource()
        self.pending_source = None
        self.ser = None
        self.ready_at = 0.0
        self.wlock = threading.Lock()
        self.running = True
        self.snap = {}
        self.test = None
        self.latency = None
        self.lat_max = 0.0
        self.ping_t = 0.0
        self.ping_sent = 0.0
        self.state = {k: (0.0, 0.0) for k in EFFECTS}
        self.active = {k: False for k in EFFECTS}
        self.last_cmd = [(-1, -1), (-1, -1)]
        self.last_send = [0.0, 0.0]
        self.last_pid = None
        self.last_change = time.perf_counter()
        self.error = ""
        self.hz = 0.0

    # --- seri port ---
    def connect(self, port):
        self.disconnect()
        ser = serial.Serial(port, 115200, timeout=0.05, write_timeout=0.1)
        self.ser = ser
        self.ready_at = time.time() + 2.0  # Arduino baglaninca yeniden baslar
        self.latency = None
        self.lat_max = 0.0
        self.last_cmd = [(-1, -1), (-1, -1)]
        threading.Thread(target=self._reader, args=(ser,), daemon=True).start()

    def disconnect(self):
        ser, self.ser = self.ser, None
        if ser:
            try:
                ser.write(b"M1,0,0\nM2,0,0\n")
                ser.close()
            except Exception:
                pass

    def _reader(self, ser):
        while self.running and ser is self.ser:
            try:
                line = ser.readline()
            except Exception:
                break
            if line.strip() == b"P" and self.ping_t:
                ms = (time.perf_counter() - self.ping_t) * 1000.0 / 2.0
                self.latency = ms if self.latency is None else 0.8 * self.latency + 0.2 * ms
                self.lat_max = max(self.lat_max, ms)

    def send(self, out, now):
        ser = self.ser
        if not ser or time.time() < self.ready_at:
            return
        try:
            with self.wlock:
                for m in (0, 1):
                    if out[m] != self.last_cmd[m] or now - self.last_send[m] > 0.05:
                        ser.write(("M%d,%d,%d\n" % (m + 1, out[m][0], out[m][1])).encode())
                        self.last_cmd[m] = out[m]
                        self.last_send[m] = now
                if now - self.ping_sent > 1.0:
                    self.ping_t = time.perf_counter()
                    ser.write(b"P\n")
                    self.ping_sent = now
        except Exception as e:
            self.error = "Seri port hatasi: %s" % e
            self.ser = None

    # --- efekt hesabi ---
    def compute(self, t, now):
        c = self.cfg
        trig = {k: 0.0 for k in EFFECTS}
        if t:
            if t["abs"] > c["abs"]["thr"]:
                trig["abs"] = 1.0
            if t["tc"] > c["tc"]["thr"]:
                trig["tc"] = 1.0
            sr = t["slipRatio"]
            if t["brake"] > 0.1 and t["speed"] > 20:
                v = -min(sr[0], sr[1])
                thr = c["lock"]["thr"]
                if v > thr:
                    trig["lock"] = 0.5 + 0.5 * min(1.0, (v - thr) / 0.5)
            if t["gas"] > 0.2 and t["speed"] > 3:
                v = max(sr[2], sr[3])
                thr = c["slip"]["thr"]
                if v > thr:
                    trig["slip"] = 0.5 + 0.5 * min(1.0, (v - thr) / 0.5)

        test = self.test
        for k in EFFECTS:
            ck = c[k]
            en = ck["enabled"]
            if test and test[0] == k and now < test[1]:
                trig[k] = 1.0
                en = True
            sev, until = self.state[k]
            if en and trig[k] > 0:
                sev, until = trig[k], now + ck["hold"] / 1000.0
            self.state[k] = (sev, until)
            self.active[k] = en and now < until

        out = [(0, 0), (0, 0)]
        for k, info in EFFECTS.items():
            if self.active[k]:
                m = info["motor"]
                inten = int(255 * min(100, c[k]["intensity"]) / 100.0 * self.state[k][0])
                if inten > out[m][0]:
                    out[m] = (inten, int(c[k]["freq"]))
        return out

    def run(self):
        loops, t0 = 0, time.perf_counter()
        while self.running:
            now = time.perf_counter()
            if self.pending_source:
                self.src.close()
                self.src = SOURCES[self.pending_source]()
                self.pending_source = None
                self.last_pid = None
                self.last_change = now
            t = self.src.read()
            live = False
            if t:
                if t["packetId"] != self.last_pid:
                    self.last_pid = t["packetId"]
                    self.last_change = now
                age = now - self.last_change
                live = age < 0.5 and t["valid"]
                if age > 2.0:
                    self.src.close()
                    self.last_change = now
            if not live:
                for k in EFFECTS:
                    self.state[k] = (0.0, 0.0)
            out = self.compute(t if live else None, now)
            self.snap = {"t": t, "live": live, "out": out, "active": dict(self.active),
                         "valid": (t["valid"] if t else True)}
            self.send(out, now)
            loops += 1
            if now - t0 >= 1.0:
                self.hz = loops / (now - t0)
                loops, t0 = 0, now
            time.sleep(0.002)
        self.disconnect()


# ----------------------------------------------------------------------------
# Arayuz
# ----------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Pedal Haptic")
        self.cfg = copy.deepcopy(DEFAULTS)
        self.vars = {}
        self.engine = Engine(self.cfg)
        self.build_ui()
        self.load_settings()
        self.engine.start()
        self.refresh_ports()
        self.tick()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- kurulum ---
    def build_ui(self):
        r = self.root
        top = ttk.LabelFrame(r, text="Arduino baglantisi")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=28, state="readonly")
        self.port_box.grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(top, text="Yenile", command=self.refresh_ports).grid(row=0, column=1, padx=2)
        self.conn_btn = ttk.Button(top, text="Baglan", command=self.toggle_conn)
        self.conn_btn.grid(row=0, column=2, padx=2)
        self.conn_lbl = ttk.Label(top, text="Bagli degil", foreground="gray")
        self.conn_lbl.grid(row=0, column=3, padx=8)
        self.lat_lbl = ttk.Label(top, text="Gecikme: -")
        self.lat_lbl.grid(row=0, column=4, padx=8)

        gf = ttk.LabelFrame(r, text="Oyun")
        gf.grid(row=0, column=2, sticky="ns", padx=6, pady=4)
        self.src_var = tk.StringVar(value="ACC")
        for name in ("ACC", "LMU", "iRacing"):
            ttk.Radiobutton(gf, text=name, value=name, variable=self.src_var, style="Toolbutton",
                            width=8, command=self.change_source).pack(side="left", padx=4, pady=4)

        tel = ttk.LabelFrame(r, text="Canli telemetri")
        tel.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        self.game_lbl = ttk.Label(tel, text="Bekleniyor...")
        self.game_lbl.grid(row=0, column=0, columnspan=4, sticky="w", padx=4)
        self.bars = {}
        for i, (key, text) in enumerate([("gas", "Gaz"), ("brake", "Fren"),
                                         ("abs", "ABS"), ("tc", "TC")]):
            ttk.Label(tel, text=text, width=6).grid(row=1 + i, column=0, sticky="w", padx=4)
            pb = ttk.Progressbar(tel, maximum=100, length=220)
            pb.grid(row=1 + i, column=1, padx=4, pady=1)
            self.bars[key] = pb
        self.val_lbl = ttk.Label(tel, text="", justify="left")
        self.val_lbl.grid(row=1, column=2, rowspan=4, padx=14, sticky="w")
        self.ind = {}
        indf = ttk.Frame(tel)
        indf.grid(row=1, column=3, rowspan=4, padx=8)
        for k, info in EFFECTS.items():
            lb = tk.Label(indf, text=info["name"], width=26, bg="#dddddd", anchor="w")
            lb.pack(pady=1)
            self.ind[k] = lb

        for i, (k, info) in enumerate(EFFECTS.items()):
            self.build_effect(k, info, 2 + i // 2, i % 2)

        pf = ttk.LabelFrame(r, text="Profiller")
        pf.grid(row=4, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        self.prof_var = tk.StringVar()
        self.prof_box = ttk.Combobox(pf, textvariable=self.prof_var, width=24)
        self.prof_box.grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(pf, text="Kaydet", command=self.save_profile).grid(row=0, column=1, padx=2)
        ttk.Button(pf, text="Yukle", command=self.load_profile).grid(row=0, column=2, padx=2)
        ttk.Button(pf, text="Varsayilana don", command=self.reset_defaults).grid(row=0, column=3, padx=2)
        self.refresh_profiles()

    def build_effect(self, key, info, row, col):
        f = ttk.LabelFrame(self.root, text=info["name"])
        f.grid(row=row, column=col, sticky="nsew", padx=6, pady=4)
        d = DEFAULTS[key]
        v = {
            "enabled": tk.BooleanVar(value=d["enabled"]),
            "intensity": tk.DoubleVar(value=d["intensity"]),
            "freq": tk.DoubleVar(value=d["freq"]),
            "thr": tk.DoubleVar(value=d["thr"]),
            "hold": tk.DoubleVar(value=d["hold"]),
        }
        self.vars[key] = v
        ttk.Checkbutton(f, text="Acik", variable=v["enabled"]).grid(row=0, column=0, sticky="w")
        ttk.Button(f, text="Test (1 sn)", command=lambda k=key: self.test_effect(k)).grid(row=0, column=1)
        self.slider(f, 1, "Siddet %", v["intensity"], 0, 100, "{:.0f}")
        self.slider(f, 2, "Frekans Hz (0=surekli)", v["freq"], 0, 60, "{:.0f}")
        self.slider(f, 3, "Esik", v["thr"], 0.0, 1.0, "{:.2f}")
        self.slider(f, 4, "Tutma ms", v["hold"], 0, 300, "{:.0f}")

    def slider(self, parent, row, text, var, lo, hi, fmt):
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=4)
        val = ttk.Label(parent, width=6)

        def upd(*_):
            val.config(text=fmt.format(var.get()))
        ttk.Scale(parent, from_=lo, to=hi, variable=var, length=160,
                  command=lambda _v: upd()).grid(row=row, column=1, padx=2)
        val.grid(row=row, column=2)
        var.trace_add("write", upd)
        upd()

    # --- baglanti ---
    def refresh_ports(self):
        ports = list(serial.tools.list_ports.comports())
        names = ["%s - %s" % (p.device, p.description) for p in ports]
        self.port_box["values"] = names
        for n in names:
            if "arduino" in n.lower() or "ch340" in n.lower():
                self.port_var.set(n)
                return
        if names and not self.port_var.get():
            self.port_var.set(names[0])

    def toggle_conn(self):
        if self.engine.ser:
            self.engine.disconnect()
            self.conn_btn.config(text="Baglan")
            return
        sel = self.port_var.get()
        if not sel:
            messagebox.showinfo("Pedal Haptic", "Once bir port sec.")
            return
        try:
            self.engine.connect(sel.split(" ")[0])
            self.conn_btn.config(text="Kes")
        except Exception as e:
            messagebox.showerror("Pedal Haptic", "Baglanilamadi:\n%s\n\nSimHub ya da Arduino IDE "
                                 "Serial Monitor aciksa kapat." % e)

    def change_source(self):
        self.engine.pending_source = self.src_var.get()

    def test_effect(self, key):
        self.engine.test = (key, time.perf_counter() + 1.0)

    # --- ayar kaydi ---
    def sync_cfg(self):
        for k, v in self.vars.items():
            for f, var in v.items():
                self.cfg[k][f] = var.get()

    def apply_cfg(self, data):
        for k in EFFECTS:
            for f in DEFAULTS[k]:
                try:
                    self.vars[k][f].set(data[k][f])
                except Exception:
                    pass

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.apply_cfg(data)
            if data.get("_source") in SOURCES:
                self.src_var.set(data["_source"])
                self.engine.pending_source = data["_source"]
        except Exception:
            pass

    def save_settings(self):
        self.sync_cfg()
        try:
            data = dict(self.cfg)
            data["_source"] = self.src_var.get()
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception:
            pass

    def refresh_profiles(self):
        names = [f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")]
        self.prof_box["values"] = sorted(names)

    def save_profile(self):
        name = self.prof_var.get().strip()
        if not name:
            messagebox.showinfo("Pedal Haptic", "Profil adi yaz.")
            return
        self.sync_cfg()
        safe = "".join(ch for ch in name if ch.isalnum() or ch in " -_")
        with open(os.path.join(PROFILE_DIR, safe + ".json"), "w", encoding="utf-8") as fh:
            json.dump(self.cfg, fh, indent=2)
        self.refresh_profiles()

    def load_profile(self):
        name = self.prof_var.get().strip()
        try:
            with open(os.path.join(PROFILE_DIR, name + ".json"), "r", encoding="utf-8") as fh:
                self.apply_cfg(json.load(fh))
        except Exception:
            messagebox.showinfo("Pedal Haptic", "Profil bulunamadi.")

    def reset_defaults(self):
        self.apply_cfg(DEFAULTS)

    # --- canli guncelleme ---
    def tick(self):
        self.sync_cfg()
        e = self.engine
        s = e.snap
        t = s.get("t") if s else None

        if e.error:
            messagebox.showwarning("Pedal Haptic", e.error)
            e.error = ""
            self.conn_btn.config(text="Baglan")
        if e.ser:
            if time.time() < e.ready_at:
                self.conn_lbl.config(text="Arduino hazirlaniyor...", foreground="orange")
            else:
                self.conn_lbl.config(text="Bagli", foreground="green")
        else:
            self.conn_lbl.config(text="Bagli degil", foreground="gray")
            self.conn_btn.config(text="Baglan")

        if e.latency is not None:
            self.lat_lbl.config(text="Seri gecikme: %.1f ms (maks %.1f) | dongu: %d Hz"
                                % (e.latency, e.lat_max, e.hz))
        else:
            self.lat_lbl.config(text="Gecikme: - | dongu: %d Hz" % e.hz)

        g = e.src.NAME
        if not t:
            hint = " (rF2 eklentisi acik mi?)" if g == "LMU" else " (oyunu baslat, pistte ol)"
            self.game_lbl.config(text="%s: veri kaynagi bulunamadi%s" % (g, hint))
        elif not s.get("valid", True):
            self.game_lbl.config(text="%s: veri yapisi uyusmuyor!" % g)
        elif not s.get("live"):
            self.game_lbl.config(text="%s: bagli, veri akmiyor (pist/pause?)" % g)
        else:
            self.game_lbl.config(text="%s: canli veri" % g)

        if t and s.get("live"):
            self.bars["gas"]["value"] = t["gas"] * 100
            self.bars["brake"]["value"] = t["brake"] * 100
            self.bars["abs"]["value"] = min(1, t["abs"]) * 100
            self.bars["tc"]["value"] = min(1, t["tc"]) * 100
            sr = t["slipRatio"]
            self.val_lbl.config(text=(
                "Hiz: %.0f km/h\nKilit (on): %.2f\nKayma (arka): %.2f\n"
                "ABS: %.2f  TC: %.2f" % (t["speed"], -min(sr[0], sr[1]), max(sr[2], sr[3]),
                                         t["abs"], t["tc"])))
        else:
            for b in self.bars.values():
                b["value"] = 0
            self.val_lbl.config(text="")
        act = s.get("active", {}) if s else {}
        for k, lb in self.ind.items():
            lb.config(bg="#ffb300" if act.get(k) else "#dddddd")
        self.root.after(40, self.tick)

    def on_close(self):
        self.save_settings()
        self.engine.running = False
        time.sleep(0.05)
        self.engine.disconnect()
        self.engine.src.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
