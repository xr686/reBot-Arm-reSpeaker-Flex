#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sound_tracking_arm.py - Sound tracking robotic arm control program

Dual mode selection:
  Mode 1 (DOA): Sound source localization tracking + nodding greeting + breathing standby
  Mode 2 (Voice): Button triggered recording + STT/LLM/TTS + robotic arm motion control (background multi-threading to prevent blocking)

Safety policy: Strictly follow URDF physical joint limits
"""

import sys, struct, time, math, argparse, logging, signal, threading
import usb.core, usb.util, numpy as np, os, tempfile, subprocess, json
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

try:
    from reBotArm_control_py.actuator import RobotArm
    from reBotArm_control_py.controllers import ArmEndPos

    ARM_LIB_AVAILABLE = True
except ImportError:
    ARM_LIB_AVAILABLE = False

try:
    import libusb_package
except ImportError:
    libusb_package = None

try:
    import groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# ============================================================================
# Global constants
# ============================================================================

DEFAULT_VID = 0x2886
PARAMETERS = {"DOA_VALUE": (20, 18, 4, "ro", "uint16")}

# Elegant slightly bent standby posture (for when the system just starts)
DEFAULT_HOME_JQ = np.array([0.0, -0.35, -0.65, 0.0, 0.3, 0.0])

JOINT_LIMITS_MIN = np.array([-2.6, -3.6, -3.6, -1.5, -1.5, -1.5])
JOINT_LIMITS_MAX = np.array([2.6, 0.0, 0.0, 1.5, 1.5, 1.5])

NOD_CFG = {"cnt": 2, "sh_dip": -0.35, "el_bend": -0.35, "down_t": 0.7, "up_t": 0.9}

DANCE_CFG = {
    "idle_t": 1.5, "breathe_spd": 4.0,
    "sh_amp": 0.10, "el_amp": 0.15
}

# === Voice Configuration ===
VOICE_CFG = {
    "api_key": "12345678",
    "rec_dur": 5.0,  # Changed to 5 seconds to match the provided test parameters
    "rec_device": "plughw:2,0",  # Changed to reSpeaker Flex
    "proxy": None,
    "stt_model": "whisper-large-v3-turbo",
    "stt_language": "en",
    "llm_model": "llama-3.3-70b-versatile",
    "tts_enabled": True,  # Enable voice broadcast
}

LLM_PROMPT = """You are a robot arm assistant. Convert user commands to JSON.

Available actions:
- "turn_left":  turn base left by angle degrees (default 45)
- "turn_right": turn base right by angle degrees (default 45)
- "greet":      polite nod greeting
- "dance":      brief dance
- "wave":       wave hand
- "home":       return to zero position (all joints to 0 degrees)
- "stop":       stop motion

Respond ONLY in JSON format:
{"action": "<action_name>", "params": {"angle": 45}, "reply": "friendly spoken response in user's language"}

If command is unclear: {"action": "unknown", "params": {}, "reply": "Sorry, I didn't hear clearly, please say it again"}"""


@dataclass
class DOAData:
    angle: float
    speech: bool
    ts: float


class S(Enum):
    IDLE = "idle"
    TRACKING = "tracking"
    WAVING = "waving"
    DANCING = "dancing"
    VOICE = "voice"
    SHUTDOWN = "shutdown"


class Mode(Enum):
    DOA = "doa"
    VOICE = "voice"


# ============================================================================
# ReSpeaker DOA
# ============================================================================

class ReSpeaker:
    TMOUT = 100000

    def __init__(self, dev):
        self.dev = dev

    def read(self, name):
        try:
            p = PARAMETERS[name]
            r = self.dev.ctrl_transfer(
                usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
                0, 0x80 | p[1], p[0], p[2] + 1, self.TMOUT)
            return r.tolist() if p[4] in ('uint8', 'uint16') else None
        except:
            return None

    def read_doa(self):
        r = self.read("DOA_VALUE")
        if not r or len(r) < 4: return None
        a = r[1] + r[2] * 256
        return DOAData(angle=float(a), speech=(r[3] == 1), ts=time.time()) if 0 <= a <= 360 else None

    def close(self):
        try:
            usb.util.dispose_resources(self.dev)
        except:
            pass

    @classmethod
    def find(cls, vid=DEFAULT_VID, pid=None):
        f = libusb_package.find if (sys.platform.startswith('win') and libusb_package) else usb.core.find
        try:
            if pid: dev = f(idVendor=vid, idProduct=pid); return cls(dev) if dev else None
            ds = list(f(find_all=True, idVendor=vid) or [])
            return cls(sorted(ds, key=lambda d: getattr(d, 'idProduct', 0))[0]) if ds else None
        except:
            return None


# ============================================================================
# Robotic Arm Control
# ============================================================================

class ArmCtrl:
    def __init__(self, sim=False):
        self.log = logging.getLogger("ArmCtrl")
        self.sim = sim or not ARM_LIB_AVAILABLE
        self.arm = None;
        self.ctrl = None
        if not self.sim: self._init()

    def _init(self):
        try:
            self.arm = RobotArm()
            self.ctrl = ArmEndPos(self.arm)
            self.ctrl.start();
            time.sleep(1.0)
        except Exception as e:
            self.log.error(f"Robotic arm initialization failed: {e}");
            self.sim = True

    def get_q(self):
        if self.sim: return np.zeros(6)
        try:
            q, _, _ = self.arm.get_state(); return q
        except:
            return np.zeros(6)

    def move_ease(self, qt, dur):
        if self.sim: time.sleep(0.1); return True
        try:
            qc = self.get_q();
            n = min(len(qc), len(qt))
            qs = np.clip(qt[:n], JOINT_LIMITS_MIN[:n], JOINT_LIMITS_MAX[:n])
            steps = max(1, int(dur * 30.0))
            for i in range(steps):
                t = i / max(1, steps - 1)
                ease = -(math.cos(math.pi * t) - 1) / 2.0
                self.ctrl._q_target[:n] = qc[:n] + (qs - qc[:n]) * ease
                time.sleep(1.0 / 30.0)
            return True
        except Exception as e:
            self.log.error(f"Motion exception: {e}");
            return False

    def move_yaw(self, yaw):
        if self.sim: return True
        qc = self.get_q();
        qt = qc.copy()
        d = yaw - qc[0]
        while d > math.pi: d -= 2 * math.pi
        while d < -math.pi: d += 2 * math.pi
        qt[0] = np.clip(qc[0] + d, JOINT_LIMITS_MIN[0], JOINT_LIMITS_MAX[0])
        dur = max(2.0, abs(d) * 1.5)
        self.log.info(f"[Base Rotation] Target {qt[0] * 180 / math.pi:.1f}°, Duration {dur:.1f}s")
        return self.move_ease(qt, dur)

    def go_standby(self):
        q = self.get_q().copy()
        n = min(len(q), len(DEFAULT_HOME_JQ))
        q[:n] = DEFAULT_HOME_JQ[:n]
        return self.move_ease(q, 2.5)

    def go_home(self):
        q = np.zeros(6)
        return self.move_ease(q, 2.5)

    def do_nod(self):
        qb = self.get_q().copy()
        for _ in range(NOD_CFG["cnt"]):
            qd = qb.copy()
            if len(qd) > 1: qd[1] += NOD_CFG["sh_dip"]
            if len(qd) > 2: qd[2] += NOD_CFG["el_bend"]
            self.move_ease(qd, NOD_CFG["down_t"])
            self.move_ease(qb, NOD_CFG["up_t"])
        return True

    def do_wave(self):
        qb = self.get_q().copy()
        qu = qb.copy()
        if len(qu) > 1: qu[1] -= 0.5
        if len(qu) > 2: qu[2] += 0.8
        self.move_ease(qu, 1.5)
        for _ in range(2):
            ql = qu.copy()
            if len(ql) > 3: ql[3] += 0.4
            self.move_ease(ql, 0.6)
            qr = qu.copy()
            if len(qr) > 3: qr[3] -= 0.4
            self.move_ease(qr, 0.6)
        self.move_ease(qb, 1.5);
        return True

    def do_dance(self):
        qb = self.get_q().copy();
        t0 = time.time()
        while time.time() - t0 < 5.0:
            ph = 2 * math.pi * (time.time() - t0) / 2.0
            qd = qb.copy()
            if len(qd) > 1: qd[1] += math.sin(ph) * 0.15
            if len(qd) > 2: qd[2] += math.cos(ph * 1.3) * 0.10
            if len(qd) > 3: qd[3] += math.sin(ph * 0.7) * 0.2
            n = len(qd)
            try:
                self.ctrl._q_target[:n] = np.clip(qd, JOINT_LIMITS_MIN[:n], JOINT_LIMITS_MAX[:n])
            except:
                break
            time.sleep(0.05)
        self.move_ease(qb, 1.5);
        return True

    def exec_cmd(self, action, params=None):
        params = params or {}
        q = self.get_q().copy()
        if action == "turn_left":
            a = params.get("angle", 45) * math.pi / 180.0
            return self.move_yaw(q[0] + a)
        elif action == "turn_right":
            a = params.get("angle", 45) * math.pi / 180.0
            return self.move_yaw(q[0] - a)
        elif action == "greet":
            return self.do_nod()
        elif action == "dance":
            return self.do_dance()
        elif action == "wave":
            return self.do_wave()
        elif action == "home":
            return self.go_home()
        elif action == "stop":
            return True
        else:
            self.log.warning(f"Unknown action: {action}"); return False

    def stop(self):
        if not self.sim and self.ctrl:
            try:
                self.ctrl.end()
            except:
                pass


# ============================================================================
# Voice Assistant (Groq STT/LLM + Edge-TTS)
# ============================================================================

class VoiceAsst:
    def __init__(self, cfg=None):
        self.log = logging.getLogger("Voice")
        self.cfg = cfg or VOICE_CFG
        self.cli = None
        key = self.cfg.get("api_key") or os.environ.get("GROQ_API_KEY")
        if not key:
            self.log.warning("Groq API Key not set");
            return
        if not GROQ_AVAILABLE:
            self.log.warning("groq library not installed: pip install groq");
            return
        try:
            proxy = self.cfg.get("proxy")
            if proxy:
                import httpx
                http_client = httpx.Client(proxy=proxy)
                self.cli = groq.Groq(api_key=key, http_client=http_client)
            else:
                self.cli = groq.Groq(api_key=key)
            self.log.info("Groq voice assistant initialized successfully")
        except Exception as e:
            self.log.error(f"Groq initialization failed: {e}")

    @property
    def ok(self):
        return self.cli is not None

    def _try_record(self, cmd, out_path, dur, label):
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except:
                pass
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=dur + 2)
            rc = result.returncode
            exists = os.path.exists(out_path)
            size = os.path.getsize(out_path) if exists else 0
            if rc == 0 and exists and size > 44:
                return True, ""
            return False, f"rc={rc}, size={size}"
        except Exception as e:
            return False, str(e)

    def _normalize_audio(self, path):
        # Modified to support extracting the first channel from multi-channel audio (NumPy accelerated version)
        try:
            import wave
            with wave.open(path, 'rb') as wf:
                nch = wf.getnchannels()
                sw = wf.getsampwidth()
                rate = wf.getframerate()
                nframes = wf.getnframes()
                raw = wf.readframes(nframes)
            if sw != 2: return  # Only supports 16-bit

            samples = np.frombuffer(raw, dtype=np.int16)
            if nch > 1:
                # Flex records in 6 channels, extract the first channel
                samples = samples.reshape(-1, nch)
                samples = samples[:, 0]

            max_amp = np.max(np.abs(samples))
            if max_amp == 0: return

            gain = min(32767.0 / max_amp * 0.7, 10.0)
            norm = np.clip(samples * gain, -32767, 32767).astype(np.int16)

            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)  # Write back as mono for LLM recognition
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(norm.tobytes())
        except Exception as e:
            self.log.error(f"[Audio Processing] Exception: {e}")

    def record(self, out_path, dur=None):
        dur = dur or self.cfg["rec_dur"]
        device = self.cfg.get("rec_device", "plughw:2,0")

        # Switch to reSpeaker Flex recording parameters
        cmd = ["arecord", "-D", device, "-c", "6", "-r", "16000", "-f", "S16_LE", "-d", str(int(dur)), out_path]
        ok, info = self._try_record(cmd, out_path, dur, device)
        if ok:
            self._normalize_audio(out_path)
            return True

        self.log.error(f"[Recording] Failed ({info}), please check device: {device}")
        return False

    def stt(self, path):
        if not self.cli: return None
        self.log.info("[STT] Cloud recognition in progress...")
        try:
            lang = self.cfg.get("stt_language", "en")
            with open(path, "rb") as f:
                r = self.cli.audio.transcriptions.create(
                    file=f, model=self.cfg["stt_model"],
                    language=lang, response_format="text"
                )
            text = r.strip() if r else ""
            if text:
                self.log.info(f'[STT] "{text}"')
                return text
            else:
                self.log.warning("[STT] No content recognized")
                return None
        except Exception as e:
            self.log.error(f"[STT] Failed: {e}");
            return None

    def llm(self, text):
        if not self.cli: return None
        try:
            r = self.cli.chat.completions.create(
                model=self.cfg["llm_model"],
                messages=[{"role": "system", "content": LLM_PROMPT},
                          {"role": "user", "content": text}],
                temperature=0.3, max_tokens=256)

            raw = r.choices[0].message.content.strip()
            backticks = "`" * 3
            raw = raw.replace(backticks + "json", "").replace(backticks, "").strip()

            try:
                result = json.loads(raw)
                self.log.info(f"[LLM] Parsed action: {result.get('action')}")
                return result
            except:
                return {"action": "chat", "params": {}, "reply": raw}
        except Exception as e:
            self.log.error(f"[LLM] Failed: {e}");
            return None

    def speak(self, text):
        if not text: return
        print(f"\n{'=' * 55}")
        print(f" 🤖 [Voice Output] {text}")
        print(f"{'=' * 55}\n")

        if not self.cfg.get("tts_enabled", False): return

        try:
            wav_path = "/tmp/arm_reply.wav"
            mp3_path = "/tmp/arm_reply.mp3"

            # Use Chinese speaker if Chinese characters are included, otherwise use English
            lang = "zh-CN-XiaoxiaoNeural" if any('\u4e00' <= c <= '\u9fff' for c in text) else "en-US-AriaNeural"

            # Use edge-tts to generate audio and convert to aplay compatible wav using ffmpeg
            subprocess.run(["edge-tts", "--text", text, "--voice", lang, "--write-media", mp3_path], check=True)
            subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # Call flex device for playback
            subprocess.run(["aplay", "-D", "plughw:2,0", wav_path], check=True)
        except Exception as e:
            self.log.error(
                f"[TTS Failed] Unable to play voice, please ensure dependencies are installed (pip install edge-tts && sudo apt install ffmpeg). Reason: {e}")

    def cycle(self):
        if not self.ok: return None
        td = tempfile.mkdtemp(prefix="v_")
        rp = os.path.join(td, "r.wav")
        try:
            self.log.info("🔴 Recording... Please speak (5 seconds)")
            if not self.record(rp): return None
            self.log.info("🟢 Recording finished, processing...")
            text = self.stt(rp)
            if not text: return None
            result = self.llm(text)
            if not result: return None

            # Removed self.speak(reply) here, handed over to main program to execute uniformly after actions
            return result
        finally:
            import shutil
            shutil.rmtree(td, ignore_errors=True)


# ============================================================================
# Main Control Class
# ============================================================================

class SysMain:
    def __init__(self, args, mode):
        self.log = logging.getLogger("SysMain")
        self.args = args
        self.mode = mode
        self.state = S.IDLE
        self._run = False

        self.last_doa = None
        self.last_trig_t = 0.0
        self.doa_buf = []
        self.cooldown = max(3.0, args.cooldown)

        self._act_t = time.time()
        self._dancing = False
        self._dance_t0 = 0.0
        self._dance_q0 = None
        self._print_t = 0.0

        self._voice_event = threading.Event()
        self._ready_to_prompt = threading.Event()
        self._ready_to_prompt.set()

        self.mic = None
        self.arm = None
        self.voice = None

        signal.signal(signal.SIGINT, self._sig)

    def _sig(self, sn, fr):
        self.log.info("Exit signal received...")
        self._run = False
        self._ready_to_prompt.set()

    def _mark_act(self):
        self._act_t = time.time()
        self._dancing = False

    def init(self):
        self.log.info("=" * 60)
        self.log.info(
            f"Robotic arm system started [Mode: {'DOA Interaction' if self.mode == Mode.DOA else 'Voice Button Interaction'}]")
        self.log.info("=" * 60)

        self.mic = ReSpeaker.find(vid=DEFAULT_VID, pid=self.args.pid)
        if not self.mic:
            self.log.error("reSpeaker microphone array not found!")
            return False

        self.arm = ArmCtrl(sim=self.args.sim)
        self.log.info("=> Entering elegant standby posture...")
        self.arm.go_standby()

        if self.mode == Mode.VOICE:
            self.voice = VoiceAsst(VOICE_CFG)
            if not self.voice.ok:
                self.log.warning("Voice assistant initialization failed, please check API KEY")
                return False

        self._mark_act()
        self._print_t = time.time()
        return True

    def should_trigger(self, ang):
        if time.time() - self.last_trig_t < self.cooldown:
            return False
        self.doa_buf.append(ang)
        if len(self.doa_buf) < 4: return False
        self.doa_buf = self.doa_buf[-4:]
        sin_s = sum(math.sin(math.radians(a)) for a in self.doa_buf)
        cos_s = sum(math.cos(math.radians(a)) for a in self.doa_buf)
        avg = math.degrees(math.atan2(sin_s, cos_s))
        if avg < 0: avg += 360
        devs = [min(abs(a - avg), 360 - abs(a - avg)) for a in self.doa_buf]
        if devs and max(devs) < 15.0:
            self.doa_buf.clear()
            if self.last_doa is not None:
                diff = min(abs(avg - self.last_doa), 360 - abs(avg - self.last_doa))
                if diff < self.args.threshold: return False
            self.last_doa = avg
            return True
        return False

    def doa_track_and_greet(self, doa):
        if not self.should_trigger(doa.angle): return
        self._mark_act()
        self.log.info("=" * 50)
        self.log.info(f"Locked on sound source: {self.last_doa:.1f} deg")

        if self.state == S.DANCING:
            self._dancing = False
            self.log.info("Exiting breathing mode")

        yaw = -self.last_doa * math.pi / 180.0
        while yaw > math.pi: yaw -= 2.0 * math.pi
        while yaw < -math.pi: yaw += 2.0 * math.pi

        self.state = S.TRACKING
        if self.arm.move_yaw(yaw):
            time.sleep(0.5)
            self.arm.do_nod()
        self.last_trig_t = time.time()
        self.state = S.IDLE
        self._mark_act()
        self.log.info(f"Entering {self.cooldown}s cooldown...")
        self.log.info("=" * 50)

    def do_idle_dance(self, t_now):
        if t_now - self._act_t < DANCE_CFG["idle_t"]: return
        self.state = S.DANCING
        if not self._dancing:
            self._dancing = True
            self._dance_t0 = t_now
            self._dance_q0 = self.arm.get_q().copy()

        ph = 2 * math.pi * (t_now - self._dance_t0) / DANCE_CFG["breathe_spd"]
        try:
            qb = self._dance_q0.copy()
            if len(qb) > 1: qb[1] += math.sin(ph) * DANCE_CFG["sh_amp"]
            if len(qb) > 2: qb[2] -= math.sin(ph - 0.5) * DANCE_CFG["el_amp"]
            n = len(qb)
            self.arm.ctrl._q_target[:n] = np.clip(qb, JOINT_LIMITS_MIN[:n], JOINT_LIMITS_MAX[:n])
        except:
            pass

    def run_doa_mode(self):
        self.log.info("[DOA Mode] Running...")
        while self._run:
            try:
                t = time.time()
                doa = self.mic.read_doa()
                if doa and doa.speech:
                    self._mark_act()
                    self.doa_track_and_greet(doa)
                if self.state not in (S.TRACKING, S.WAVING):
                    self.do_idle_dance(t)
                time.sleep(self.args.interval)
            except Exception as e:
                self.log.error(f"Exception: {e}");
                time.sleep(1.0)

    def run_voice_mode(self):
        self.log.info("=" * 55)
        self.log.info("🎙️ [Voice Mode] Started")
        self.log.info("  - The robotic arm will maintain breathing standby in the background")
        self.log.info("  - Press the [Enter] key in the terminal to interrupt it and start recording")
        self.log.info("=" * 55)

        self.arm.do_nod()

        def input_listener():
            while self._run:
                self._ready_to_prompt.wait()
                if not self._run: break
                try:
                    input("\n[Interaction] >>> 🟢 System idle, please press Enter to start recording... <<<\n")
                    if self._run:
                        self._ready_to_prompt.clear()
                        self._voice_event.set()
                except Exception:
                    break

        threading.Thread(target=input_listener, daemon=True).start()

        while self._run:
            try:
                if self.state != S.VOICE:
                    self.do_idle_dance(time.time())

                if self._voice_event.is_set():
                    self._voice_event.clear()
                    self.state = S.VOICE

                    self.log.info("=> Pausing micro-movements, staying quiet to improve recognition rate...")
                    self.arm.move_ease(DEFAULT_HOME_JQ, 0.5)

                    result = self.voice.cycle()
                    if result:
                        action = result.get("action", "unknown")
                        params = result.get("params", {})
                        reply = result.get("reply", "")

                        # Execute robotic arm action first
                        if action not in ("unknown", "chat"):
                            self.log.info(f"=> Starting to execute action: {action}")
                            self.arm.exec_cmd(action, params)

                        # Perform voice output after all actions have completed
                        if reply:
                            self.voice.speak(reply)

                    self._mark_act()
                    self.state = S.IDLE
                    self._ready_to_prompt.set()

                time.sleep(self.args.interval)
            except Exception as e:
                self.log.error(f"Exception: {e}");
                time.sleep(1.0)

    def run(self):
        self._run = True
        if self.mode == Mode.DOA:
            self.run_doa_mode()
        else:
            self.run_voice_mode()
        self.shutdown()

    def shutdown(self):
        self.log.info("Shutting down...")
        if self.arm: self.arm.stop()
        if self.mic: self.mic.close()
        self.log.info("Exited safely.")


# ============================================================================
# Startup Menu and Entry
# ============================================================================

def select_mode() -> Mode:
    print("\n" + "=" * 50)
    print("  reBot Arm B601-DM + reSpeaker Flex")
    print("  Please select the running mode:")
    print("=" * 50)
    print("  [1] DOA Interaction Mode (Sound source tracking + Standby micro-movements)")
    print("  [2] Voice Control Mode (Button trigger + AI LLM control)")
    print("=" * 50)

    while True:
        try:
            choice = input("Please enter the mode number (1 or 2): ").strip()
            if choice == "1":
                return Mode.DOA
            elif choice == "2":
                return Mode.VOICE
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)


def parse_args():
    p = argparse.ArgumentParser(description='Sound Tracking Robotic Arm')
    p.add_argument('--interval', type=float, default=0.05)
    p.add_argument('--threshold', type=float, default=15.0)
    p.add_argument('--cooldown', type=float, default=3.0)
    p.add_argument('--pid', type=lambda x: int(x, 0), default=None)
    p.add_argument('--sim', action='store_true')
    p.add_argument('--mode', type=str, choices=['doa', 'voice'], default=None)
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

    mode = Mode.DOA if args.mode == "doa" else (Mode.VOICE if args.mode == "voice" else select_mode())

    sys_m = SysMain(args, mode)
    if sys_m.init():
        try:
            sys_m.run()
        except KeyboardInterrupt:
            pass
        finally:
            sys_m.shutdown()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()