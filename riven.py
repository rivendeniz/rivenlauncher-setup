#!/usr/bin/env python3
"""Riven Launcher: instance'lı, Modrinth entegrasyonlu Minecraft (Fabric) launcher.

Mimari: Python arka uç + HTML arayüz. Arayüz yalnızca 127.0.0.1 üzerindeki yerel
sunucudan servis edilir ve kendi uygulama penceresinde (pywebview) açılır;
pywebview yoksa Edge/Chrome "uygulama modu"na düşer.

Dış bağlantılar (başka hiçbir yere bağlanmaz):
  - Mojang / Fabric          : sürüm, kütüphane, asset indirme
  - bmclapi2.bangbang93.com / optifine.net : yalnızca 1.14 öncesi sürümlerde OptiFine indirme
  - api.modrinth.com / cdn.modrinth.com : mod arama ve indirme (SHA-512 doğrulamalı)
  - api.curseforge.com / *.forgecdn.net : yalnızca CurseForge API anahtarı girersen (SHA-1 doğrulamalı)
  - Microsoft / Xbox / Minecraft Services : yalnızca Microsoft ile giriş yaparsan
Token'lar düz dosyaya yazılmaz; refresh token sistem kimlik deposunda (keyring) durur.
"""
import base64
import ctypes
import hashlib
import inspect
import json
import os
import random
import re
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import minecraft_launcher_lib as mll
except ImportError:
    sys.exit("Eksik paket. Çalıştır:  python -m pip install -r requirements.txt")

try:
    import keyring
except ImportError:  # keyring yoksa Microsoft oturumu hatırlanmaz
    keyring = None

APP = "Riven Launcher"
APP_VERSION = "1.3.2"
# Otomatik güncelleme: GitHub "kullanici/depo" adını yaz (ör. "riven/RivenLauncher").
# Boş bırakırsan otomatik güncelleme kapalı kalır. Depo herkese açık (public) olmalı.
UPDATE_REPO = "rivendeniz/rivenlauncher-setup"
UPDATE_ASSET_SUFFIX = "Setup.exe"
DEFAULT_VERSION = "1.21.11"
HOME_DIR = Path.home() / ".riven"
INSTANCES_DIR = HOME_DIR / "instances"
CONFIG_FILE = HOME_DIR / "config.json"
INSTANCES_FILE = HOME_DIR / "instances.json"
# PyInstaller exe'sinde dosyalar geçici klasöre (_MEIPASS) açılır
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB_DIR = BASE_DIR / "web"
SHARED_DIR = str(mll.utils.get_minecraft_directory())  # kütüphaneler/asset'ler ortak
RIVEN_MODS_DIR = BASE_DIR / "mods"  # launcher ile gelen gömülü modlar (örn. riventag)
RIVEN_MOD_PREFIX = "riventag-"  # bu önekle başlayan dosyalar kullanıcı mod listesinde gösterilmez
ICON_KEYS = ("diamond", "star", "heart", "sword", "shield", "skull", "potion",
             "chest", "bolt", "compass", "pickaxe", "anvil")
MAX_ICON_BYTES = 1_500_000
REDIRECT_URI = "http://localhost"
MS_AUTH = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
# Mojang onayı gelen Azure Client ID'ni buraya yazarsan arayüz hiç ID sormaz (arkadaşların için ideal).
DEFAULT_CLIENT_ID = ""
KEYRING_SERVICE = "RivenLauncher"
KEYRING_USER = "microsoft_refresh_token"
MODRINTH = "https://api.modrinth.com/v2"
UA = f"RivenLauncher/{APP_VERSION} (kisisel kullanim)"
IDLE_TIMEOUT = 120      # sn: pencere kapandıktan sonra sunucu kapanır
MAX_DOWNLOAD = 300 * 1024 * 1024
# Daha az GC duraklaması, daha hızlı açılış/oyun (Java 8-21 ile uyumlu, güvenli bayraklar)
JVM_FAST_FLAGS = ["-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions", "-XX:G1NewSizePercent=20",
                  "-XX:G1ReservePercent=20", "-XX:MaxGCPauseMillis=50", "-XX:G1HeapRegionSize=16M",
                  "-XX:+DisableExplicitGC", "-XX:+ParallelRefProcEnabled", "-Xshare:auto"]
TOKEN_FRESH_SECONDS = 6 * 3600   # Minecraft erişim token'ı ~24 saat geçerli
MAX_PACK_UNPACKED = 2 * 1024 * 1024 * 1024   # bir modpack'in açılmış toplam boyut sınırı
# Çalıştırılabilir dosyalar modpack içinden asla yazılmaz (mod .jar'ları normal akıştır)
BLOCKED_EXT = (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".msi", ".lnk", ".com", ".jse", ".wsf")

# Modrinth proje türü -> instance klasörü
PTYPES = {
    "mod": {"key": "mods", "dir": "mods", "ext": (".jar",)},
    "resourcepack": {"key": "resourcepacks", "dir": "resourcepacks", "ext": (".zip",)},
    "shader": {"key": "shaders", "dir": "shaderpacks", "ext": (".zip",)},
}
CTYPES = {v["key"]: (k, v) for k, v in PTYPES.items()}  # "mods" -> ("mod", {...})

DATA_LOCK = threading.RLock()
INSTALL_LOCK = threading.Lock()
LAUNCH_LOCK = threading.Lock()

CFG = {}
ACCOUNT = {"data": None, "t": 0.0}       # Microsoft oturumu: {"name","id","access_token","refresh_token"}
LOGIN = {}                     # bekleyen giriş: state / verifier
PROG = {"status": "Hazır", "value": 0, "max": 1}
PREPARING = {"id": None}
RUNNING = {}                   # instance_id -> Popen
RUN_STARTED = {}               # instance_id -> başlangıç zamanı (Discord için)
LAUNCHER_STARTED = time.time()
LOGS = deque(maxlen=3000)
LOG_STATE = {"idx": 0}
LOG_LOCK = threading.Lock()
PING = {"last": time.time(), "bye": None}
SERVER = {"port": 0, "token": secrets.token_urlsafe(24), "httpd": None}
VERSIONS_CACHE = {"t": 0.0, "v": []}
DEVICE = {"id": None, "status": "idle", "message": "", "uri": ""}


# ------------------------------------------------------------------ yardımcılar
class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg, self.code = msg, code


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def add_log(text):
    with LOG_LOCK:
        LOG_STATE["idx"] += 1
        LOGS.append({"i": LOG_STATE["idx"], "t": str(text).rstrip("\n")})


def call_compat(func, **candidates):
    """Kütüphane sürümleri arasındaki imza farklarını tolere et."""
    params = inspect.signature(func).parameters
    return func(**{k: v for k, v in candidates.items() if k in params})


def offline_uuid(name):
    digest = hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def clean_text(value, maxlen, field="Değer"):
    value = str(value or "").strip()
    if not value or len(value) > maxlen:
        raise ApiError(f"{field} 1-{maxlen} karakter olmalı.")
    return value


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{10}", value):
        raise ApiError("Geçersiz instance.", 404)
    return value


def safe_filename(name, exts):
    name = str(name or "")
    ok = (Path(name).name == name and ".." not in name
          and re.fullmatch(r"[\w\-. +()\[\]]{1,150}", name) is not None
          and name.lower().endswith(exts))
    if not ok:
        raise ApiError("Geçersiz dosya adı.")
    return name


def loose_filename(name, exts):
    """Yalnızca okuma için: klasör dışına çıkmayan her dosya adı (özel karakterli adlar dahil)."""
    name = str(name or "")
    if not (name and Path(name).name == name and ".." not in name and "\x00" not in name
            and name.lower().endswith(exts)):
        raise ApiError("Geçersiz dosya adı.")
    return name


def save_cfg():
    with DATA_LOCK:
        write_json(CONFIG_FILE, CFG)


def migrate_old_config():
    """Eski MiniLauncher ayarlarından yalnızca ad ve client id'yi al."""
    old = read_json(Path.home() / ".mini_launcher" / "config.json", {})
    for key in ("client_id", "offline_name"):
        if old.get(key) and not CFG.get(key):
            CFG[key] = old[key]


# -------------------------------------------------------------------- instance'lar
def load_instances():
    return read_json(INSTANCES_FILE, [])


def get_instance(iid):
    for inst in load_instances():
        if inst["id"] == iid:
            return inst
    raise ApiError("Instance bulunamadı.", 404)


def instance_dir(inst):
    return INSTANCES_DIR / inst["id"]


def content_dir(inst, ctype):
    if ctype not in CTYPES:
        raise ApiError("Geçersiz içerik türü.")
    return instance_dir(inst) / CTYPES[ctype][1]["dir"]


def index_path(inst):
    return instance_dir(inst) / "riven_index.json"


def load_index(inst):
    return read_json(index_path(inst), {})


LOCAL_META = {}   # (yol, mtime, boyut) -> dosyanın kendi içindeki bilgiler


def _plain_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("text") or "") + "".join(_plain_text(x) for x in v.get("extra") or [])
    if isinstance(v, list):
        return "".join(_plain_text(x) for x in v)
    return ""


def local_meta(path, ctype):
    """Mod (fabric.mod.json) / resource pack / shader (pack.mcmeta, pack.png) dosyasının içinden bilgi okur."""
    try:
        st = path.stat()
    except OSError:
        return {}
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in LOCAL_META:
        return LOCAL_META[key]
    out = {}
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if ctype == "mods":
                if "fabric.mod.json" in names:
                    raw = zf.read("fabric.mod.json").decode("utf-8-sig", "replace")
                    try:
                        data = json.loads(raw, strict=False)
                    except ValueError:
                        data = {}
                    authors = []
                    for a in data.get("authors") or []:
                        authors.append(a.get("name") if isinstance(a, dict) else str(a))
                    contact = data.get("contact") or {}
                    ic = data.get("icon")
                    if isinstance(ic, dict) and ic:
                        ic = ic[max(ic, key=lambda k: int(k) if str(k).isdigit() else 0)]
                    ic = str(ic or "").lstrip("/")
                    out = {"title": data.get("name") or data.get("id"), "version": data.get("version"),
                           "description": _plain_text(data.get("description")),
                           "authors": [a for a in authors if a][:6],
                           "homepage": contact.get("homepage") if isinstance(contact.get("homepage"), str) else None,
                           "sources": contact.get("sources") if isinstance(contact.get("sources"), str) else None,
                           "icon_member": ic if ic in names else None}
            else:
                desc = ""
                if "pack.mcmeta" in names:
                    try:
                        desc = _plain_text((json.loads(zf.read("pack.mcmeta").decode("utf-8-sig", "replace"),
                                                       strict=False).get("pack") or {}).get("description"))
                    except ValueError:
                        pass
                out = {"description": re.sub(r"§.", "", desc),
                       "icon_member": "pack.png" if "pack.png" in names else None}
    except Exception:
        out = {}
    if len(LOCAL_META) > 4000:
        LOCAL_META.clear()
    LOCAL_META[key] = out
    return out


def content_file(inst, ctype, fname):
    folder = content_dir(inst, ctype)
    for cand in (folder / fname, folder / (fname + ".disabled")):
        if cand.is_file():
            return cand
    return None


IDENT_TRIED = set()


def mr_post_json(url, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"User-Agent": UA, "Accept": "application/json",
                                          "Content-Type": "application/json"})
    try:
        with open_url(req, timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise ApiError(f"Modrinth hatası ({exc.code}).", 502)
    except Exception as exc:
        raise ApiError(f"Modrinth'e ulaşılamadı: {explain_net_error(exc)}", 502)


def identify_unindexed(inst, ctypes=None):
    """Dizinde kaydı olmayan dosyaları (modpack ile gelen, elle atılan) SHA-1 özetiyle Modrinth'te bulup
    simge / başlık / proje bağlantısını dizine yazar. Ağ yoksa sessizce vazgeçer."""
    try:
        todo = {}
        idx = load_index(inst)
        for ctype in (ctypes or list(CTYPES)):
            folder = content_dir(inst, ctype)
            if not folder.is_dir():
                continue
            for p in folder.iterdir():
                if not p.is_file():
                    continue
                base = p.name[:-9] if p.name.endswith(".disabled") else p.name
                if not base.lower().endswith(CTYPES[ctype][1]["ext"]):
                    continue
                if ctype == "mods" and base.lower().startswith(RIVEN_MOD_PREFIX):
                    continue
                k = f"{ctype}/{base}"
                if idx.get(k, {}).get("project_id"):
                    continue
                st = p.stat()
                tried = (inst["id"], k, st.st_size, st.st_mtime_ns)
                if tried in IDENT_TRIED or st.st_size > 120_000_000:
                    continue
                IDENT_TRIED.add(tried)
                h = hashlib.sha1()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                todo[h.hexdigest()] = k
        if not todo:
            return
        found = mr_post_json(f"{MODRINTH}/version_files", {"hashes": list(todo), "algorithm": "sha1"})
        if not isinstance(found, dict) or not found:
            return
        pids = sorted({v.get("project_id") for v in found.values() if v.get("project_id")})
        projs = {}
        for i in range(0, len(pids), 50):
            chunk = pids[i:i + 50]
            for pr in http_json(f"{MODRINTH}/projects?ids=" + urllib.parse.quote(json.dumps(chunk))):
                projs[pr.get("id")] = pr
        with DATA_LOCK:
            idx = load_index(inst)
            for digest, ver in found.items():
                k = todo.get(digest)
                pr = projs.get(ver.get("project_id"))
                if not k or not pr:
                    continue
                idx[k] = {"project_id": pr["id"], "title": pr.get("title") or k.split("/", 1)[1],
                          "icon": cdn_icon(pr.get("icon_url")), "version": ver.get("version_number"),
                          "version_id": ver.get("id")}
            write_json(index_path(inst), idx)
    except Exception as exc:
        add_log(f"İçerik tanıma atlandı: {exc}")


def list_content(inst, ctype):
    folder = content_dir(inst, ctype)
    exts = CTYPES[ctype][1]["ext"]
    idx = load_index(inst)
    items = []
    if folder.is_dir():
        for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file():
                continue
            base = p.name[:-9] if p.name.endswith(".disabled") else p.name
            if not base.lower().endswith(exts):
                continue
            if ctype == "mods" and base.lower().startswith(RIVEN_MOD_PREFIX):
                continue  # launcher'ın kendi gömülü modu, kullanıcı listesinde yönetilmez
            meta = idx.get(f"{ctype}/{base}", {})
            lm = local_meta(p, ctype) if not (meta.get("icon") and meta.get("title")) else {}
            icon = meta.get("icon")
            if not icon and lm.get("icon_member"):
                icon = f"/content-icon/{inst['id']}/{ctype}/{urllib.parse.quote(base)}"
            items.append({
                "filename": base, "enabled": base == p.name, "size": p.stat().st_size,
                "title": meta.get("title") or lm.get("title") or base, "icon": icon,
                "version": meta.get("version") or lm.get("version"), "project_id": meta.get("project_id"),
            })
    return items


def public_instance(inst):
    out = dict(inst)
    out.setdefault("icon_key", ICON_KEYS[int(hashlib.sha1(inst["id"].encode()).hexdigest(), 16) % len(ICON_KEYS)])
    out.setdefault("custom_icon", False)
    out.setdefault("icon_rev", 0)
    out["counts"] = {k: sum(1 for i in list_content(inst, k) if i["enabled"]) for k in CTYPES}
    return out


MIN_MC = (1, 8)          # listelenecek en eski Minecraft sürümü
FABRIC_MIN_MC = (1, 14)  # Fabric yalnızca 1.14 ve üstünü destekler


def mc_supports_fabric(mc):
    return _ver_tuple(mc) >= FABRIC_MIN_MC


def mc_supports_optifine(mc):
    """1.14 öncesi (1.8 - 1.13.x): Fabric yok, bunun yerine OptiFine kullanılır."""
    return MIN_MC <= _ver_tuple(mc) < FABRIC_MIN_MC


def default_loader(mc):
    return "fabric" if mc_supports_fabric(mc) else "optifine"


def _plain_release(v):
    return bool(re.fullmatch(r"\d+(\.\d+)*", str(v))) and _ver_tuple(v) >= MIN_MC


def get_versions():
    """Minecraft 1.8'den itibaren TÜM kararlı sürümler (1.8, 1.8.9, 1.12.2, 1.16.5, 1.21.x ...)."""
    if VERSIONS_CACHE["v"] and time.time() - VERSIONS_CACHE["t"] < 3600:
        return VERSIONS_CACHE["v"]
    versions = []
    try:
        versions = [v["id"] for v in mll.utils.get_version_list()
                    if v.get("type") == "release" and _plain_release(v["id"])]
    except Exception as exc:
        add_log(f"Sürüm listesi alınamadı: {exc}")
    if not versions:   # çevrimdışı/yedek: Fabric listesi + bilgisayarda kurulu sürümler
        try:
            versions = [v for v in mll.fabric.get_stable_minecraft_versions() if _plain_release(v)]
        except Exception:
            pass
        try:
            versions += [v["id"] for v in mll.utils.get_installed_versions(SHARED_DIR) if _plain_release(v["id"])]
        except Exception:
            pass
    versions = sorted(set(versions), key=_ver_tuple, reverse=True)
    if DEFAULT_VERSION not in versions:
        versions.insert(0, DEFAULT_VERSION)
    VERSIONS_CACHE.update(t=time.time(), v=versions)
    return versions


# --------------------------------------------------------------------- Modrinth
MODRINTH_HOSTS = {"bmclapi2.bangbang93.com", "optifine.net", "api.modrinth.com", "cdn.modrinth.com", "api.curseforge.com",
                  "edge.forgecdn.net", "mediafilez.forgecdn.net", "media.forgecdn.net",
                  "edge-service.forgecdn.net", "mediafiles.forgecdn.net"}
_REAL_GETADDRINFO = socket.getaddrinfo


_SSL_CTX = {}


def make_ssl_context(level=0):
    """Önbellekli: sertifika deposunu her istekte yeniden yüklemek (Windows'ta ~100 ms) ağ işlerini yavaşlatıyordu."""
    ctx = _SSL_CTX.get(level)
    if ctx is None:
        ctx = _SSL_CTX[level] = _build_ssl_context(level)
    return ctx


def _build_ssl_context(level=0):
    """0: varsayılan. 1: katı X509 denetimi kapalı (Python 3.13+ bazı sertifikalarda takılır).
    2: certifi sertifika paketi. Üçünde de zincir ve alan adı doğrulaması AÇIK kalır."""
    if level == 2:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    else:
        ctx = ssl.create_default_context()
    if level >= 1:
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return ctx


def doh_resolve(host):
    """Sistem DNS'i çözemezse Cloudflare DNS-over-HTTPS ile IPv4 adresi bul."""
    req = urllib.request.Request(
        f"https://1.1.1.1/dns-query?name={urllib.parse.quote(host)}&type=A",
        headers={"accept": "application/dns-json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=8, context=make_ssl_context(0)) as resp:
        data = json.load(resp)
    return [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]


def patched_getaddrinfo(host, port, *args, **kwargs):
    """Yalnızca Modrinth alan adları için: sistem DNS'i başarısızsa DoH'a düş, IPv4'ü öne al."""
    if host not in MODRINTH_HOSTS:
        return _REAL_GETADDRINFO(host, port, *args, **kwargs)
    try:
        result = _REAL_GETADDRINFO(host, port, *args, **kwargs)
    except socket.gaierror:
        try:
            ips = doh_resolve(host)
        except Exception:
            ips = []
        if not ips:
            raise
        add_log(f"Sistem DNS'i {host} adresini çözemedi, DNS-over-HTTPS kullanıldı.")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, int(port or 0))) for ip in ips]
    return sorted(result, key=lambda r: r[0] != socket.AF_INET)


socket.getaddrinfo = patched_getaddrinfo


def open_url(req, timeout=20):
    """HTTPS isteği. Sertifika hatasında daha esnek bağlamlarla, ağ hatasında bir kez daha dener."""
    levels = [0, 1]
    try:
        import certifi  # noqa: F401
        levels.append(2)
    except ImportError:
        pass
    last, net_tries = None, 0
    for level in levels:
        while True:
            try:
                return urllib.request.urlopen(req, timeout=timeout, context=make_ssl_context(level))
            except urllib.error.HTTPError:
                raise
            except Exception as exc:
                last = exc
                if isinstance(getattr(exc, "reason", exc), ssl.SSLError):
                    break  # bir sonraki sertifika seviyesine geç
                net_tries += 1
                if net_tries < 2:
                    time.sleep(0.5)
                    continue
                raise
    raise last


def explain_net_error(exc):
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLError):
        msg = "Güvenlik sertifikası doğrulanamadı (antivirüs/güvenlik duvarının HTTPS taraması olabilir)"
    elif isinstance(reason, socket.gaierror):
        msg = ("Alan adı çözülemedi (DNS). İnternet yok ya da servis sağlayıcı engelliyor olabilir; "
               "DNS'i 1.1.1.1 veya 8.8.8.8 yapmayı dene")
    elif isinstance(reason, (socket.timeout, TimeoutError)):
        msg = "Bağlantı zaman aşımına uğradı (güvenlik duvarı, VPN veya servis sağlayıcı engeli olabilir)"
    elif getattr(reason, "winerror", None) == 10049 or getattr(reason, "errno", None) in (10049, 99):
        msg = ("Geçersiz adres (0.0.0.0 gibi). Sunucu aynı bilgisayardaysa http://127.0.0.1:8780, "
               "başka bilgisayardaysa onun IPv4 adresini yaz")
    elif isinstance(reason, (ConnectionRefusedError, ConnectionResetError, PermissionError)):
        msg = "Bağlantı reddedildi ya da kesildi (Windows güvenlik duvarı veya antivirüs engelliyor olabilir)"
    else:
        msg = "Bağlantı kurulamadı"
    return f"{msg} [{type(reason).__name__}: {reason}]"


def mojang_lookup_uuid(name):
    """Mojang'ın genel API'si: kullanıcı adından UUID. Kimlik doğrulama istemez."""
    req = urllib.request.Request(f"https://api.mojang.com/users/profiles/minecraft/{urllib.parse.quote(name)}",
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with open_url(req, 10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 204):
            raise ApiError(f"\"{name}\" adında bir Minecraft hesabı bulunamadı.")
        raise ApiError(f"Mojang hatası ({exc.code}).", 502)
    except ValueError:
        raise ApiError(f"\"{name}\" adında bir Minecraft hesabı bulunamadı.")
    except Exception as exc:
        raise ApiError(f"Mojang'a ulaşılamadı: {explain_net_error(exc)}", 502)
    raw = str(data.get("id", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{32}", raw):
        raise ApiError("Mojang beklenmeyen bir yanıt verdi.", 502)
    uuid_str = f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    return {"uuid": uuid_str, "name": str(data.get("name", name))}


SKIN_DIR = HOME_DIR / "skins"
CUSTOM_SKIN = HOME_DIR / "skin_custom.png"


def valid_png(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) < 200_000


def fetch_skin(name):
    """Mojang'dan oyuncunun skin PNG'sini indirir (önbellekli). Hesap yoksa None."""
    if not re.fullmatch(r"\w{3,16}", name):
        return None
    SKIN_DIR.mkdir(parents=True, exist_ok=True)
    cache, miss = SKIN_DIR / f"{name.lower()}.png", SKIN_DIR / f"{name.lower()}.none"
    if cache.is_file() and time.time() - cache.stat().st_mtime < 86400:
        return cache.read_bytes()
    if miss.is_file() and time.time() - miss.stat().st_mtime < 3600:
        return None
    try:
        uid = mojang_lookup_uuid(name)["uuid"].replace("-", "")
        req = urllib.request.Request(f"https://sessionserver.mojang.com/session/minecraft/profile/{uid}",
                                     headers={"User-Agent": UA, "Accept": "application/json"})
        with open_url(req, 10) as resp:
            prof = json.load(resp)
        tex = next(p for p in prof["properties"] if p["name"] == "textures")
        url = json.loads(base64.b64decode(tex["value"]))["textures"]["SKIN"]["url"]
        if not re.fullmatch(r"https?://textures\.minecraft\.net/texture/[0-9a-f]+", url):
            raise ValueError("beklenmeyen skin adresi")
        with open_url(urllib.request.Request(url, headers={"User-Agent": UA}), 10) as resp:
            data = resp.read(200_001)
        if not valid_png(data):
            raise ValueError("geçersiz skin")
        cache.write_bytes(data)
        return data
    except Exception:
        if cache.is_file():
            return cache.read_bytes()
        try:
            miss.write_text("1")
        except OSError:
            pass
        return None


def http_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with open_url(req, timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise ApiError(f"Modrinth hatası ({exc.code}).", 502)
    except ValueError:
        raise ApiError("Modrinth beklenmeyen bir yanıt verdi (proxy veya engel sayfası olabilir).", 502)
    except Exception as exc:
        raise ApiError(f"Modrinth'e ulaşılamadı: {explain_net_error(exc)}", 502)


def diagnose_network():
    steps = []

    def step(name, fn):
        try:
            steps.append({"name": name, "ok": True, "detail": str(fn())})
        except Exception as exc:
            steps.append({"name": name, "ok": False, "detail": explain_net_error(exc)})

    host = "api.modrinth.com"
    root = MODRINTH.rsplit("/v2", 1)[0] + "/"

    def dns(h):
        return lambda: ", ".join(sorted({r[4][0] for r in _REAL_GETADDRINFO(h, 443, type=socket.SOCK_STREAM)}))

    def raw_internet():
        socket.create_connection(("1.1.1.1", 443), timeout=6).close()
        return "bağlandı"

    def tcp():
        ip = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        socket.create_connection((ip, 443), timeout=8).close()
        return f"{ip} bağlandı"

    def tls():
        with socket.create_connection((host, 443), timeout=8) as sock:
            with make_ssl_context(0).wrap_socket(sock, server_hostname=host) as tls_sock:
                return tls_sock.version()

    def http():
        req = urllib.request.Request(root, headers={"User-Agent": UA})
        with open_url(req, 10) as resp:
            return f"HTTP {resp.status}"

    step("İnternet (1.1.1.1:443)", raw_internet)
    step("DNS: cloudflare.com", dns("cloudflare.com"))
    step("DNS: api.modrinth.com", dns(host))
    step("TCP 443: api.modrinth.com", tcp)
    step("TLS/sertifika (varsayılan)", tls)
    step("HTTPS isteği (yedek yollar dahil)", http)

    ok = {st["name"]: st["ok"] for st in steps}
    if not ok["İnternet (1.1.1.1:443)"]:
        summary = "İnternet yok ya da dışarıya çıkış engelli (güvenlik duvarı/antivirüs/VPN)."
    elif not ok["DNS: api.modrinth.com"] and ok["DNS: cloudflare.com"]:
        summary = ("Sistem DNS'i api.modrinth.com'u çözemiyor (servis sağlayıcı engeli olabilir). Launcher "
                   "otomatik DNS-over-HTTPS dener; olmazsa Windows DNS'ini 1.1.1.1 / 8.8.8.8 yap.")
    elif not ok["DNS: cloudflare.com"]:
        summary = "DNS genel olarak çalışmıyor. Ağ bağlantını ve DNS ayarını kontrol et."
    elif not ok["TCP 443: api.modrinth.com"]:
        summary = "Modrinth'in IP adresine bağlanılamıyor (güvenlik duvarı, VPN veya servis sağlayıcı engeli)."
    elif not ok["HTTPS isteği (yedek yollar dahil)"]:
        summary = ("Bağlantı kuruluyor ama HTTPS isteği başarısız: antivirüsün 'web koruması / HTTPS tarama' "
                   "özelliğini geçici kapatmayı dene ya da Windows Güvenlik Duvarı'nda uygulamaya izin ver.")
    else:
        summary = "Bağlantı sağlam görünüyor. Aramayı tekrar dene."
    return {"steps": steps, "summary": summary}


def cdn_icon(url):
    return url if isinstance(url, str) and url.startswith("https://cdn.modrinth.com/") else None


def project_id_ok(pid):
    if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", pid):
        raise ApiError("Geçersiz proje.")
    return pid


SORT_KEYS = ("relevance", "downloads", "updated", "newest")


def modrinth_search(query, ptype, inst, offset, sort="", mc=""):
    facets = [[f"project_type:{ptype}"]]
    if ptype == "modpack":
        facets.append(["categories:fabric"])  # launcher yalnızca Fabric paketlerini kurabilir
        if mc:
            facets.append([f"versions:{mc}"])
    elif inst:
        facets.append([f"versions:{inst['mc_version']}"])
        if ptype == "mod":
            facets.append(["categories:fabric"])
    if sort not in SORT_KEYS:
        sort = "relevance"
    if sort == "relevance" and not query:
        sort = "downloads"
    params = {"query": query, "facets": json.dumps(facets), "limit": 20, "offset": offset, "index": sort}
    data = http_json(f"{MODRINTH}/search?" + urllib.parse.urlencode(params))
    installed = set()
    if inst and ptype in PTYPES:
        ctype = PTYPES[ptype]["key"]
        installed = {v.get("project_id") for k, v in load_index(inst).items()
                     if k.startswith(ctype + "/")}

    def page_url(h):
        slug = str(h.get("slug") or "")
        if not re.fullmatch(r"[\w\-]{1,80}", slug):
            return None
        return f"https://modrinth.com/{ptype}/{slug}"

    hits = [{
        "project_id": h["project_id"], "title": h.get("title", ""),
        "author": h.get("author", ""), "description": h.get("description", ""),
        "icon": cdn_icon(h.get("icon_url")), "downloads": h.get("downloads", 0),
        "installed": h["project_id"] in installed, "url": page_url(h),
        "categories": [str(c) for c in (h.get("display_categories") or [])][:3],
    } for h in data.get("hits", [])]
    return {"hits": hits, "total": data.get("total_hits", 0), "offset": offset}


def pick_version(project_id, inst, ptype):
    params = {"game_versions": json.dumps([inst["mc_version"]])}
    if ptype == "mod":
        params["loaders"] = json.dumps(["fabric"])
    versions = http_json(f"{MODRINTH}/project/{urllib.parse.quote(project_id)}/version?"
                         + urllib.parse.urlencode(params))
    if not versions:
        raise ApiError(f"Bu proje {inst['mc_version']} için uyumlu dosya sunmuyor.")
    releases = [v for v in versions if v.get("version_type") == "release"]
    return (releases or versions)[0]


def download_file(inst, ptype, version):
    files = version.get("files") or []
    if not files:
        raise ApiError("Sürümde dosya yok.")
    info = next((f for f in files if f.get("primary")), files[0])
    exts = PTYPES[ptype]["ext"]
    fname = safe_filename(info.get("filename"), exts)
    parsed = urllib.parse.urlparse(info.get("url", ""))
    if parsed.scheme != "https" or parsed.hostname != "cdn.modrinth.com":
        raise ApiError("Beklenmeyen indirme adresi, reddedildi.")

    folder = instance_dir(inst) / PTYPES[ptype]["dir"]
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / fname
    if dest.exists() or (folder / (fname + ".disabled")).exists():
        return fname

    tmp = folder / (fname + ".part")
    sha512, sha1 = hashlib.sha512(), hashlib.sha1()
    req = urllib.request.Request(info["url"], headers={"User-Agent": UA})
    try:
        with open_url(req, 60) as resp:
            final = urllib.parse.urlparse(resp.geturl())
            if final.scheme != "https" or final.hostname != "cdn.modrinth.com":
                raise ApiError("İndirme beklenmeyen bir adrese yönlendirildi.")
            total = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise ApiError("Dosya çok büyük.")
                    fh.write(chunk)
                    sha512.update(chunk)
                    sha1.update(chunk)
        hashes = info.get("hashes") or {}
        if hashes.get("sha512"):
            ok = hashes["sha512"].lower() == sha512.hexdigest()
        elif hashes.get("sha1"):
            ok = hashes["sha1"].lower() == sha1.hexdigest()
        else:
            ok = False
        if not ok:
            raise ApiError("Dosya doğrulaması (hash) başarısız, silindi.")
        os.replace(tmp, dest)
    except (urllib.error.URLError, OSError) as exc:
        raise ApiError(f"İndirme başarısız: {explain_net_error(exc)}", 502)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return fname


def install_version(inst, ptype, version, proj, installed, done, depth=0):
    pid = version["project_id"]
    if pid in installed:
        return
    installed.add(pid)
    proj = proj or http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}")
    fname = download_file(inst, ptype, version)
    with DATA_LOCK:
        idx = load_index(inst)
        idx[f"{PTYPES[ptype]['key']}/{fname}"] = {
            "project_id": pid, "title": proj.get("title", fname),
            "icon": cdn_icon(proj.get("icon_url")), "version": version.get("version_number"),
            "version_id": version.get("id"),
        }
        write_json(index_path(inst), idx)
    done.append(proj.get("title", fname))
    add_log(f"Kuruldu: {proj.get('title', fname)} ({fname})")

    if ptype == "mod" and depth < 4:
        for dep in version.get("dependencies") or []:
            dpid = dep.get("project_id")
            if dep.get("dependency_type") != "required" or not dpid or dpid in installed:
                continue
            try:
                if dep.get("version_id"):
                    dv = http_json(f"{MODRINTH}/version/{urllib.parse.quote(dep['version_id'])}")
                else:
                    dv = pick_version(dpid, inst, ptype)
                install_version(inst, ptype, dv, None, installed, done, depth + 1)
            except ApiError as exc:
                add_log(f"Bağımlılık kurulamadı ({dpid}): {exc.msg}")


def install_project(inst, ptype, pid):
    proj = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}")
    ctype = PTYPES[ptype]["key"]
    installed = {v.get("project_id") for k, v in load_index(inst).items()
                 if k.startswith(ctype + "/")}
    if proj["id"] in installed:
        return {"installed": [], "skipped": True}
    version = pick_version(proj["id"], inst, ptype)
    done = []
    install_version(inst, ptype, version, proj, installed, done)
    return {"installed": done, "skipped": False}


# ----------------------------------------------------------------------- hesap
def store_refresh_token(token):
    if keyring is None:
        add_log("keyring kurulu değil, Microsoft oturumu hatırlanmayacak.")
        return
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
    except Exception as exc:
        add_log(f"Token kaydedilemedi: {exc}")


def load_refresh_token():
    if keyring is None:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        return None


def client_id():
    return CFG.get("client_id") or DEFAULT_CLIENT_ID or os.environ.get("RIVEN_CLIENT_ID", "")


def refresh_session(refresh_token):
    data = call_compat(mll.microsoft_account.complete_refresh,
                       client_id=client_id(), client_secret=None,
                       redirect_uri=REDIRECT_URI, refresh_token=refresh_token)
    store_refresh_token(data["refresh_token"])
    ACCOUNT["data"], ACCOUNT["t"] = data, time.time()
    return data


AUTO_LOGIN_DONE = threading.Event()


def auto_login():
    """Arka planda çalışır (anahtarlık + ağ), pencere açılışını geciktirmez."""
    def work():
        try:
            token = load_refresh_token()
            if not (client_id() and token):
                return
            data = refresh_session(token)
            add_log(f"Microsoft oturumu yenilendi: {data['name']}")
        except Exception as exc:
            add_log(f"Otomatik giriş başarısız, tekrar giriş yap: {exc}")
        finally:
            AUTO_LOGIN_DONE.set()
    threading.Thread(target=work, daemon=True).start()


def account_info():
    data = ACCOUNT["data"]
    return {
        "mode": "microsoft" if data else "offline",
        "name": data["name"] if data else CFG.get("offline_name", "Player"),
        "offline_name": CFG.get("offline_name", "Player"),
        "client_id": CFG.get("client_id", ""),
        "client_id_baked": bool(DEFAULT_CLIENT_ID),
        "keyring": keyring is not None,
        "curseforge": bool(cf_key()),
    }


def current_auth():
    AUTO_LOGIN_DONE.wait(15)   # açılıştaki otomatik giriş bitsin (çevrimdışı ada düşmeyelim)
    data = ACCOUNT["data"]
    if data and time.time() - ACCOUNT["t"] > TOKEN_FRESH_SECONDS:   # taze token'ı yeniden yenileme: 1-3 sn kazandırır
        try:
            data = refresh_session(data["refresh_token"])
        except Exception as exc:
            add_log(f"Token yenilenemedi, eskisiyle denenecek: {exc}")
        return {"username": data["name"], "uuid": data["id"], "token": data["access_token"]}
    name = CFG.get("offline_name", "Player")
    return {"username": name, "uuid": offline_uuid(name), "token": "0"}


# ------------------------------------------------------------------ oyun başlatma
def progress_callbacks():
    return {
        "setStatus": lambda s: PROG.update(status=str(s)),
        "setProgress": lambda v: PROG.update(value=v),
        "setMax": lambda v: PROG.update(max=v),
    }


def find_installed_fabric(installed_ids, mc_version):
    found = [i for i in installed_ids
             if i.startswith("fabric-loader-") and i.endswith("-" + mc_version)]
    found.sort(key=lambda i: _ver_tuple(i.split("-")[2]) if i.count("-") >= 3 else (0,))
    return found[-1] if found else None


# ------------------------------------------------------------------ OptiFine (1.14 öncesi)
OPTIFINE_API = "https://bmclapi2.bangbang93.com/optifine"
OPTIFINE_SITE = "https://optifine.net"
OPTIFINE_DIR = HOME_DIR / "optifine"          # indirilen OptiFine jar'ları (önbellek)
OPTIFINE_TYPE_RANK = {"HD_U": 5, "HD": 4, "ULTRA": 3, "STANDARD": 2, "LIGHT": 1}


def _of_key(b):
    m = re.match(r"([A-Z])(\d+)", b["patch"])
    return (OPTIFINE_TYPE_RANK.get(b["type"], 0), ord(m.group(1)) if m else 0, int(m.group(2)) if m else 0)


def optifine_builds(mc):
    """Bu Minecraft sürümü için OptiFine derlemeleri: [{mc, type, patch, filename}] (önizleme sürümleri hariç)."""
    builds = []
    try:
        for it in http_json(f"{OPTIFINE_API}/{urllib.parse.quote(mc)}") or []:
            fn = str(it.get("filename") or "")
            typ, patch = str(it.get("type") or ""), str(it.get("patch") or "")
            if fn and typ and patch and "pre" not in patch.lower() and "pre" not in fn.lower() \
                    and re.fullmatch(r"[\w.\-]+", fn) and re.fullmatch(r"[A-Z]\d+", patch):
                builds.append({"mc": mc, "type": typ, "patch": patch, "filename": fn})
    except Exception as exc:
        add_log(f"OptiFine listesi (BMCLAPI) alınamadı: {exc}")
    if not builds:   # yedek: resmi indirme sayfası
        try:
            req = urllib.request.Request(f"{OPTIFINE_SITE}/downloads", headers={"User-Agent": UA})
            with open_url(req, 20) as resp:
                html = resp.read(4_000_000).decode("utf-8", "replace")
            pat = r"f=(OptiFine_" + re.escape(mc) + r"_(HD_U|HD|ULTRA|LIGHT|STANDARD)_([A-Z]\d+)\.jar)"
            for fn, typ, patch in set(re.findall(pat, html)):
                builds.append({"mc": mc, "type": typ, "patch": patch, "filename": fn})
        except Exception as exc:
            add_log(f"OptiFine listesi (optifine.net) alınamadı: {exc}")
    return builds


def optifine_pick(mc):
    builds = optifine_builds(mc)
    return max(builds, key=_of_key) if builds else None


def _valid_optifine_jar(path):
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
        return any(n.startswith("optifine/") for n in names) and \
            any(re.fullmatch(r"launchwrapper-of-[\d.]+\.jar", n) for n in names)
    except Exception:
        return False


def _download_to(url, dest, timeout=60):
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    got = 0
    try:
        with open_url(req, timeout) as resp, open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_DOWNLOAD:
                    raise RuntimeError("OptiFine dosyası çok büyük.")
                fh.write(chunk)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def optifine_download(build):
    """OptiFine jar'ını indirir (önbellekli). Önce BMCLAPI, olmazsa resmi optifine.net."""
    OPTIFINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = OPTIFINE_DIR / build["filename"]
    if dest.is_file() and _valid_optifine_jar(dest):
        return dest
    errors = []
    try:   # 1) BMCLAPI
        _download_to(f"{OPTIFINE_API}/{build['mc']}/{build['type']}/{build['patch']}", dest)
        if _valid_optifine_jar(dest):
            return dest
        dest.unlink(missing_ok=True)
        errors.append("BMCLAPI geçersiz dosya verdi")
    except Exception as exc:
        errors.append(f"BMCLAPI: {exc}")
    try:   # 2) resmi site: adloadx sayfasındaki geçici indirme bağlantısı
        import html as _html
        req = urllib.request.Request(f"{OPTIFINE_SITE}/adloadx?f={urllib.parse.quote(build['filename'])}",
                                     headers={"User-Agent": UA})
        with open_url(req, 20) as resp:
            page = resp.read(2_000_000).decode("utf-8", "replace")
        m = re.search(r"""href=['"](downloadx\?f=[^'"]+)['"]""", page)
        if not m:
            raise RuntimeError("indirme bağlantısı bulunamadı")
        _download_to(f"{OPTIFINE_SITE}/{_html.unescape(m.group(1))}", dest)
        if _valid_optifine_jar(dest):
            return dest
        dest.unlink(missing_ok=True)
        errors.append("optifine.net geçersiz dosya verdi")
    except Exception as exc:
        errors.append(f"optifine.net: {exc}")
    raise RuntimeError("OptiFine indirilemedi (" + "; ".join(errors) + ")")


def find_installed_optifine(installed_ids, mc_version):
    found = [i for i in installed_ids if i.startswith(mc_version + "-OptiFine_")]
    def key(i):
        m = re.search(r"_([A-Z])(\d+)$", i)
        return (ord(m.group(1)), int(m.group(2))) if m else (0, 0)
    found.sort(key=key)
    return found[-1] if found else None


def install_optifine(mc, cb=None):
    """OptiFine'ı launchwrapper/tweaker yöntemiyle kurur (HMCL/PCL ile aynı): jar kütüphane olur,
    Minecraft jar'ı değiştirilmez. Dönen değer: kurulan sürüm kimliği (versions/ klasöründeki)."""
    cb = cb or {}
    if cb.get("setStatus"):
        cb["setStatus"]("OptiFine hazırlanıyor...")
    build = optifine_pick(mc)
    if not build:
        raise RuntimeError(f"{mc} için OptiFine sürümü bulunamadı.")
    if cb.get("setStatus"):
        cb["setStatus"](f"OptiFine indiriliyor: {build['filename']}")
    jar = optifine_download(build)

    base = Path(SHARED_DIR)
    parent_json = base / "versions" / mc / f"{mc}.json"
    parent = json.loads(parent_json.read_text(encoding="utf-8"))
    ver = f"{mc}_{build['type']}_{build['patch']}"
    vid = f"{mc}-OptiFine_{build['type']}_{build['patch']}"

    lib_of = base / "libraries" / "optifine" / "OptiFine" / ver
    lib_of.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(jar, lib_of / f"OptiFine-{ver}.jar")
    with zipfile.ZipFile(jar) as zf:
        lw = next(n for n in zf.namelist() if re.fullmatch(r"launchwrapper-of-[\d.]+\.jar", n))
        lw_ver = re.fullmatch(r"launchwrapper-of-([\d.]+)\.jar", lw).group(1)
        lw_dir = base / "libraries" / "optifine" / "launchwrapper-of" / lw_ver
        lw_dir.mkdir(parents=True, exist_ok=True)
        (lw_dir / f"launchwrapper-of-{lw_ver}.jar").write_bytes(zf.read(lw))

    tweak = ["--tweakClass", "optifine.OptiFineTweaker"]
    data = {
        "id": vid, "inheritsFrom": mc, "jar": mc, "type": parent.get("type", "release"),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "releaseTime": parent.get("releaseTime", "2000-01-01T00:00:00+00:00"),
        "mainClass": "net.minecraft.launchwrapper.Launch",
        "libraries": [{"name": f"optifine:OptiFine:{ver}"}, {"name": f"optifine:launchwrapper-of:{lw_ver}"}],
    }
    if parent.get("arguments"):
        data["arguments"] = {"game": tweak}
    else:
        data["minecraftArguments"] = (parent.get("minecraftArguments", "") + " " + " ".join(tweak)).strip()
    out = base / "versions" / vid
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{vid}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    add_log(f"OptiFine kuruldu: {vid}")
    return vid


def refresh_fabric_loaders():
    """Açılıştan sonra arka planda: kurulu Fabric sürümlerinin loader'ını yeniler (oyun açılışını bekletmez)."""
    time.sleep(25)
    try:
        if RUNNING or PREPARING["id"]:
            return
        installed = {v["id"] for v in mll.utils.get_installed_versions(SHARED_DIR)}
        loader = mll.fabric.get_latest_loader_version()
        for mc in {i["mc_version"] for i in load_instances()}:
            have = find_installed_fabric(installed, mc)
            if not have or have == f"fabric-loader-{loader}-{mc}":
                continue
            if RUNNING or PREPARING["id"]:
                return
            mll.fabric.install_fabric(mc, SHARED_DIR, loader_version=loader)
            add_log(f"Fabric loader güncellendi: {mc} -> {loader}")
    except Exception:
        pass


def _same_file(a, b):
    """İki dosya birebir aynı mı (boyut + SHA1)? mtime'a güvenmeyiz, mod güncellenince kesin kopyalansın."""
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return hashlib.sha1(a.read_bytes()).digest() == hashlib.sha1(b.read_bytes()).digest()
    except OSError:
        return False


def riven_tag_available(inst):
    """Bu instance'ın Minecraft sürümü için gömülü Riven Tag jar'ı var mı?"""
    return (RIVEN_MODS_DIR / f"riventag-{inst['mc_version']}.jar").is_file()


def install_riven_tag_jar(inst):
    """Riven Tag jar'ını instance'ın mods klasörüne koyar; eski riventag-*.jar dosyalarını siler.
    Mod yalnızca Fabric + launcher'da jar'ı olan sürümler içindir; diğerlerinde eski jar'lar temizlenir."""
    mods_dir = instance_dir(inst) / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    src = RIVEN_MODS_DIR / f"riventag-{inst['mc_version']}.jar"
    keep = src.name if src.is_file() else None
    for old in mods_dir.glob(RIVEN_MOD_PREFIX + "*.jar"):
        if old.name != keep:
            try:
                old.unlink()
            except OSError:
                pass
    if keep:
        dest = mods_dir / keep
        if not dest.exists() or not _same_file(src, dest):
            shutil.copyfile(src, dest)
            add_log(f"Riven Tag modu kuruldu/güncellendi: {inst['name']}")


def install_riven_tag_all():
    """Tüm instance'lara Riven Tag'i kurar (launcher açılışında ve yeni instance'ta)."""
    for inst in load_instances():
        try:
            install_riven_tag_jar(inst)
        except Exception as exc:
            add_log(f"Riven Tag kurulamadı ({inst.get('name')}): {exc}")


def inject_riven_tag(inst, game_dir, auth):
    """Oyun başlarken: arkadaş listesini yazar ve modun kurulu olduğundan emin olur.
    Eksik olsa da oyun başlatmayı engellemez."""
    try:
        config_dir = game_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        write_json(config_dir / "riven-tag.json", {
            "self": {"uuid": auth["uuid"], "name": auth["username"]},
            "friends": friend_badges(),
        })
        (game_dir / "mods").mkdir(parents=True, exist_ok=True)
        install_riven_tag_jar(inst)
    except Exception as exc:
        add_log(f"Riven Tag eklenemedi (oyun yine de başlıyor): {exc}")


# ---------------------------------------------------------------- otomatik güncelleme
UPDATE = {"state": "idle", "version": "", "progress": 0.0, "message": ""}
UPDATE_LOCK = threading.Lock()


def _ver_tuple(v):
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def _update_dir():
    d = HOME_DIR / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_update():
    """GitHub'daki son sürümü kontrol eder. Yeni sürüm varsa (sürüm, indirme_adresi, sha256) döner."""
    if not UPDATE_REPO or "/" not in UPDATE_REPO:
        return None
    url = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with open_url(req, 15) as resp:
        rel = json.load(resp)
    tag = str(rel.get("tag_name") or "")
    if _ver_tuple(tag) <= _ver_tuple(APP_VERSION):
        return None
    for a in rel.get("assets") or []:
        if str(a.get("name", "")).endswith(UPDATE_ASSET_SUFFIX):
            dl = a.get("browser_download_url", "")
            host = urllib.parse.urlparse(dl).hostname or ""
            if urllib.parse.urlparse(dl).scheme != "https" or not (host == "github.com" or host.endswith(".githubusercontent.com")):
                continue
            digest = str(a.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else ""
            return tag.lstrip("vV"), dl, sha
    return None


def download_update(version, dl_url, sha256):
    dest = _update_dir() / f"RivenLauncher-Setup-{version}.exe"
    tmp = dest.with_suffix(".part")
    h = hashlib.sha256()
    req = urllib.request.Request(dl_url, headers={"User-Agent": UA})
    try:
        with open_url(req, 60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_DOWNLOAD:
                        raise ApiError("Güncelleme dosyası çok büyük.")
                    fh.write(chunk)
                    h.update(chunk)
                    if total:
                        UPDATE["progress"] = got / total
        if sha256 and h.hexdigest() != sha256:
            raise ApiError("Güncelleme doğrulaması (hash) başarısız.")
        if got < 1_000_000:
            raise ApiError("Güncelleme dosyası eksik indi.")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest


def apply_update(setup):
    """Kurulumu sessizce çalıştırır, bitince launcher'ı yeniden açar. Çağıran süreç çıkar."""
    exe = Path(sys.executable)
    managed = (exe.parent / "unins000.exe").is_file()   # Setup.exe ile kurulmuş mu?
    flags = 0x08000000 | 0x00000008 | 0x00000200       # NO_WINDOW | DETACHED | NEW_GROUP
    if managed:
        bat = _update_dir() / "apply.bat"
        bat.write_text(
            "@echo off\r\ntimeout /t 2 /nobreak >nul\r\n"
            f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS\r\n'
            f'start "" "{exe}"\r\n', encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)
    else:   # portable kopya: sihirbazı normal aç
        subprocess.Popen([str(setup)], creationflags=0x00000008, close_fds=True)
    time.sleep(1.0)
    os._exit(0)


def update_cycle(auto=True):
    with UPDATE_LOCK:
        if UPDATE["state"] in ("downloading", "installing"):
            return
        try:
            UPDATE.update(state="checking", message="", progress=0.0)
            found = find_update()
            if not found:
                UPDATE.update(state="idle")
                return
            version, dl, sha = found
            UPDATE.update(version=version)
            if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
                UPDATE.update(state="available", message="Yeni sürüm var (kaynak koddan çalıştığın için elle güncelle).")
                return
            if not auto:
                UPDATE.update(state="available")
                return
            UPDATE.update(state="downloading")
            add_log(f"Yeni launcher sürümü bulundu: {version}, indiriliyor...")
            setup = download_update(version, dl, sha)
            # Oyun açıkken kesme; oyun bitince kur
            while RUNNING or PREPARING["id"]:
                UPDATE.update(state="waiting", message="Oyun kapanınca güncellenecek.")
                time.sleep(5)
            UPDATE.update(state="installing", message="Güncelleniyor, launcher yeniden açılacak...")
            add_log("Launcher güncelleniyor...")
            time.sleep(1.5)   # arayüz mesajı görsün
            apply_update(setup)
        except Exception as exc:
            UPDATE.update(state="error", message=str(exc))
            add_log(f"Otomatik güncelleme başarısız: {exc}")


def update_worker():
    time.sleep(4)
    while True:
        if UPDATE_REPO:
            update_cycle(auto=True)
        time.sleep(1800)



def launch_worker(inst, repair):
    iid, name = inst["id"], inst["name"]
    try:
        auth = current_auth()
        mc = inst["mc_version"]
        PROG.update(status="Sürüm kontrol ediliyor...", value=0, max=1)
        installed = {v["id"] for v in mll.utils.get_installed_versions(SHARED_DIR)}
        cb = progress_callbacks()

        # Riven Tag Fabric ister: jar'ı olan sürümlerde Vanilla instance'lar da Fabric ile açılır.
        use_fabric = (inst["loader"] == "fabric" or riven_tag_available(inst)) and mc_supports_fabric(mc)
        local_fabric = find_installed_fabric(installed, mc) if use_fabric else None
        if use_fabric and local_fabric and not repair:
            version_id = local_fabric   # kuruluysa ağa hiç çıkma (loader güncellemesi arka planda yapılır)
        elif use_fabric:
            try:
                loader = mll.fabric.get_latest_loader_version()
                wanted = f"fabric-loader-{loader}-{mc}"
            except Exception as exc:
                add_log(f"Loader sürümü alınamadı (çevrimdışı?): {exc}")
                loader, wanted = None, None
            if wanted:
                if wanted not in installed or repair:
                    add_log(f"Kuruluyor: {wanted}")
                    mll.fabric.install_fabric(mc, SHARED_DIR, loader_version=loader, callback=cb)
                version_id = wanted
            else:
                version_id = find_installed_fabric(installed, mc)
                if not version_id:
                    raise RuntimeError("İnternet yok ve kurulu Fabric sürümü bulunamadı.")
        else:
            version_id = mc
            if mc not in installed or repair:
                add_log(f"Kuruluyor: {mc}")
                mll.install.install_minecraft_version(mc, SHARED_DIR, callback=cb)
                installed.add(mc)
            # 1.14 öncesi: OptiFine instance'ları OptiFine ile açılır (Vanilla seçilmişse dokunulmaz)
            if inst["loader"] == "optifine" and mc_supports_optifine(mc):
                local_of = find_installed_optifine(installed, mc)
                if local_of and not repair:
                    version_id = local_of   # kuruluysa ağa çıkma
                else:
                    try:
                        version_id = install_optifine(mc, cb)
                    except Exception as exc:
                        if local_of:
                            add_log(f"OptiFine güncellenemedi, kurulu sürüm kullanılacak: {exc}")
                            version_id = local_of
                        else:
                            add_log(f"UYARI: OptiFine kurulamadı, Vanilla açılıyor: {exc}")

        game_dir = instance_dir(inst)
        for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
            (game_dir / sub).mkdir(parents=True, exist_ok=True)
        if use_fabric:
            inject_riven_tag(inst, game_dir, auth)

        options = {
            "username": auth["username"], "uuid": auth["uuid"], "token": auth["token"],
            "launcherName": APP, "launcherVersion": APP_VERSION,
            "gameDirectory": str(game_dir),
            "jvmArguments": [f"-Xmx{inst['ram']}M", f"-Xms{min(inst['ram'], 2048)}M"] + JVM_FAST_FLAGS,
        }
        command = mll.command.get_minecraft_command(version_id, SHARED_DIR, options)
        if command and command[0] == "java" and not shutil.which("java"):
            raise RuntimeError(f"{mc} için Java bulunamadı. 'Onar' ile sürümü yeniden kur "
                               "(Java otomatik indirilir) veya Java yükle.")

        with DATA_LOCK:
            items = load_instances()
            for it in items:
                if it["id"] == iid:
                    it["last_played"] = time.time()
            write_json(INSTANCES_FILE, items)

        PROG.update(status=f"Oyun çalışıyor: {name}", value=0, max=1)
        add_log(f"Başlatılıyor: {name} ({version_id}) - {auth['username']}")
        proc = subprocess.Popen(
            command, cwd=str(game_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        RUNNING[iid] = proc
        RUN_STARTED[iid] = time.time()
        PREPARING["id"] = None
        for line in proc.stdout:
            add_log(f"[{name}] {line}")
        code = proc.wait()
        add_log(f"{name} kapandı (çıkış kodu {code}).")
    except Exception as exc:
        add_log(f"HATA ({name}): {exc}")
        PROG["status"] = "Hata, konsola bak"
    finally:
        RUNNING.pop(iid, None)
        RUN_STARTED.pop(iid, None)
        if PREPARING["id"] == iid:
            PREPARING["id"] = None
        if not RUNNING and PREPARING["id"] is None and not PROG["status"].startswith("Hata"):
            PROG.update(status="Hazır", value=0, max=1)


# ------------------------------------------------------------- Discord Rich Presence
class DiscordRPC:
    """Discord "oynuyor" durumu (IPC). Ek paket gerekmez; Discord masaüstü uygulaması açık olmalı."""

    def __init__(self):
        self.conn = None
        self.client_id = None
        self.connected = False
        self.sent = None
        self.last_send = 0.0
        self.last_try = 0.0
        self.error = "Henüz bağlanılmadı"

    @staticmethod
    def _paths():
        if sys.platform.startswith("win"):
            return [rf"\\.\pipe\discord-ipc-{i}" for i in range(10)]
        dirs = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")] + ["/tmp"]
        out = []
        for d in filter(None, dirs):
            for sub in ("", "app/com.discordapp.Discord/", "snap.discord/"):
                out += [f"{d}/{sub}discord-ipc-{i}" for i in range(10)]
        return out

    def _write(self, op, payload):
        data = json.dumps(payload).encode("utf-8")
        frame = struct.pack("<II", op, len(data)) + data
        if hasattr(self.conn, "sendall"):
            self.conn.sendall(frame)
        else:
            self.conn.write(frame)

    def _read_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.conn.recv(n - len(buf)) if hasattr(self.conn, "recv") else self.conn.read(n - len(buf))
            if not chunk:
                raise ConnectionError("Discord bağlantısı kapandı")
            buf += chunk
        return buf

    def _read(self):
        op, length = struct.unpack("<II", self._read_exact(8))
        body = self._read_exact(length) if length else b"{}"
        return op, json.loads(body)

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn, self.connected, self.sent = None, False, None

    def connect(self, client_id):
        last = None
        for path in self._paths():
            try:
                if sys.platform.startswith("win"):
                    conn = open(path, "r+b", buffering=0)
                else:
                    conn = socket.socket(socket.AF_UNIX)
                    conn.settimeout(5)
                    conn.connect(path)
            except OSError as exc:
                last = last or exc
                continue
            self.conn = conn
            try:
                self._write(0, {"v": 1, "client_id": client_id})
                _op, data = self._read()
                if data.get("evt") == "READY":
                    self.connected, self.error = True, ""
                    return True
                msg = (data.get("data") or {}).get("message") or data.get("message") or "Discord bağlantıyı reddetti"
                raise ConnectionError(msg)
            except Exception as exc:
                self.close()
                last = exc
        if isinstance(last, ConnectionError):
            self.error = f"Discord: {last}"
        else:
            self.error = "Discord uygulaması açık değil (veya Application ID yanlış)"
        return False

    def set_activity(self, activity):
        self._write(1, {"cmd": "SET_ACTIVITY", "nonce": uuid.uuid4().hex,
                        "args": {"pid": os.getpid(), "activity": activity}})
        _op, data = self._read()
        if data.get("evt") == "ERROR":
            raise ConnectionError((data.get("data") or {}).get("message", "Discord hatası"))


RPC = DiscordRPC()


def friends_list():
    out = []
    for f in CFG.get("friends") or []:
        if isinstance(f, dict) and f.get("uuid") and f.get("name"):
            out.append({"uuid": f["uuid"], "name": f["name"],
                        "offline_uuid": f.get("offline_uuid") or offline_uuid(f["name"]),
                        "premium": bool(f.get("premium", True))})
    return out


def friend_badges():
    """Rozet modu için UUID listesi: premium arkadaşın hem gerçek hem çevrimdışı UUID'si (korsan sunucuda da çıksın)."""
    out = []
    for f in friends_list():
        out.append({"uuid": f["uuid"], "name": f["name"]})
        if f["offline_uuid"] != f["uuid"]:
            out.append({"uuid": f["offline_uuid"], "name": f["name"]})
    return out


def save_friends(items):
    CFG["friends"] = items
    save_cfg()


def discord_cfg():
    d = CFG.get("discord") or {}
    return {"enabled": bool(d.get("enabled", True)), "client_id": str(d.get("client_id", "")),
            "show_name": bool(d.get("show_name", True))}


def desired_activity(cfg):
    assets = {"large_image": "riven", "large_text": APP}
    if RUNNING:
        iid = max(RUNNING, key=lambda k: RUN_STARTED.get(k, 0))
        try:
            inst = get_instance(iid)
        except ApiError:
            inst = None
        if inst:
            mods = sum(1 for i in list_content(inst, "mods") if i["enabled"]) if inst["loader"] == "fabric" else 0
            state = f"Minecraft {inst['mc_version']} • {loaderlabel(inst['loader'])}" + (f" • {mods} mod" if mods else "")
            return {"details": inst["name"] if cfg["show_name"] else "Minecraft oynuyor",
                    "state": state, "assets": assets,
                    "timestamps": {"start": int(RUN_STARTED.get(iid, time.time()))}}
    if PREPARING["id"]:
        return {"details": "Oyun hazırlanıyor…", "state": APP, "assets": assets,
                "timestamps": {"start": int(LAUNCHER_STARTED)}}
    return {"details": "Launcher'da", "state": "Instance'lar arasında geziniyor", "assets": assets,
            "timestamps": {"start": int(LAUNCHER_STARTED)}}


def loaderlabel(loader):
    return {"fabric": "Fabric", "optifine": "OptiFine"}.get(loader, "Vanilla")


def discord_worker():
    while True:
        time.sleep(3)
        try:
            cfg = discord_cfg()
            cid = cfg["client_id"]
            if not (cfg["enabled"] and re.fullmatch(r"\d{15,22}", cid)):
                if RPC.connected:
                    RPC.close()
                RPC.error = "Kapalı ya da Application ID girilmemiş"
                continue
            if RPC.connected and RPC.client_id != cid:
                RPC.close()
            if not RPC.connected:
                if time.time() - RPC.last_try < 15:
                    continue
                RPC.last_try, RPC.client_id = time.time(), cid
                if not RPC.connect(cid):
                    continue
            act = desired_activity(cfg)
            if act != RPC.sent and time.time() - RPC.last_send >= 15:  # Discord hız sınırı
                RPC.set_activity(act)
                RPC.sent, RPC.last_send = act, time.time()
        except Exception as exc:
            RPC.error = f"Discord: {exc}"
            RPC.close()


# ---------------------------------------------------------------------- API rotaları
ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


def qs(q, key, default=""):
    return q.get(key, [default])[0]


ID = "([a-f0-9]{10})"


@route("GET", "/state")
def r_state(m, q, b):
    PING["last"], PING["bye"] = time.time(), None
    try:
        since = int(qs(q, "since", "0"))
    except ValueError:
        since = 0
    with LOG_LOCK:
        logs = [l for l in LOGS if l["i"] > since][-400:]
        idx = LOG_STATE["idx"]
    return {
        "status": PROG["status"], "progress": PROG["value"] / max(PROG["max"], 1),
        "preparing": PREPARING["id"], "running": list(RUNNING),
        "account": account_info(), "logs": logs, "log_idx": idx,
        "theme": CFG.get("theme", "green"), "accent": CFG.get("accent", ""),
        "update": dict(UPDATE), "app_version": APP_VERSION,
    }


@route("POST", "/update/check")
def r_update_check(m, q, b):
    if not UPDATE_REPO:
        raise ApiError("Otomatik güncelleme kapalı (riven.py içinde UPDATE_REPO boş).")
    threading.Thread(target=update_cycle, daemon=True).start()
    return {"ok": True}


@route("POST", "/bye")
def r_bye(m, q, b):
    PING["bye"] = time.time()
    return {"ok": True}


@route("GET", "/versions")
def r_versions(m, q, b):
    return {"versions": get_versions(), "default": DEFAULT_VERSION}


@route("GET", "/instances")
def r_instances(m, q, b):
    return {"instances": [public_instance(i) for i in load_instances()]}


def create_instance(name, mc, loader, color=0, icon_key=None):
    """Yeni instance kaydı + klasörleri oluşturur (arayüzden ve modpack kurulumundan ortak)."""
    icon_key = icon_key if icon_key in ICON_KEYS else random.choice(ICON_KEYS)
    inst = {"id": uuid.uuid4().hex[:10], "name": name, "mc_version": mc, "loader": loader,
            "ram": 4096, "color": int(color) % 8, "created": time.time(), "last_played": 0,
            "icon_key": icon_key, "custom_icon": False, "icon_rev": 0}
    with DATA_LOCK:
        items = load_instances()
        items.append(inst)
        write_json(INSTANCES_FILE, items)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        (instance_dir(inst) / sub).mkdir(parents=True, exist_ok=True)
    try:
        install_riven_tag_jar(inst)
    except Exception:
        pass
    return inst


def remove_instance(inst):
    """Başarısız kurulumu geri al: kaydı ve klasörü sil."""
    with DATA_LOCK:
        write_json(INSTANCES_FILE, [i for i in load_instances() if i["id"] != inst["id"]])
    target = instance_dir(inst).resolve()
    if target.parent == INSTANCES_DIR.resolve() and target.exists():
        shutil.rmtree(target, ignore_errors=True)


@route("POST", "/instances")
def r_create(m, q, b):
    name = clean_text(b.get("name"), 32, "Ad")
    mc = str(b.get("mc_version") or DEFAULT_VERSION)
    if not re.fullmatch(r"[0-9A-Za-z._\-]{1,32}", mc):
        raise ApiError("Geçersiz sürüm.")
    loader = b.get("loader") or default_loader(mc)
    if loader not in ("fabric", "optifine", "vanilla"):
        raise ApiError("Geçersiz loader.")
    if loader in ("fabric", "optifine"):
        # Fabric 1.14 öncesini desteklemez -> OptiFine; OptiFine yalnızca 1.14 öncesi için -> Fabric
        loader = default_loader(mc)
        if loader == "optifine" and not mc_supports_optifine(mc):
            loader = "vanilla"
    inst = create_instance(name, mc, loader, int(b.get("color", 0)), str(b.get("icon_key") or ""))
    return {"instance": public_instance(inst)}


@route("POST", f"/instances/{ID}/update")
def r_update(m, q, b):
    iid = valid_id(m.group(1))
    with DATA_LOCK:
        items = load_instances()
        inst = next((i for i in items if i["id"] == iid), None)
        if not inst:
            raise ApiError("Instance bulunamadı.", 404)
        if "name" in b:
            inst["name"] = clean_text(b["name"], 32, "Ad")
        if "ram" in b:
            ram = int(b["ram"])
            if not 1024 <= ram <= 32768:
                raise ApiError("RAM 1024-32768 MB arasında olmalı.")
            inst["ram"] = ram
        if "color" in b:
            inst["color"] = int(b["color"]) % 8
        if "icon_key" in b:
            key = str(b["icon_key"])
            if key not in ICON_KEYS:
                raise ApiError("Geçersiz ikon.")
            inst["icon_key"] = key
            if inst.get("custom_icon"):
                inst["custom_icon"] = False
                inst["icon_rev"] = inst.get("icon_rev", 0) + 1
                (instance_dir(inst) / "icon.png").unlink(missing_ok=True)
        write_json(INSTANCES_FILE, items)
    return {"instance": public_instance(inst)}


@route("POST", f"/instances/{ID}/icon")
def r_icon_upload(m, q, b):
    inst = get_instance(valid_id(m.group(1)))
    data_url = str(b.get("data_url", ""))
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ApiError("Sadece PNG resim kabul edilir.")
    try:
        raw = base64.b64decode(data_url[len(prefix):], validate=True)
    except Exception:
        raise ApiError("Resim verisi okunamadı.")
    if not raw or len(raw) > MAX_ICON_BYTES:
        raise ApiError("Resim çok büyük.")
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ApiError("Geçerli bir PNG değil.")
    with DATA_LOCK:
        items = load_instances()
        cur = next((i for i in items if i["id"] == inst["id"]), None)
        if not cur:
            raise ApiError("Instance bulunamadı.", 404)
        path = instance_dir(cur) / "icon.png"
        tmp = path.with_name("icon.png.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)
        cur["custom_icon"] = True
        cur["icon_rev"] = cur.get("icon_rev", 0) + 1
        write_json(INSTANCES_FILE, items)
        cur = dict(cur)
    return {"instance": public_instance(cur)}


@route("POST", f"/instances/{ID}/icon/reset")
def r_icon_reset(m, q, b):
    with DATA_LOCK:
        items = load_instances()
        cur = next((i for i in items if i["id"] == valid_id(m.group(1))), None)
        if not cur:
            raise ApiError("Instance bulunamadı.", 404)
        (instance_dir(cur) / "icon.png").unlink(missing_ok=True)
        cur["custom_icon"] = False
        cur["icon_rev"] = cur.get("icon_rev", 0) + 1
        write_json(INSTANCES_FILE, items)
        cur = dict(cur)
    return {"instance": public_instance(cur)}


@route("POST", f"/instances/{ID}/delete")
def r_delete(m, q, b):
    iid = valid_id(m.group(1))
    if iid in RUNNING or PREPARING["id"] == iid:
        raise ApiError("Çalışan instance silinemez.")
    with DATA_LOCK:
        items = load_instances()
        inst = next((i for i in items if i["id"] == iid), None)
        if not inst:
            raise ApiError("Instance bulunamadı.", 404)
        write_json(INSTANCES_FILE, [i for i in items if i["id"] != iid])
    target = instance_dir(inst).resolve()
    if target.parent == INSTANCES_DIR.resolve() and target.exists():
        shutil.rmtree(target, ignore_errors=True)
    return {"ok": True}


@route("POST", f"/instances/{ID}/launch")
def r_launch(m, q, b):
    inst = get_instance(valid_id(m.group(1)))
    with LAUNCH_LOCK:
        if inst["id"] in RUNNING:
            raise ApiError("Bu instance zaten çalışıyor.")
        if PREPARING["id"]:
            raise ApiError("Başka bir instance hazırlanıyor, bitmesini bekle.")
        PREPARING["id"] = inst["id"]
    threading.Thread(target=launch_worker, args=(inst, bool(b.get("repair"))),
                     daemon=True).start()
    return {"ok": True}


@route("POST", f"/instances/{ID}/folder")
def r_folder(m, q, b):
    inst = get_instance(valid_id(m.group(1)))
    path = instance_dir(inst)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return {"ok": True}


@route("GET", f"/instances/{ID}/content")
def r_content(m, q, b):
    inst = get_instance(valid_id(m.group(1)))
    ctype = qs(q, "type", "mods")
    if ctype in CTYPES:
        identify_unindexed(inst, [ctype])
    return {"items": list_content(inst, ctype)}


@route("GET", f"/instances/{ID}/content/info")
def r_content_info(m, q, b):
    """Modrinth/CurseForge'da bulunamayan dosyalar için dosyanın kendi içindeki bilgiler."""
    inst = get_instance(valid_id(m.group(1)))
    ctype = qs(q, "type", "mods")
    if ctype not in CTYPES:
        raise ApiError("Geçersiz içerik türü.")
    fname = loose_filename(qs(q, "filename"), CTYPES[ctype][1]["ext"])
    path = content_file(inst, ctype, fname)
    if not path:
        raise ApiError("Dosya bulunamadı.", 404)
    lm = dict(local_meta(path, ctype))
    lm.pop("icon_member", None)
    meta = load_index(inst).get(f"{ctype}/{fname}", {})
    lm["title"] = meta.get("title") or lm.get("title") or fname
    lm["version"] = meta.get("version") or lm.get("version")
    lm["filename"] = fname
    lm["size"] = path.stat().st_size
    return lm


def content_target(m, b):
    inst = get_instance(valid_id(m.group(1)))
    ctype = b.get("type", "mods")
    if ctype not in CTYPES:
        raise ApiError("Geçersiz içerik türü.")
    exts = CTYPES[ctype][1]["ext"]
    fname = safe_filename(b.get("filename"), exts)
    if ctype == "mods" and fname.lower().startswith(RIVEN_MOD_PREFIX):
        raise ApiError("Bu, launcher'ın kendi modu; buradan yönetilemez.")
    return inst, ctype, content_dir(inst, ctype), fname


@route("POST", f"/instances/{ID}/content/toggle")
def r_toggle(m, q, b):
    inst, ctype, folder, fname = content_target(m, b)
    on, off = folder / fname, folder / (fname + ".disabled")
    with DATA_LOCK:
        if on.exists():
            on.rename(off)
            enabled = False
        elif off.exists():
            off.rename(on)
            enabled = True
        else:
            raise ApiError("Dosya bulunamadı.", 404)
    return {"enabled": enabled}


@route("POST", f"/instances/{ID}/content/delete")
def r_content_delete(m, q, b):
    inst, ctype, folder, fname = content_target(m, b)
    with DATA_LOCK:
        for p in (folder / fname, folder / (fname + ".disabled")):
            p.unlink(missing_ok=True)
        idx = load_index(inst)
        idx.pop(f"{ctype}/{fname}", None)
        write_json(index_path(inst), idx)
    return {"ok": True}


@route("GET", "/modrinth/search")
def r_search(m, q, b):
    ptype = qs(q, "type", "mod")
    if ptype not in PTYPES and ptype != "modpack":
        raise ApiError("Geçersiz tür.")
    inst = get_instance(valid_id(qs(q, "instance"))) if qs(q, "instance") else None
    mc = qs(q, "mc")
    if mc and not re.fullmatch(r"[0-9A-Za-z._\-]{1,32}", mc):
        raise ApiError("Geçersiz sürüm.")
    try:
        offset = max(0, int(qs(q, "offset", "0")))
    except ValueError:
        offset = 0
    return modrinth_search(qs(q, "q")[:80], ptype, inst, offset, qs(q, "sort"), mc)


@route("POST", "/modrinth/install")
def r_install(m, q, b):
    inst = get_instance(valid_id(b.get("instance")))
    ptype = b.get("type", "mod")
    if ptype not in PTYPES:
        raise ApiError("Geçersiz tür.")
    if ptype == "mod" and inst["loader"] != "fabric":
        raise ApiError(f"{loaderlabel(inst['loader'])} instance'a mod kurulamaz.")
    pid = project_id_ok(b.get("project_id"))
    with INSTALL_LOCK:
        return install_project(inst, ptype, pid)


@route("GET", "/account")
def r_account(m, q, b):
    return account_info()


@route("POST", "/account/offline")
def r_offline(m, q, b):
    name = str(b.get("name", "")).strip()
    if not re.fullmatch(r"\w{3,16}", name):
        raise ApiError("Ad 3-16 karakter olmalı (harf, rakam, _).")
    CFG["offline_name"] = name
    save_cfg()
    return account_info()


def ms_post_form(url, data):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                 "User-Agent": UA})
    try:
        with open_url(req, 20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:  # OAuth hataları 400 + JSON gelir
        try:
            return json.loads(exc.read())
        except Exception:
            raise ApiError(f"Microsoft hatası ({exc.code}).", 502)
    except ValueError:
        raise ApiError("Microsoft beklenmeyen bir yanıt verdi.", 502)
    except Exception as exc:
        raise ApiError(f"Microsoft'a ulaşılamadı: {explain_net_error(exc)}", 502)


def oauth_hint(desc):
    desc = desc or ""
    if "70002" in desc or "7000218" in desc:
        return " Azure'da Authentication bölümünde 'Allow public client flows' seçeneğini Evet yap."
    if "700016" in desc:
        return " Bu Client ID bulunamadı, yanlış yazılmış olabilir."
    return ""


def device_fail(session, message):
    if DEVICE["id"] == session:
        DEVICE.update(status="error", message=message)


def device_poll(session, cid, dev):
    interval = max(int(dev.get("interval", 5)), 1)
    deadline = time.time() + int(dev.get("expires_in", 900))
    failures = 0
    while time.time() < deadline and DEVICE["id"] == session:
        time.sleep(interval)
        if DEVICE["id"] != session:
            return
        try:
            tok = ms_post_form(f"{MS_AUTH}/token", {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": cid, "device_code": dev["device_code"]})
            failures = 0
        except ApiError as exc:
            failures += 1
            if failures >= 5:
                return device_fail(session, exc.msg)
            continue
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err == "authorization_declined":
            return device_fail(session, "Giriş reddedildi.")
        if err == "expired_token":
            break
        if err:
            desc = (tok.get("error_description") or err).split("\r\n")[0]
            return device_fail(session, desc + oauth_hint(desc))
        try:
            data = call_compat(mll.microsoft_account.complete_refresh, client_id=cid, client_secret=None,
                               redirect_uri=REDIRECT_URI, refresh_token=tok["refresh_token"])
        except Exception as exc:
            hint = ""
            if "NotPermitted" in type(exc).__name__:
                hint = " Azure uygulamana henüz Minecraft API izni verilmemiş (başvuru: aka.ms/mce-reviewappid)."
            return device_fail(session, f"Minecraft girişi başarısız: {exc}.{hint}")
        store_refresh_token(data["refresh_token"])
        ACCOUNT["data"], ACCOUNT["t"] = data, time.time()
        if DEVICE["id"] == session:
            DEVICE.update(status="ok", message=data["name"])
        add_log(f"Microsoft ile giriş yapıldı: {data['name']}")
        return
    device_fail(session, "Kodun süresi doldu, tekrar dene.")


@route("POST", "/account/device-start")
def r_device_start(m, q, b):
    cid = str(b.get("client_id", "")).strip() or client_id()
    if not re.fullmatch(r"[0-9a-fA-F\-]{20,40}", cid):
        raise ApiError("Client ID gerekli (UUID biçiminde, Azure uygulamasının Overview sayfasında).")
    if cid != DEFAULT_CLIENT_ID:
        CFG["client_id"] = cid
        save_cfg()
    dev = ms_post_form(f"{MS_AUTH}/devicecode", {"client_id": cid, "scope": "XboxLive.signin offline_access"})
    if "device_code" not in dev:
        desc = (dev.get("error_description") or dev.get("error") or "Cihaz kodu alınamadı").split("\r\n")[0]
        raise ApiError(desc + oauth_hint(desc))
    session = uuid.uuid4().hex
    uri = str(dev.get("verification_uri", "https://www.microsoft.com/link"))
    DEVICE.update(id=session, status="pending", message="", uri=uri)
    threading.Thread(target=device_poll, args=(session, cid, dev), daemon=True).start()
    return {"user_code": dev["user_code"], "display_uri": uri.replace("https://", "").rstrip("/"),
            "expires_in": int(dev.get("expires_in", 900))}


@route("GET", "/account/device-status")
def r_device_status(m, q, b):
    return {"status": DEVICE["status"], "message": DEVICE["message"]}


@route("POST", "/account/device-open")
def r_device_open(m, q, b):
    host = urllib.parse.urlparse(DEVICE.get("uri", "")).hostname
    if host not in ("www.microsoft.com", "microsoft.com", "login.microsoftonline.com", "login.live.com"):
        raise ApiError("Açılacak adres yok.")
    webbrowser.open(DEVICE["uri"])
    return {"ok": True}


@route("POST", "/account/login-start")
def r_login_start(m, q, b):
    cid = str(b.get("client_id", "")).strip()
    if not re.fullmatch(r"[0-9a-fA-F\-]{20,40}", cid):
        raise ApiError("Client ID geçersiz görünüyor (UUID biçiminde olmalı).")
    CFG["client_id"] = cid
    save_cfg()
    url, state, verifier = mll.microsoft_account.get_secure_login_data(cid, REDIRECT_URI)
    LOGIN.update(state=state, verifier=verifier)
    webbrowser.open(url)
    return {"url": url}


@route("POST", "/account/login-finish")
def r_login_finish(m, q, b):
    if not LOGIN.get("state"):
        raise ApiError("Önce giriş sürecini başlat.")
    try:
        code = mll.microsoft_account.parse_auth_code_url(str(b.get("url", "")).strip(),
                                                         LOGIN["state"])
    except Exception as exc:
        raise ApiError(f"Adres geçersiz veya state uyuşmuyor: {exc}")
    try:
        data = call_compat(mll.microsoft_account.complete_login,
                           client_id=CFG["client_id"], client_secret=None,
                           redirect_uri=REDIRECT_URI, auth_code=code,
                           code_verifier=LOGIN.get("verifier"))
    except Exception as exc:
        hint = ""
        if "NotPermitted" in type(exc).__name__:
            hint = " Azure uygulamana henüz Minecraft API izni verilmemiş (başvuru: aka.ms/mce-reviewappid)."
        raise ApiError(f"Giriş başarısız: {exc}.{hint}")
    LOGIN.clear()
    store_refresh_token(data["refresh_token"])
    ACCOUNT["data"], ACCOUNT["t"] = data, time.time()
    return account_info()


@route("POST", "/account/logout")
def r_logout(m, q, b):
    ACCOUNT["data"] = None
    if keyring is not None:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass
    return account_info()


# --------------------------------------------------------------------- FPS BOOST
FPS_NAME = "FPS BOOST"
FPS_VERSION = "1.21.11"
# (Modrinth adresi, ad, ne işe yarar). Sürüm desteklemiyorsa atlanır, kurulum bozulmaz.
FPS_MODS = [
    ("fabric-api", "Fabric API", "Modların çalışması için gereken temel kütüphane"),
    ("sodium", "Sodium", "Çizim motorunu baştan yazar, en büyük FPS artışı"),
    ("lithium", "Lithium", "Oyun mantığını hızlandırır (mob yapay zekâsı, fizik)"),
    ("ferrite-core", "FerriteCore", "RAM kullanımını ciddi şekilde azaltır"),
    ("modernfix", "ModernFix", "Açılışı hızlandırır, bellek sorunlarını giderir"),
    ("entityculling", "Entity Culling", "Görünmeyen yaratıkları hiç çizmez"),
    ("immediatelyfast", "ImmediatelyFast", "Arayüz ve yazı çizimini hızlandırır"),
    ("moreculling", "More Culling", "Görünmeyen blok yüzeylerini çizmez"),
    ("dynamic-fps", "Dynamic FPS", "Oyun arka plandayken kaynak kullanımını düşürür"),
    ("sodium-extra", "Sodium Extra", "Sodium için ek grafik ayarları"),
    ("krypton", "Krypton", "Çok oyunculu bağlantıyı hafifletir"),
]
FPS = {"status": "idle", "instance": None, "steps": [], "message": ""}
FPS_LOCK = threading.Lock()


def fps_snapshot():
    return {"status": FPS["status"], "instance": FPS["instance"], "message": FPS["message"],
            "steps": [dict(st) for st in FPS["steps"]]}


def fps_find_or_create():
    with DATA_LOCK:
        items = load_instances()
        for it in items:
            if it["name"] == FPS_NAME and it["mc_version"] == FPS_VERSION and it["loader"] == "fabric":
                return it
        inst = {"id": uuid.uuid4().hex[:10], "name": FPS_NAME, "mc_version": FPS_VERSION, "loader": "fabric",
                "ram": 4096, "color": 0, "created": time.time(), "last_played": 0}
        items.append(inst)
        write_json(INSTANCES_FILE, items)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves"):
        (instance_dir(inst) / sub).mkdir(parents=True, exist_ok=True)
    return inst


def fps_worker(inst):
    try:
        for st in FPS["steps"]:
            st["state"] = "installing"
            try:
                with INSTALL_LOCK:
                    res = install_project(inst, "mod", st["slug"])
                extra = [n for n in res["installed"] if n.lower() != st["title"].lower()]
                if res["skipped"]:
                    st.update(state="ok", detail="zaten kurulu")
                else:
                    st.update(state="ok", detail="kuruldu" + (f" (+ {', '.join(extra)})" if extra else ""))
            except ApiError as exc:
                if exc.code == 502 and "ulaşılamadı" in exc.msg:  # ağ yoksa boşuna devam etme
                    st.update(state="skip", detail=exc.msg)
                    FPS.update(status="error", message=exc.msg)
                    return
                st.update(state="skip", detail=exc.msg)
            except Exception as exc:
                st.update(state="skip", detail=str(exc))
        ok = sum(1 for st in FPS["steps"] if st["state"] == "ok")
        FPS.update(status="done", message=f"{ok} / {len(FPS['steps'])} mod hazır. "
                   + ("Hepsi kuruldu, oyna!" if ok == len(FPS["steps"]) else "Atlananların nedeni yukarıda yazıyor."))
        add_log(f"FPS BOOST: {ok} / {len(FPS['steps'])} mod hazır.")
    except Exception as exc:
        FPS.update(status="error", message=f"Beklenmeyen hata: {exc}")


@route("POST", "/fps-boost")
def r_fps_start(m, q, b):
    with FPS_LOCK:
        if FPS["status"] == "running":
            return fps_snapshot()
        inst = fps_find_or_create()
        FPS.update(status="running", instance=inst["id"], message="",
                   steps=[{"slug": s_, "title": t, "desc": d, "state": "pending", "detail": ""}
                          for s_, t, d in FPS_MODS])
    threading.Thread(target=fps_worker, args=(inst,), daemon=True).start()
    return fps_snapshot()


@route("GET", "/fps-boost")
def r_fps_status(m, q, b):
    return fps_snapshot()


THEME_NAMES = ("green", "blue", "purple", "pink", "orange")


@route("POST", "/theme")
def r_theme(m, q, b):
    theme = b.get("theme")
    if theme == "custom":
        color = str(b.get("color", ""))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ApiError("Geçersiz renk.")
        CFG["accent"] = color.lower()
    elif theme not in THEME_NAMES:
        raise ApiError("Geçersiz tema.")
    CFG["theme"] = theme
    save_cfg()
    return {"theme": theme, "accent": CFG.get("accent", "")}


@route("GET", "/diagnose")
def r_diagnose(m, q, b):
    return diagnose_network()


@route("GET", "/friends")
def r_friends(m, q, b):
    return {"friends": friends_list()}


@route("POST", "/friends")
def r_friends_add(m, q, b):
    name = str(b.get("name", "")).strip()
    if not re.fullmatch(r"\w{3,16}", name):
        raise ApiError("Minecraft kullanıcı adı 3-16 karakter olmalı (harf, rakam, _).")
    found, premium = None, False
    if not b.get("offline"):
        try:
            found, premium = mojang_lookup_uuid(name), True
        except ApiError as exc:
            if exc.code != 400:   # ağ hatası: kullanıcı "korsan" kutusunu işaretleyip ekleyebilir
                raise
    if not found:                 # Mojang'da yok = korsan/çevrimdışı hesap
        found = {"uuid": offline_uuid(name), "name": name}
    entry = {**found, "premium": premium, "offline_uuid": offline_uuid(found["name"])}
    items = friends_list()
    if any(f["uuid"] == entry["uuid"] for f in items):
        return {"friends": items, "added": False}
    items.append(entry)
    save_friends(items)
    return {"friends": items, "added": True, "premium": premium}


@route("POST", "/friends/remove")
def r_friends_remove(m, q, b):
    uuid_ = str(b.get("uuid", ""))
    items = [f for f in friends_list() if f["uuid"] != uuid_]
    save_friends(items)
    return {"friends": items}


# --------------------------------------------------------------------- Mesajlaşma
def chat_cfg():
    c = CFG.get("chat")
    return c if isinstance(c, dict) else {}


def chat_me():
    """Mesajlarda kullanılacak ad: Microsoft girişi varsa gerçek ad, yoksa çevrimdışı ad."""
    return account_info()["name"]


def chat_normalize_server(raw):
    raw = str(raw or "").strip().rstrip("/")
    if raw and "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ApiError("Sunucu adresi geçersiz. Örnek: http://192.168.1.20:8780")
    host = parsed.hostname
    # 0.0.0.0 / :: "dinleme adresi"dir, bağlanılacak adres değildir (WinError 10049). Aynı PC için 127.0.0.1 kullan.
    if host in ("0.0.0.0", "::", "0", "[::]"):
        host = "127.0.0.1"
    if ":" in host:  # IPv6
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def chat_call(method, path, body=None, user=None, timeout=10):
    c = chat_cfg()
    if not c.get("server"):
        raise ApiError("Mesaj sunucusu ayarlanmamış.")
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if c.get("password"):
        headers["X-Chat-Key"] = c["password"]
    if user:
        headers["X-Chat-User"] = user[0]
        headers["X-Chat-Token"] = user[1]
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(c["server"] + path, data=data, headers=headers, method=method)
    try:
        with open_url(req, timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read(2000).decode("utf-8", "replace")).get("error")
        except Exception:
            msg = None
        raise ApiError(msg or f"Mesaj sunucusu hatası ({exc.code}).", 502 if exc.code >= 500 else 400)
    except ValueError:
        raise ApiError("Adres bir Riven mesaj sunucusu gibi görünmüyor.", 502)
    except Exception as exc:
        raise ApiError(f"Mesaj sunucusuna ulaşılamadı: {explain_net_error(exc)}", 502)


def chat_user():
    """(ad, token). İlk kullanımda sunucuya kaydolur; token yalnızca bu bilgisayarda tutulur."""
    me = chat_me()
    c = chat_cfg()
    tokens = c.get("tokens") if isinstance(c.get("tokens"), dict) else {}
    token = tokens.get(me.lower())
    if not token:
        try:
            token = chat_call("POST", "/register", {"name": me})["token"]
        except ApiError as exc:
            if "zaten alınmış" in exc.msg:
                raise ApiError(f"\"{me}\" adı bu sunucuda zaten kayıtlı ve anahtarı bu bilgisayarda yok. "
                               "Hesap sayfasından başka bir ad kullan ya da sunucu sahibinden kaydı sildirmesini iste.")
            raise
        tokens[me.lower()] = token
        CFG["chat"] = {**c, "tokens": tokens}
        save_cfg()
    return me, token


def chat_status():
    c = chat_cfg()
    return {"configured": bool(c.get("server")), "server": c.get("server", ""),
            "has_password": bool(c.get("password")), "me": chat_me()}


@route("GET", "/chat/status")
def r_chat_status(m, q, b):
    return chat_status()


@route("POST", "/chat/setup")
def r_chat_setup(m, q, b):
    server = chat_normalize_server(b.get("server"))
    password = str(b.get("password", ""))[:100]
    old = chat_cfg()
    CFG["chat"] = {"server": server, "password": password,
                   "tokens": old.get("tokens", {}) if old.get("server") == server else {}}
    try:
        chat_call("GET", "/ping")
        chat_user()
    except ApiError:
        CFG["chat"] = old
        raise
    save_cfg()
    return chat_status()


@route("POST", "/chat/reset")
def r_chat_reset(m, q, b):
    CFG.pop("chat", None)
    save_cfg()
    return chat_status()


@route("GET", "/chat/poll")
def r_chat_poll(m, q, b):
    try:
        since = max(0, int(qs(q, "since", "0")))
    except ValueError:
        since = 0
    me, token = chat_user()
    data = chat_call("GET", f"/poll?since={since}", user=(me, token))
    friends = {f["name"].lower() for f in friends_list()}
    out, hidden = [], 0
    for msg in data.get("messages", []):
        other = msg["to"] if msg["from"].lower() == me.lower() else msg["from"]
        if other.lower() in friends:
            out.append({"id": msg["id"], "from": msg["from"], "to": msg["to"],
                        "text": str(msg["text"])[:500], "ts": msg["ts"]})
        else:
            hidden += 1
    return {"me": me, "messages": out, "hidden": hidden, "last_id": data.get("last_id", since)}


@route("POST", "/chat/send")
def r_chat_send(m, q, b):
    to = str(b.get("to", "")).strip()
    text = str(b.get("text", "")).strip()
    if not any(f["name"].lower() == to.lower() for f in friends_list()):
        raise ApiError("Önce bu kişiyi arkadaş olarak eklemelisin.")
    if not text:
        raise ApiError("Mesaj boş.")
    me, token = chat_user()
    return chat_call("POST", "/send", {"to": to, "text": text[:500]}, user=(me, token))


@route("POST", "/skin/upload")  # giriş ekranı ve eski arayüz: kütüphaneye ekler
def r_skin_upload(m, q, b):
    skin_add(b.get("name") or "Yüklenen skin", data_url_bytes(b.get("data_url")))
    return {"ok": True}


@route("POST", "/skin/reset")
def r_skin_reset(m, q, b):
    CFG["skin_active"] = None
    save_cfg()
    return {"ok": True}


# ------------------------------------------------------------- skin kütüphanesi
SKIN_LIB = HOME_DIR / "skin_library"
SKIN_INDEX = HOME_DIR / "skins.json"
MAX_SKINS = 60


def png_pixel_alpha(data, x, y):
    """8-bit RGBA, interlace'siz PNG'den tek pikselin alfa değeri. Desteklenmeyen biçimde None."""
    try:
        pos, idat = 8, b""
        w = h = depth = ctype = interlace = 0
        while pos + 8 <= len(data):
            ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + ln]
            pos += 12 + ln
            if typ == b"IHDR":
                w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            elif typ == b"IDAT":
                idat += body
            elif typ == b"IEND":
                break
        if (depth, ctype, interlace) != (8, 6, 0) or not (0 <= x < w and 0 <= y < h):
            return None
        raw = zlib.decompressobj().decompress(idat, w * h * 4 + h + 16)
        bpp, stride = 4, w * 4
        prev, i = bytearray(stride), 0
        for _ in range(y + 1):
            ftype = raw[i]
            line = bytearray(raw[i + 1:i + 1 + stride])
            i += 1 + stride
            for k in range(stride):
                a = line[k - bpp] if k >= bpp else 0
                up = prev[k]
                c = prev[k - bpp] if k >= bpp else 0
                if ftype == 1:
                    line[k] = (line[k] + a) & 255
                elif ftype == 2:
                    line[k] = (line[k] + up) & 255
                elif ftype == 3:
                    line[k] = (line[k] + ((a + up) >> 1)) & 255
                elif ftype == 4:
                    pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                    pred = a if (pa <= pb and pa <= pc) else (up if pb <= pc else c)
                    line[k] = (line[k] + pred) & 255
            prev = line
        return prev[x * 4 + 3]
    except Exception:
        return None


def skin_is_slim(data):
    """İnce kollu (Alex) skin: sağ kolun kullanılmayan sütunu (55,25) şeffaftır."""
    w, h = struct.unpack(">II", data[16:24])
    return h == 64 and png_pixel_alpha(data, 55, 25) == 0


def skin_validate(data):
    if not valid_png(data) or len(data) < 33:
        raise ApiError("Geçersiz PNG.")
    w, h = struct.unpack(">II", data[16:24])
    if w != 64 or h not in (32, 64):
        raise ApiError("Skin 64x64 (ya da eski 64x32) olmalı.")


def skins_load():
    items = read_json(SKIN_INDEX, [])
    return items if isinstance(items, list) else []


def skin_file(sid):
    if not isinstance(sid, str) or not re.fullmatch(r"[a-f0-9]{10}", sid):
        raise ApiError("Geçersiz skin.", 404)
    return SKIN_LIB / f"{sid}.png"


def skin_active_bytes():
    sid = CFG.get("skin_active")
    try:
        path = skin_file(sid) if sid else None
    except ApiError:
        return None
    return path.read_bytes() if path and path.is_file() else None


def skin_add(name, data, activate=True):
    skin_validate(data)
    name = (str(name or "").strip() or "Skin")[:24]
    digest = hashlib.sha1(data).hexdigest()
    with DATA_LOCK:
        items = skins_load()
        item = next((i for i in items if i.get("sha1") == digest), None)
        if not item:
            if len(items) >= MAX_SKINS:
                raise ApiError(f"Skin kütüphanesi dolu ({MAX_SKINS}). Birkaç skin sil.")
            item = {"id": uuid.uuid4().hex[:10], "name": name, "sha1": digest,
                    "slim": skin_is_slim(data), "added": time.time()}
            SKIN_LIB.mkdir(parents=True, exist_ok=True)
            skin_file(item["id"]).write_bytes(data)
            items.append(item)
            write_json(SKIN_INDEX, items)
        if activate:
            CFG["skin_active"] = item["id"]
            save_cfg()
    return item


def skins_public():
    active = CFG.get("skin_active")
    items = [{"id": i["id"], "name": i.get("name", "Skin"), "slim": bool(i.get("slim"))}
             for i in skins_load() if skin_file(i["id"]).is_file()]
    return {"items": items, "active": active if any(i["id"] == active for i in items) else None}


def migrate_skins():
    """Eski tek dosyalık özel skin'i kütüphaneye taşı."""
    try:
        if CFG.get("skin_custom") and CUSTOM_SKIN.is_file() and not skins_load():
            item = skin_add("Özel skin", CUSTOM_SKIN.read_bytes(), activate=True)
            add_log(f"Eski özel skin kütüphaneye taşındı ({item['id']}).")
        CFG.pop("skin_custom", None)
    except Exception as exc:
        add_log(f"Skin taşınamadı: {exc}")


def data_url_bytes(raw):
    raw = str(raw or "")
    if not raw.startswith("data:image/png;base64,"):
        raise ApiError("Skin bir PNG dosyası olmalı.")
    try:
        return base64.b64decode(raw.split(",", 1)[1], validate=True)
    except ValueError:
        raise ApiError("Geçersiz dosya.")


def mojang_upload_skin(data, slim):
    """Microsoft hesabının gerçek skin'ini değiştirir (oyunda herkes görür)."""
    if not ACCOUNT["data"]:
        raise ApiError("Bunun için Microsoft hesabıyla giriş yapmalısın.")
    auth = current_auth()
    boundary = "----riven" + secrets.token_hex(12)
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"variant\"\r\n\r\n"
            f"{'slim' if slim else 'classic'}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"skin.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode()
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://api.minecraftservices.com/minecraft/profile/skins", data=body, method="POST",
        headers={"Authorization": f"Bearer {auth['token']}", "User-Agent": UA,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with open_url(req, 30):
            pass
    except urllib.error.HTTPError as exc:
        hint = {401: "oturum süresi dolmuş olabilir, çıkış yapıp tekrar gir",
                403: "bu hesap Minecraft Services'e erişemiyor", 429: "çok sık denendi, biraz bekle"}.get(exc.code, "")
        raise ApiError(f"Mojang skin'i reddetti ({exc.code}){': ' + hint if hint else ''}.", 502)
    except Exception as exc:
        raise ApiError(f"Mojang'a ulaşılamadı: {explain_net_error(exc)}", 502)
    name = ACCOUNT["data"]["name"].lower()
    for ext in (".png", ".none"):
        (SKIN_DIR / f"{name}{ext}").unlink(missing_ok=True)


# ---------------------------------------------------------------------- CurseForge
CF_API = "https://api.curseforge.com/v1"
CF_GAME = 432                       # Minecraft
CF_CLASS = {"mod": 6, "resourcepack": 12, "shader": 6552, "modpack": 4471}
CF_FABRIC = 4                       # modLoaderType
CF_SORT = {"relevance": 1, "downloads": 6, "updated": 3, "newest": 11}
CF_DL_HOSTS = {"edge.forgecdn.net", "mediafilez.forgecdn.net", "media.forgecdn.net",
               "edge-service.forgecdn.net", "mediafiles.forgecdn.net"}
CF_IMG_HOSTS = {"media.forgecdn.net", "edge.forgecdn.net", "mediafilez.forgecdn.net"}
CF_KEYRING_USER = "curseforge_api_key"
# Kendi CurseForge anahtarını (console.curseforge.com) buraya yazarsan kullanıcıya hiç sorulmaz.
DEFAULT_CF_KEY = ""
MRPACK_HOSTS = {"cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com",
                "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
EXTERNAL_HOSTS = {"modrinth.com", "www.modrinth.com", "curseforge.com", "www.curseforge.com",
                  "console.curseforge.com"}


class ManualDownload(ApiError):
    """Yazar üçüncü taraf indirmesine izin vermiyor: dosya elle indirilmeli."""
    def __init__(self, title, url):
        super().__init__(f"{title}: yazar launcher'dan indirmeye izin vermiyor.")
        self.title, self.url = title, url


_CF_CACHE = {"loaded": False, "value": ""}


def cf_key():
    key = os.environ.get("RIVEN_CF_KEY") or DEFAULT_CF_KEY
    if key:
        return key
    if not _CF_CACHE["loaded"]:  # kimlik deposunu her istekte değil, bir kez oku
        value = ""
        if keyring is not None:
            try:
                value = keyring.get_password(KEYRING_SERVICE, CF_KEYRING_USER) or ""
            except Exception:
                value = ""
        _CF_CACHE.update(loaded=True, value=value or CFG.get("curseforge_key", ""))
    return _CF_CACHE["value"]


def cf_store_key(key):
    _CF_CACHE.update(loaded=True, value=key)
    CFG.pop("curseforge_key", None)
    if keyring is not None:
        try:
            if key:
                keyring.set_password(KEYRING_SERVICE, CF_KEYRING_USER, key)
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, CF_KEYRING_USER)
                except Exception:
                    pass
            save_cfg()
            return
        except Exception as exc:
            add_log(f"Anahtar kimlik deposuna yazılamadı, ayar dosyasına kaydedilecek: {exc}")
    if key:
        CFG["curseforge_key"] = key
    save_cfg()


def cf_clean_key(raw):
    """Yapıştırılan anahtarı temizler: boşluk, tırnak, 'x-api-key:' öneki, satır sonu."""
    key = str(raw or "").strip().strip("\"'`").strip()
    key = re.sub(r"^(x-api-key\s*[:=]\s*)", "", key, flags=re.I).strip().strip("\"'`")
    return "".join(key.split())


def cf_http_error(exc):
    """HTTPError -> anlaşılır ApiError. Gövdedeki gerçek sebebi de gösterir."""
    try:
        raw = exc.read(2000).decode("utf-8", "replace")
    except Exception:
        raw = ""
    detail = ""
    try:
        parsed = json.loads(raw)
        detail = str(parsed.get("error") or parsed.get("message") or raw)[:160]
    except Exception:
        if "cloudflare" in raw.lower() or "<html" in raw.lower():
            detail = "Cloudflare/güvenlik duvarı sayfası döndü"
        elif raw.strip():
            detail = raw.strip()[:160]
    try:
        server = exc.headers.get("Server") or ""
        ray = exc.headers.get("CF-RAY") or ""
        extra = ", ".join(x for x in (f"sunucu: {server}" if server else "", f"cf-ray: {ray}" if ray else "") if x)
        if extra:
            detail = (detail + " | " if detail else "") + extra
    except Exception:
        pass
    add_log(f"CurseForge HTTP {exc.code}: {detail or 'boş yanıt'}")
    if exc.code == 401:
        return ApiError("CurseForge API anahtarı geçersiz ya da eksik (401)." + (f" [{detail}]" if detail else ""))
    if exc.code == 403:
        if "cloudflare" in detail.lower():
            return ApiError(f"CurseForge isteği engelledi (403): {detail}. VPN/proxy/antivirüs HTTPS taramasını kapatıp dene.", 502)
        return ApiError("CurseForge isteği reddetti (403). Anahtar yanlış/iptal edilmiş olabilir ya da bu bağlantıdan "
                        "(VPN, ortak IP) CurseForge'a erişim engelleniyor." + (f" [{detail}]" if detail else ""))
    if exc.code == 404:
        return ApiError("CurseForge'da bulunamadı.", 404)
    if exc.code == 429:
        return ApiError("CurseForge çok fazla istek aldı, biraz bekleyip tekrar dene.", 502)
    return ApiError(f"CurseForge hatası ({exc.code})." + (f" [{detail}]" if detail else ""), 502)


def cf_request(path, params=None, body=None, timeout=25):
    key = cf_key()
    if not key:
        raise ApiError("CurseForge için API anahtarı gerekli. Hesap sayfasından ekleyebilirsin.")
    url = CF_API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    headers = {"x-api-key": key, "Accept": "application/json", "User-Agent": UA}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last = None
    browser_ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36")
    tried_browser = False
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with open_url(req, timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            last = cf_http_error(exc)
            if exc.code == 403 and not tried_browser:
                tried_browser = True  # bazı ağlar/WAF özel User-Agent'ı engeller
                headers = {**headers, "User-Agent": browser_ua, "Accept-Language": "en-US,en;q=0.9"}
                continue
            if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last
        except ValueError:
            # yarım kalan / bozuk yanıt çoğunlukla geçicidir: yeniden dene
            last = ApiError("CurseForge beklenmeyen bir yanıt verdi.", 502)
            if attempt < 3:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise last
        except Exception as exc:
            last = ApiError(f"CurseForge'a ulaşılamadı: {explain_net_error(exc)}", 502)
            if attempt < 3:  # zaman aşımı, bağlantı kopması, geçici DNS/TLS hataları
                add_log(f"CurseForge ağ hatası (deneme {attempt + 1}/4): {exc}")
                time.sleep(1.0 * (attempt + 1))
                continue
            raise last
    raise last


def cf_icon(proj):
    logo = proj.get("logo") or {}
    url = logo.get("thumbnailUrl") or logo.get("url")
    parsed = urllib.parse.urlparse(url or "")
    return url if parsed.scheme == "https" and parsed.hostname in CF_IMG_HOSTS else None


def cf_page_url(proj):
    url = (proj.get("links") or {}).get("websiteUrl") or ""
    parsed = urllib.parse.urlparse(url)
    return url if parsed.scheme == "https" and parsed.hostname in EXTERNAL_HOSTS else None


def cf_search(query, ptype, inst, offset, sort="", mc=""):
    sort = sort if sort in CF_SORT else "relevance"
    if sort == "relevance" and not query:
        sort = "downloads"
    offset = min(offset, 9980)
    params = {"gameId": CF_GAME, "classId": CF_CLASS[ptype], "pageSize": 20, "index": offset,
              "sortField": CF_SORT[sort], "sortOrder": "desc"}
    if query:
        params["searchFilter"] = query
    version = mc if ptype == "modpack" else (inst["mc_version"] if inst else "")
    if version:
        params["gameVersion"] = version
    if ptype in ("mod", "modpack"):
        params["modLoaderType"] = CF_FABRIC
    data = cf_request("/mods/search", params)
    add_log(f"CurseForge arama: sorgu='{query}' tür={ptype} sürüm={version or '-'} -> {len(data.get('data', []))} sonuç")
    if not data.get("data") and "modLoaderType" in params and offset == 0:
        # loader filtresi bazı sürümlerde sonuç vermiyor: filtreyi kaldırıp dene
        loose = {k: v for k, v in params.items() if k != "modLoaderType"}
        data = cf_request("/mods/search", loose)
        add_log(f"CurseForge arama (loader filtresiz): {len(data.get('data', []))} sonuç")
    installed = set()
    if inst and ptype in PTYPES:
        ctype = PTYPES[ptype]["key"]
        installed = {v.get("project_id") for k, v in load_index(inst).items() if k.startswith(ctype + "/")}
    hits = []
    for h in data.get("data", []):
        authors = h.get("authors") or [{}]
        hits.append({
            "project_id": str(h["id"]), "title": h.get("name", ""),
            "author": authors[0].get("name", ""), "description": h.get("summary", ""),
            "icon": cf_icon(h), "downloads": int(h.get("downloadCount") or 0),
            "installed": f"cf:{h['id']}" in installed, "url": cf_page_url(h),
            "categories": [str(c.get("name", "")) for c in (h.get("categories") or [])][:3],
        })
    total = (data.get("pagination") or {}).get("totalCount", len(hits))
    return {"hits": hits, "total": min(total, 10000), "offset": offset}


def cf_pick_file(mod_id, mc, fabric):
    def fetch(with_loader):
        params = {"gameVersion": mc, "pageSize": 50}
        if with_loader:
            params["modLoaderType"] = CF_FABRIC
        return [f for f in cf_request(f"/mods/{int(mod_id)}/files", params).get("data", [])
                if f.get("isAvailable", True)]

    files = fetch(fabric)
    if not files and fabric:  # bazı dosyalarda loader alanı boş; sürüm listesinden Fabric'i ara
        files = [f for f in fetch(False)
                 if any(str(v).lower() == "fabric" for v in (f.get("gameVersions") or []))]
    if not files:
        raise ApiError(f"Bu proje {mc} için uyumlu dosya sunmuyor.")
    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    releases = [f for f in files if f.get("releaseType") == 1]
    return (releases or files)[0]


def cf_download_url(file, mod_id):
    url = file.get("downloadUrl")
    if not url:
        try:
            url = cf_request(f"/mods/{int(mod_id)}/files/{int(file['id'])}/download-url").get("data")
        except ApiError as exc:
            add_log(f"CurseForge indirme adresi alınamadı ({file.get('fileName')}): {exc.msg}")
            url = None
    return url


def clean_filename(name, exts=None):
    """Harici dosya adını güvenli hale getirir (geçersiz karakterler _ olur)."""
    name = Path(str(name or "")).name
    name = re.sub(r"[^\w\-. +()\[\]]", "_", name).strip(". ")[:150]
    if not name or ".." in name or (exts and not name.lower().endswith(exts)):
        raise ApiError("Geçersiz dosya adı.")
    return name


def stream_download(url, tmp, hosts):
    """HTTPS indirme (adres ve yönlendirme sunucu listesi denetimli). Özet değerlerini döndürür."""
    parsed = urllib.parse.urlparse(str(url))
    if parsed.scheme != "https" or parsed.hostname not in hosts:
        raise ApiError("Beklenmeyen indirme adresi, reddedildi.")
    digests = {n: hashlib.new(n) for n in ("sha1", "sha512", "md5")}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with open_url(req, 60) as resp:
            final = urllib.parse.urlparse(resp.geturl())
            if final.scheme != "https" or final.hostname not in hosts:
                raise ApiError("İndirme beklenmeyen bir adrese yönlendirildi.")
            total = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise ApiError("Dosya çok büyük.")
                    fh.write(chunk)
                    for d in digests.values():
                        d.update(chunk)
    except (urllib.error.URLError, OSError) as exc:
        raise ApiError(f"İndirme başarısız: {explain_net_error(exc)}", 502)
    return {n: d.hexdigest() for n, d in digests.items()}


def cf_hash_ok(file, got):
    expected = {h.get("algo"): str(h.get("value", "")).lower() for h in file.get("hashes") or []}
    if 1 in expected:
        return expected[1] == got["sha1"]
    if 2 in expected:
        return expected[2] == got["md5"]
    return False


def cf_fetch_file(dest_dir, file, mod_id, title, page_url, exts):
    """CurseForge dosyasını indirip doğrular. İzin yoksa ManualDownload fırlatır."""
    fname = clean_filename(file.get("fileName"), exts)
    dest = dest_dir / fname
    if dest.exists() or (dest_dir / (fname + ".disabled")).exists():
        return fname
    url = cf_download_url(file, mod_id)
    if not url:
        raise ManualDownload(title, page_url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / (fname + ".part")
    try:
        got = stream_download(url, tmp, CF_DL_HOSTS)
        if not cf_hash_ok(file, got):
            raise ApiError("Dosya doğrulaması (hash) başarısız, silindi.")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return fname


def cf_install_one(inst, ptype, proj, file, installed, done, manual, depth=0):
    key = f"cf:{proj['id']}"
    if key in installed:
        return
    installed.add(key)
    spec = PTYPES[ptype]
    try:
        fname = cf_fetch_file(instance_dir(inst) / spec["dir"], file, proj["id"], proj.get("name", ""),
                              cf_page_url(proj), spec["ext"])
    except ManualDownload as exc:
        manual.append({"title": exc.title, "url": exc.url})
        return
    with DATA_LOCK:
        idx = load_index(inst)
        idx[f"{spec['key']}/{fname}"] = {
            "project_id": key, "title": proj.get("name", fname), "icon": cf_icon(proj),
            "version": str(file.get("displayName") or "")[:60] or None,
            "version_id": str(file.get("id") or "") or None}
        write_json(index_path(inst), idx)
    done.append(proj.get("name", fname))
    add_log(f"Kuruldu (CurseForge): {proj.get('name', fname)} ({fname})")
    if ptype == "mod" and depth < 4:
        for dep in file.get("dependencies") or []:
            dmod = dep.get("modId")
            if dep.get("relationType") != 3 or not isinstance(dmod, int) or f"cf:{dmod}" in installed:
                continue
            try:
                dproj = cf_request(f"/mods/{dmod}")["data"]
                dfile = cf_pick_file(dmod, inst["mc_version"], True)
                cf_install_one(inst, ptype, dproj, dfile, installed, done, manual, depth + 1)
            except ApiError as exc:
                add_log(f"Bağımlılık kurulamadı (CurseForge {dmod}): {exc.msg}")


def cf_install_project(inst, ptype, pid):
    proj = cf_request(f"/mods/{int(pid)}")["data"]
    ctype = PTYPES[ptype]["key"]
    installed = {v.get("project_id") for k, v in load_index(inst).items() if k.startswith(ctype + "/")}
    if f"cf:{proj['id']}" in installed:
        return {"installed": [], "skipped": True, "manual": []}
    file = cf_pick_file(proj["id"], inst["mc_version"], ptype == "mod")
    done, manual = [], []
    cf_install_one(inst, ptype, proj, file, installed, done, manual)
    return {"installed": done, "skipped": False, "manual": manual}


# ------------------------------------------------------------------- modpack kurulumu
JOB = {"state": "idle", "message": "", "progress": 0.0, "instance": None, "error": None,
       "manual": [], "failed": [], "name": ""}
JOB_LOCK = threading.Lock()


def job_update(**kw):
    JOB.update(kw)
    if "message" in kw:
        PROG["status"] = kw["message"]
    if "progress" in kw:
        PROG.update(value=int(kw["progress"] * 1000), max=1000)


def safe_join(base, rel):
    """Paket içindeki göreli yolu, base dışına çıkamayacak şekilde çözer."""
    rel = str(rel or "").replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if (not parts or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel)
            or any(p == ".." or ":" in p or "\x00" in p for p in parts)):
        raise ApiError("Pakette güvensiz bir dosya yolu var, reddedildi.")
    root = Path(base).resolve()
    target = root.joinpath(*parts).resolve()
    if root not in target.parents:
        raise ApiError("Pakette güvensiz bir dosya yolu var, reddedildi.")
    return target


def extract_overrides(zf, prefixes, dest):
    """Paketin overrides klasörlerini güvenli şekilde instance'a açar (sıra önemli: sonraki ezer)."""
    total = 0
    for prefix in prefixes:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(prefix) or info.is_dir():
                continue
            rel = name[len(prefix):]
            if not rel:
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                continue  # sembolik bağlantılar açılmaz
            target = safe_join(dest, rel)
            if target.suffix.lower() in BLOCKED_EXT:
                add_log(f"Güvenlik: çalıştırılabilir dosya atlandı ({rel})")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PACK_UNPACKED:
                        raise ApiError("Paket beklenenden çok büyük, kurulum durduruldu.")
                    out.write(chunk)


def run_downloads(tasks, label, workers=4):
    """tasks: [(başlık, çağrılabilir)]. Başarısız olanların açıklamalarını döndürür."""
    total, state, lock, failed = max(len(tasks), 1), {"n": 0}, threading.Lock(), []

    def wrap(item):
        title, fn = item
        try:
            fn()
        except ManualDownload as exc:
            with lock:
                JOB["manual"].append({"title": exc.title, "url": exc.url})
        except ApiError as exc:
            with lock:
                failed.append(f"{title}: {exc.msg}")
        except Exception as exc:
            with lock:
                failed.append(f"{title}: {exc}")
        finally:
            with lock:
                state["n"] += 1
                job_update(message=f"{label} ({state['n']}/{len(tasks)})",
                           progress=0.1 + 0.85 * state["n"] / total)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(wrap, tasks))
    return failed


def mr_pack_file_task(game_dir, entry):
    target = safe_join(game_dir, entry.get("path"))
    if target.suffix.lower() in BLOCKED_EXT:
        raise ApiError("güvensiz dosya türü atlandı")
    if target.exists():
        return
    hashes = entry.get("hashes") or {}
    urls = [u for u in entry.get("downloads") or [] if isinstance(u, str)]
    if not urls or not (hashes.get("sha512") or hashes.get("sha1")):
        raise ApiError("indirme adresi ya da hash bilgisi eksik")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    last = None
    for url in urls:
        try:
            got = stream_download(url, tmp, MRPACK_HOSTS)
            want, key = (hashes["sha512"], "sha512") if hashes.get("sha512") else (hashes["sha1"], "sha1")
            if want.lower() != got[key]:
                raise ApiError("hash doğrulaması başarısız")
            os.replace(tmp, target)
            return
        except ApiError as exc:
            last = exc
        finally:
            tmp.unlink(missing_ok=True)
    raise last


def sniff_image(raw):
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:4] == b"GIF8":
        return "image/gif"
    return None


def set_pack_icon(inst, url, hosts):
    """Modpack'in orijinal logosunu instance simgesi yapar (yüklenen resim gibi saklanır)."""
    if not url:
        return
    tmp = instance_dir(inst) / "icon.png.dl"
    try:
        stream_download(url, tmp, hosts)
        raw = tmp.read_bytes()
        if not raw or len(raw) > MAX_ICON_BYTES or not sniff_image(raw):
            return
        os.replace(tmp, instance_dir(inst) / "icon.png")
        with DATA_LOCK:
            items = load_instances()
            cur = next((i for i in items if i["id"] == inst["id"]), None)
            if cur:
                cur["custom_icon"] = True
                cur["icon_rev"] = cur.get("icon_rev", 0) + 1
                write_json(INSTANCES_FILE, items)
    except Exception as exc:
        add_log(f"Modpack simgesi alınamadı: {exc}")
    finally:
        tmp.unlink(missing_ok=True)


def pack_name(requested, fallback):
    name = (str(requested or "").strip() or str(fallback or "").strip() or "Modpack")[:32].strip()
    return name or "Modpack"


def install_mrpack(path, requested_name, fallback_name):
    with zipfile.ZipFile(path) as zf:
        try:
            index = json.loads(zf.read("modrinth.index.json"))
        except (KeyError, ValueError):
            raise ApiError("Geçersiz .mrpack dosyası (modrinth.index.json yok).")
        deps = index.get("dependencies") or {}
        mc = str(deps.get("minecraft", ""))
        if not re.fullmatch(r"[0-9A-Za-z._\-]{1,32}", mc):
            raise ApiError("Paketin Minecraft sürümü anlaşılamadı.")
        if any(k in deps for k in ("forge", "neoforge", "quilt-loader")):
            raise ApiError("Bu paket Forge/NeoForge/Quilt kullanıyor. Riven şimdilik yalnızca Fabric paketlerini kurar.")
        loader = "fabric" if "fabric-loader" in deps else "vanilla"
        entries = [e for e in index.get("files") or []
                   if isinstance(e, dict) and (e.get("env") or {}).get("client") != "unsupported"]
        inst = create_instance(pack_name(requested_name, index.get("name") or fallback_name), mc, loader,
                               color=random.randrange(8))
        JOB["instance"] = inst["id"]
        game_dir = instance_dir(inst)
        try:
            job_update(message="Dosyalar indiriliyor…", progress=0.1)
            tasks = [(Path(str(e.get("path"))).name, (lambda e=e: mr_pack_file_task(game_dir, e)))
                     for e in entries]
            failed = run_downloads(tasks, "Dosyalar indiriliyor")
            job_update(message="Ayar dosyaları açılıyor…", progress=0.96)
            extract_overrides(zf, ("overrides/", "client-overrides/"), game_dir)
        except BaseException:
            remove_instance(inst)
            raise
    JOB["failed"] = failed
    return inst


def mr_modpack_job(pid, name):
    job_update(message="Paket bilgisi alınıyor…", progress=0.02)
    proj = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}")
    versions = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}/version?"
                         + urllib.parse.urlencode({"loaders": json.dumps(["fabric"])}))
    if not versions:
        raise ApiError("Bu paket Fabric için sürüm sunmuyor. Riven şimdilik yalnızca Fabric paketlerini kurar.")
    version = ([v for v in versions if v.get("version_type") == "release"] or versions)[0]
    files = version.get("files") or []
    info = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not info or not str(info.get("filename", "")).lower().endswith(".mrpack"):
        raise ApiError("Pakette .mrpack dosyası bulunamadı.")
    tmp_dir = HOME_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex}.mrpack"
    try:
        job_update(message="Paket indiriliyor…", progress=0.05)
        got = stream_download(info.get("url", ""), tmp, MRPACK_HOSTS)
        want = (info.get("hashes") or {}).get("sha512")
        if not want or want.lower() != got["sha512"]:
            raise ApiError("Paket doğrulaması (hash) başarısız.")
        inst = install_mrpack(tmp, name, proj.get("title"))
        job_update(message="Simgeler ve mod bilgileri hazırlanıyor…", progress=0.98)
        set_pack_icon(inst, cdn_icon(proj.get("icon_url")), {"cdn.modrinth.com"})
        identify_unindexed(inst)
        return inst
    except zipfile.BadZipFile:
        raise ApiError("Paket dosyası bozuk.")
    finally:
        tmp.unlink(missing_ok=True)


CF_CLASS_DIR = {6: ("mods", (".jar",)), 12: ("resourcepacks", (".zip",)), 6552: ("shaderpacks", (".zip",))}


def cf_modpack_job(pid, name):
    job_update(message="Paket bilgisi alınıyor…", progress=0.02)
    proj = cf_request(f"/mods/{int(pid)}")["data"]
    page = cf_page_url(proj)
    files = [f for f in cf_request(f"/mods/{int(pid)}/files", {"pageSize": 30}).get("data", [])
             if f.get("isAvailable", True) and "Fabric" in (f.get("gameVersions") or [])]
    if not files:
        raise ApiError("Bu paket Fabric için sürüm sunmuyor. Riven şimdilik yalnızca Fabric paketlerini kurar.")
    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    pack = ([f for f in files if f.get("releaseType") == 1] or files)[0]
    url = cf_download_url(pack, pid)
    if not url:
        JOB["manual"].append({"title": proj.get("name", "Modpack"), "url": page})
        raise ApiError("Bu paketin yazarı launcher'lardan indirmeye izin vermiyor. Sayfasından elle indirebilirsin.")
    tmp_dir = HOME_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex}.zip"
    try:
        job_update(message="Paket indiriliyor…", progress=0.05)
        got = stream_download(url, tmp, CF_DL_HOSTS)
        if not cf_hash_ok(pack, got):
            raise ApiError("Paket doğrulaması (hash) başarısız.")
        with zipfile.ZipFile(tmp) as zf:
            try:
                man = json.loads(zf.read("manifest.json"))
            except (KeyError, ValueError):
                raise ApiError("Geçersiz paket (manifest.json yok).")
            mcinfo = man.get("minecraft") or {}
            mc = str(mcinfo.get("version", ""))
            if not re.fullmatch(r"[0-9A-Za-z._\-]{1,32}", mc):
                raise ApiError("Paketin Minecraft sürümü anlaşılamadı.")
            loaders = mcinfo.get("modLoaders") or []
            primary = str(next((l.get("id") for l in loaders if l.get("primary")),
                               loaders[0].get("id") if loaders else ""))
            if primary and not primary.startswith("fabric-"):
                raise ApiError("Bu paket Fabric dışı bir loader kullanıyor. Riven şimdilik yalnızca Fabric paketlerini kurar.")
            refs = [(int(f["projectID"]), int(f["fileID"])) for f in man.get("files") or []
                    if isinstance(f, dict) and str(f.get("projectID", "")).isdigit()
                    and str(f.get("fileID", "")).isdigit()]
            inst = create_instance(pack_name(name, man.get("name") or proj.get("name")), mc,
                                   "fabric" if primary else "vanilla", color=random.randrange(8))
            JOB["instance"] = inst["id"]
            game_dir = instance_dir(inst)
            try:
                job_update(message="Dosya listesi çözülüyor…", progress=0.08)
                file_ids = list({fid for _, fid in refs})
                mod_ids = list({mid for mid, _ in refs})
                fmap, mmap = {}, {}
                for i in range(0, len(file_ids), 100):
                    for f in cf_request("/mods/files", body={"fileIds": file_ids[i:i + 100]}).get("data", []):
                        fmap[f["id"]] = f
                for i in range(0, len(mod_ids), 100):
                    for mdl in cf_request("/mods", body={"modIds": mod_ids[i:i + 100]}).get("data", []):
                        mmap[mdl["id"]] = mdl
                tasks, cf_meta = [], []
                CKEY = {"mods": "mods", "resourcepacks": "resourcepacks", "shaderpacks": "shaders"}

                def cf_task(f, mid, title, mdl, folder, exts):
                    fname = cf_fetch_file(game_dir / folder, f, mid, title, cf_page_url(mdl), exts)
                    cf_meta.append((f"{CKEY[folder]}/{fname}", {
                        "project_id": f"cf:{mid}", "title": mdl.get("name") or fname, "icon": cf_icon(mdl),
                        "version": str(f.get("displayName") or "")[:60] or None,
                        "version_id": str(f.get("id") or "") or None}))

                for mid, fid in refs:
                    f, mdl = fmap.get(fid), mmap.get(mid, {})
                    title = mdl.get("name") or f"Dosya {fid}"
                    if not f:
                        tasks.append((title, missing_file))
                        continue
                    folder, exts = CF_CLASS_DIR.get(mdl.get("classId"), ("mods", (".jar",)))
                    tasks.append((title, (lambda f=f, mid=mid, title=title, mdl=mdl, folder=folder, exts=exts:
                                          cf_task(f, mid, title, mdl, folder, exts))))
                failed = run_downloads(tasks, "Dosyalar indiriliyor")
                with DATA_LOCK:
                    idx = load_index(inst)
                    idx.update(dict(cf_meta))
                    write_json(index_path(inst), idx)
                job_update(message="Ayar dosyaları açılıyor…", progress=0.96)
                prefix = str(man.get("overrides") or "overrides").strip("/\\") + "/"
                extract_overrides(zf, (prefix,), game_dir)
            except BaseException:
                remove_instance(inst)
                raise
        job_update(message="Simgeler ve mod bilgileri hazırlanıyor…", progress=0.98)
        set_pack_icon(inst, cf_icon(proj), CF_IMG_HOSTS)
        identify_unindexed(inst)
        JOB["failed"] = failed
        return inst
    except zipfile.BadZipFile:
        raise ApiError("Paket dosyası bozuk.")
    finally:
        tmp.unlink(missing_ok=True)


def missing_file():
    raise ApiError("dosya CurseForge'da bulunamadı")


def run_job(fn, *args):
    try:
        inst = fn(*args)
        job_update(state="done", message="Paket kuruldu", progress=1.0)
        JOB["instance"] = inst["id"]
        add_log(f"Modpack kuruldu: {inst['name']} ({len(JOB['manual'])} elle indirme, {len(JOB['failed'])} hata)")
    except ApiError as exc:
        JOB.update(state="error", error=exc.msg, instance=None)
        add_log(f"Modpack kurulamadı: {exc.msg}")
    except Exception as exc:
        traceback.print_exc()
        JOB.update(state="error", error=f"Beklenmeyen hata: {exc}", instance=None)
        add_log(f"Modpack kurulamadı: {exc}")
    finally:
        if not RUNNING and PREPARING["id"] is None:
            PROG.update(status="Hazır", value=0, max=1)


def start_job(fn, *args):
    with JOB_LOCK:
        if JOB["state"] == "running":
            raise ApiError("Başka bir paket kuruluyor, bitmesini bekle.")
        JOB.update(state="running", message="Başlıyor…", progress=0.0, instance=None, error=None,
                   manual=[], failed=[])
    threading.Thread(target=run_job, args=(fn,) + args, daemon=True).start()


# ------------------------------------------------------------------------ rotalar
@route("GET", "/skins")
def r_skins(m, q, b):
    return skins_public()


@route("POST", "/skins/add")
def r_skins_add(m, q, b):
    item = skin_add(b.get("name"), data_url_bytes(b.get("data_url")))
    return {**skins_public(), "added": item["id"]}


@route("POST", "/skins/import")
def r_skins_import(m, q, b):
    name = str(b.get("username", "")).strip()
    if not re.fullmatch(r"\w{3,16}", name):
        raise ApiError("Oyuncu adı 3-16 karakter olmalı (harf, rakam, _).")
    for ext in (".png", ".none"):  # önbelleği atla, güncel skin'i çek
        (SKIN_DIR / f"{name.lower()}{ext}").unlink(missing_ok=True)
    data = fetch_skin(name)
    if not data:
        raise ApiError(f"\"{name}\" için skin alınamadı (premium hesap değil ya da Mojang'a ulaşılamıyor).")
    item = skin_add(name, data)
    return {**skins_public(), "added": item["id"]}


@route("POST", "/skins/select")
def r_skins_select(m, q, b):
    sid = b.get("id")
    if sid is not None and not skin_file(sid).is_file():
        raise ApiError("Skin bulunamadı.", 404)
    CFG["skin_active"] = sid
    save_cfg()
    return skins_public()


@route("POST", "/skins/delete")
def r_skins_delete(m, q, b):
    sid = b.get("id")
    path = skin_file(sid)
    with DATA_LOCK:
        write_json(SKIN_INDEX, [i for i in skins_load() if i["id"] != sid])
        path.unlink(missing_ok=True)
        if CFG.get("skin_active") == sid:
            CFG["skin_active"] = None
            save_cfg()
    return skins_public()


@route("POST", "/skins/apply")
def r_skins_apply(m, q, b):
    sid = b.get("id")
    path = skin_file(sid)
    if not path.is_file():
        raise ApiError("Skin bulunamadı.", 404)
    data = path.read_bytes()
    mojang_upload_skin(data, skin_is_slim(data))
    return {"ok": True}


@route("POST", "/open-external")
def r_open_external(m, q, b):
    url = str(b.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in EXTERNAL_HOSTS:
        raise ApiError("Bu adres açılamaz.")
    webbrowser.open(url)
    return {"ok": True}


@route("GET", "/curseforge/status")
def r_cf_status(m, q, b):
    return {"configured": bool(cf_key()), "baked": bool(DEFAULT_CF_KEY or os.environ.get("RIVEN_CF_KEY")),
            "keyring": keyring is not None}


@route("POST", "/curseforge/key")
def r_cf_key(m, q, b):
    key = cf_clean_key(b.get("key", ""))
    if key and not re.fullmatch(r"[\w$./+=\-]{20,250}", key):
        raise ApiError("Anahtar geçersiz görünüyor. console.curseforge.com adresindeki API Keys bölümünden kopyala.")
    previous = cf_key()
    cf_store_key(key)
    if key:
        try:
            cf_request(f"/games/{CF_GAME}")  # anahtarı gerçekten dene
        except ApiError:
            cf_store_key(previous)
            raise
    return r_cf_status(m, q, b)


@route("GET", "/curseforge/search")
def r_cf_search(m, q, b):
    ptype = qs(q, "type", "mod")
    if ptype not in CF_CLASS:
        raise ApiError("Geçersiz tür.")
    inst = get_instance(valid_id(qs(q, "instance"))) if qs(q, "instance") else None
    mc = qs(q, "mc")
    if mc and not re.fullmatch(r"[0-9A-Za-z._\-]{1,32}", mc):
        raise ApiError("Geçersiz sürüm.")
    try:
        offset = max(0, int(qs(q, "offset", "0")))
    except ValueError:
        offset = 0
    return cf_search(qs(q, "q")[:80], ptype, inst, offset, qs(q, "sort"), mc)


@route("POST", "/curseforge/install")
def r_cf_install(m, q, b):
    inst = get_instance(valid_id(b.get("instance")))
    ptype = b.get("type", "mod")
    if ptype not in PTYPES:
        raise ApiError("Geçersiz tür.")
    if ptype == "mod" and inst["loader"] != "fabric":
        raise ApiError(f"{loaderlabel(inst['loader'])} instance'a mod kurulamaz.")
    pid = str(b.get("project_id", ""))
    if not re.fullmatch(r"\d{1,10}", pid):
        raise ApiError("Geçersiz proje.")
    with INSTALL_LOCK:
        return cf_install_project(inst, ptype, pid)


# ------------------------------------------------------------------- proje detay sayfası
CF_CLASS_TYPE = {v: k for k, v in CF_CLASS.items()}
CF_RELEASE = {1: "release", 2: "beta", 3: "alpha"}


def src_pid(source, pid):
    if source == "modrinth":
        return project_id_ok(pid)
    if source == "curseforge":
        pid = str(pid)
        if not re.fullmatch(r"\d{1,10}", pid):
            raise ApiError("Geçersiz proje.")
        return pid
    raise ApiError("Geçersiz kaynak.")


def index_project_id(source, pid):
    return pid if source == "modrinth" else f"cf:{pid}"


def installed_entry(inst, ptype, source, pid):
    """Projenin bu instance'ta kurulu dosyası: {filename, enabled, version, version_id} ya da None."""
    ctype = PTYPES[ptype]["key"]
    want = index_project_id(source, pid)
    folder = content_dir(inst, ctype)
    for k, v in load_index(inst).items():
        if not k.startswith(ctype + "/") or v.get("project_id") != want:
            continue
        fname = k.split("/", 1)[1]
        if (folder / fname).exists():
            enabled = True
        elif (folder / (fname + ".disabled")).exists():
            enabled = False
        else:
            continue
        return {"filename": fname, "enabled": enabled, "version": v.get("version"),
                "version_id": v.get("version_id")}
    return None


def mc_only(versions):
    out = [str(v) for v in (versions or []) if re.fullmatch(r"\d+(\.\d+)*[\w.\-]*", str(v)) and str(v)[0].isdigit()]
    return out[:6]


PROJ_CACHE = {}          # (kaynak, id, mc, tür) -> (zaman, bilgi)
PROJ_TTL = 180
POOL = ThreadPoolExecutor(max_workers=8)


def mr_versions(pid, inst, ptype):
    params = {"game_versions": json.dumps([inst["mc_version"]])}
    if ptype == "mod":
        params["loaders"] = json.dumps(["fabric"])
    raw = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}/version?" + urllib.parse.urlencode(params))
    out = []
    for v in raw[:60]:
        files = v.get("files") or []
        info = next((f for f in files if f.get("primary")), files[0] if files else {})
        out.append({"id": v.get("id"), "name": v.get("name") or v.get("version_number"),
                    "number": v.get("version_number"), "type": v.get("version_type", "release"),
                    "mc": mc_only(v.get("game_versions")), "date": v.get("date_published"),
                    "filename": info.get("filename"), "downloads": v.get("downloads", 0)})
    return out


def mr_author(pid):
    try:
        members = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}/members")
        owner = next((m for m in members if m.get("role") == "Owner"), members[0] if members else {})
        return (owner.get("user") or {}).get("username", "")
    except ApiError:
        return ""


def mr_project_info(pid, inst, hint="mod"):
    # proje, yapımcı ve sürümler aynı anda istenir (sırayla beklemek yerine)
    f_proj = POOL.submit(http_json, f"{MODRINTH}/project/{urllib.parse.quote(pid)}")
    f_auth = POOL.submit(mr_author, pid)
    f_ver = POOL.submit(mr_versions, pid, inst, hint) if inst and hint in PTYPES else None
    proj = f_proj.result()
    ptype = proj.get("project_type") or "mod"
    slug = str(proj.get("slug") or "")
    url = f"https://modrinth.com/{ptype}/{slug}" if re.fullmatch(r"[\w\-]{1,80}", slug) else None
    versions = []
    if ptype in PTYPES and inst:
        versions = f_ver.result() if (f_ver and hint == ptype) else mr_versions(pid, inst, ptype)
    gallery = [g["url"] for g in (proj.get("gallery") or [])
               if isinstance(g.get("url"), str) and g["url"].startswith("https://cdn.modrinth.com/")][:8]
    return {"type": ptype, "title": proj.get("title", ""), "author": f_auth.result(),
            "icon": cdn_icon(proj.get("icon_url")), "summary": proj.get("description", ""),
            "body": proj.get("body", ""), "body_format": "markdown", "url": url,
            "downloads": proj.get("downloads", 0), "followers": proj.get("followers", 0),
            "categories": [str(c) for c in (proj.get("categories") or [])][:6],
            "gallery": gallery, "versions": versions}


def cf_list_files(mod_id, mc, fabric):
    def fetch(with_loader):
        params = {"gameVersion": mc, "pageSize": 60}
        if with_loader:
            params["modLoaderType"] = CF_FABRIC
        return [f for f in cf_request(f"/mods/{int(mod_id)}/files", params).get("data", [])
                if f.get("isAvailable", True)]

    files = fetch(fabric)
    if not files and fabric:
        files = [f for f in fetch(False)
                 if any(str(v).lower() == "fabric" for v in (f.get("gameVersions") or []))]
    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    return files


def cf_description(pid):
    try:
        return cf_request(f"/mods/{int(pid)}/description").get("data") or ""
    except ApiError as exc:
        add_log(f"CurseForge açıklaması alınamadı: {exc.msg}")
        return ""


def cf_versions(pid, inst, ptype):
    out = []
    for f in cf_list_files(pid, inst["mc_version"], ptype == "mod")[:60]:
        out.append({"id": str(f["id"]), "name": f.get("displayName") or f.get("fileName"),
                    "number": f.get("fileName"), "type": CF_RELEASE.get(f.get("releaseType"), "release"),
                    "mc": mc_only(f.get("gameVersions")), "date": f.get("fileDate"),
                    "filename": f.get("fileName"), "downloads": int(f.get("downloadCount") or 0),
                    "restricted": not f.get("downloadUrl")})
    return out


def cf_project_info(pid, inst, hint="mod"):
    f_proj = POOL.submit(lambda: cf_request(f"/mods/{int(pid)}")["data"])
    f_desc = POOL.submit(cf_description, pid)
    f_ver = POOL.submit(cf_versions, pid, inst, hint) if inst and hint in PTYPES else None
    proj = f_proj.result()
    ptype = CF_CLASS_TYPE.get(proj.get("classId"), "mod")
    versions = []
    if ptype in PTYPES and inst:
        versions = f_ver.result() if (f_ver and hint == ptype) else cf_versions(pid, inst, ptype)
    shots = []
    for sc in proj.get("screenshots") or []:
        u = sc.get("url") or ""
        if urllib.parse.urlparse(u).scheme == "https":
            shots.append(u)
    authors = proj.get("authors") or [{}]
    return {"type": ptype, "title": proj.get("name", ""), "author": authors[0].get("name", ""),
            "icon": cf_icon(proj), "summary": proj.get("summary", ""), "body": f_desc.result(), "body_format": "html",
            "url": cf_page_url(proj), "downloads": int(proj.get("downloadCount") or 0),
            "followers": int(proj.get("thumbsUpCount") or 0),
            "categories": [str(c.get("name", "")) for c in (proj.get("categories") or [])][:6],
            "gallery": shots[:8], "versions": versions}


@route("GET", "/project/info")
def r_project_info(m, q, b):
    source = qs(q, "source")
    pid = src_pid(source, qs(q, "id"))
    inst = get_instance(valid_id(qs(q, "instance"))) if qs(q, "instance") else None
    hint = qs(q, "type", "mod")
    key = (source, pid, inst["mc_version"] if inst else "", hint)
    now = time.time()
    hit = PROJ_CACHE.get(key)
    if hit and now - hit[0] < PROJ_TTL:
        info = dict(hit[1])
    else:
        info = mr_project_info(pid, inst, hint) if source == "modrinth" else cf_project_info(pid, inst, hint)
        if len(PROJ_CACHE) > 200:
            PROJ_CACHE.clear()
        PROJ_CACHE[key] = (now, info)
        info = dict(info)
    # kurulu durumu önbelleğe girmez: her seferinde taze okunur
    info.update({"source": source, "project_id": pid, "installed": None, "instance": None})
    if inst:
        info["instance"] = {"id": inst["id"], "name": inst["name"], "mc_version": inst["mc_version"],
                            "loader": inst["loader"]}
        if info["type"] in PTYPES:
            info["installed"] = installed_entry(inst, info["type"], source, pid)
    return info


def replace_old_file(inst, ptype, old, new_fname):
    """Yeni sürüm indikten sonra eski dosyayı kaldırır; eski kapalıysa yeni de kapalı kalır."""
    if not old or old["filename"] == new_fname:
        return
    ctype = PTYPES[ptype]["key"]
    folder = content_dir(inst, ctype)
    with DATA_LOCK:
        if not old["enabled"] and (folder / new_fname).exists():
            (folder / new_fname).rename(folder / (new_fname + ".disabled"))
        for p in (folder / old["filename"], folder / (old["filename"] + ".disabled")):
            p.unlink(missing_ok=True)
        idx = load_index(inst)
        idx.pop(f"{ctype}/{old['filename']}", None)
        write_json(index_path(inst), idx)


def mr_set_version(inst, ptype, pid, vid):
    version = http_json(f"{MODRINTH}/version/{urllib.parse.quote(vid)}")
    if version.get("project_id") != pid:
        raise ApiError("Bu sürüm bu projeye ait değil.")
    if inst["mc_version"] not in (version.get("game_versions") or []):
        raise ApiError(f"Bu sürüm Minecraft {inst['mc_version']} ile uyumlu değil.")
    if ptype == "mod" and "fabric" not in (version.get("loaders") or []):
        raise ApiError("Bu sürüm Fabric desteklemiyor.")
    files = version.get("files") or []
    if not files:
        raise ApiError("Sürümde dosya yok.")
    info = next((f for f in files if f.get("primary")), files[0])
    new_fname = safe_filename(info.get("filename"), PTYPES[ptype]["ext"])
    old = installed_entry(inst, ptype, "modrinth", pid)
    proj = http_json(f"{MODRINTH}/project/{urllib.parse.quote(pid)}")
    ctype = PTYPES[ptype]["key"]
    others = {v.get("project_id") for k, v in load_index(inst).items() if k.startswith(ctype + "/")} - {pid}
    done = []
    install_version(inst, ptype, version, proj, others, done)
    replace_old_file(inst, ptype, old, new_fname)
    return {"installed": done, "manual": [], "replaced": bool(old), "filename": new_fname}


def cf_set_version(inst, ptype, pid, fid):
    proj = cf_request(f"/mods/{int(pid)}")["data"]
    file = cf_request(f"/mods/{int(pid)}/files/{int(fid)}")["data"]
    if str(file.get("modId")) != str(pid):
        raise ApiError("Bu sürüm bu projeye ait değil.")
    if inst["mc_version"] not in (file.get("gameVersions") or []):
        raise ApiError(f"Bu sürüm Minecraft {inst['mc_version']} ile uyumlu değil.")
    ctype = PTYPES[ptype]["key"]
    key = f"cf:{pid}"
    others = {v.get("project_id") for k, v in load_index(inst).items() if k.startswith(ctype + "/")} - {key}
    old = installed_entry(inst, ptype, "curseforge", pid)
    done, manual = [], []
    cf_install_one(inst, ptype, proj, file, others, done, manual)
    if manual:
        return {"installed": [], "manual": manual, "replaced": False}
    new_fname = clean_filename(file.get("fileName"), PTYPES[ptype]["ext"])
    replace_old_file(inst, ptype, old, new_fname)
    return {"installed": done, "manual": [], "replaced": bool(old), "filename": new_fname}


@route("POST", "/project/version")
def r_project_version(m, q, b):
    """Belirli bir sürümü kurar; proje zaten kuruluysa eski dosyanın yerine geçirir."""
    source = b.get("source")
    pid = src_pid(source, b.get("project_id"))
    inst = get_instance(valid_id(b.get("instance")))
    ptype = b.get("type", "mod")
    if ptype not in PTYPES:
        raise ApiError("Geçersiz tür.")
    if ptype == "mod" and inst["loader"] != "fabric":
        raise ApiError(f"{loaderlabel(inst['loader'])} instance'a mod kurulamaz.")
    vid = str(b.get("version_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", vid):
        raise ApiError("Geçersiz sürüm.")
    if source == "curseforge" and not vid.isdigit():
        raise ApiError("Geçersiz sürüm.")
    with INSTALL_LOCK:
        return mr_set_version(inst, ptype, pid, vid) if source == "modrinth" else cf_set_version(inst, ptype, pid, vid)


@route("POST", "/open-link")
def r_open_link(m, q, b):
    """Proje açıklamalarındaki dış bağlantılar için (yalnızca https, kullanıcı tıklamasıyla)."""
    url = str(b.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or len(url) > 2000 or parsed.username or parsed.password:
        raise ApiError("Bu adres açılamaz.")
    webbrowser.open(url)
    return {"ok": True}


@route("POST", "/modpack/install")
def r_modpack_install(m, q, b):
    source, pid = b.get("source"), str(b.get("project_id", ""))
    name = str(b.get("name", "")).strip()[:32]
    if source == "modrinth":
        start_job(mr_modpack_job, project_id_ok(pid), name)
    elif source == "curseforge":
        if not re.fullmatch(r"\d{1,10}", pid):
            raise ApiError("Geçersiz proje.")
        if not cf_key():
            raise ApiError("CurseForge için API anahtarı gerekli.")
        start_job(cf_modpack_job, pid, name)
    else:
        raise ApiError("Geçersiz kaynak.")
    return {"started": True}


@route("GET", "/modpack/status")
def r_modpack_status(m, q, b):
    return dict(JOB)


def discord_status():
    return {**discord_cfg(), "connected": RPC.connected, "error": RPC.error}


@route("GET", "/discord")
def r_discord_get(m, q, b):
    return discord_status()


@route("POST", "/discord")
def r_discord_set(m, q, b):
    cid = str(b.get("client_id", "")).strip()
    if cid and not re.fullmatch(r"\d{15,22}", cid):
        raise ApiError("Application ID sadece rakamlardan oluşur (15-22 hane).")
    CFG["discord"] = {"enabled": bool(b.get("enabled")), "client_id": cid,
                      "show_name": bool(b.get("show_name"))}
    save_cfg()
    RPC.close()
    RPC.last_try = RPC.last_send = 0.0
    RPC.error = "Bağlanılıyor…"
    return discord_status()


# --------------------------------------------------------------------- HTTP sunucu
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self' "
                                "'unsafe-inline'; img-src 'self' https: data:; "
                                "media-src 'self'; "
                                "connect-src 'self'; base-uri 'none'; form-action 'none'; "
                                "frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
STATIC = {"/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/extras.js": ("extras.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/favicon-32.png": ("favicon-32.png", "image/png"),
          "/favicon-180.png": ("favicon-180.png", "image/png"),
          "/favicon-512.png": ("favicon-512.png", "image/png")}


class Handler(BaseHTTPRequestHandler):
    server_version = "Riven"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_video(self, path):
        """Giriş videosu: tarayıcı döngü/atlama için Range ister, 206 ile yanıtla."""
        f = WEB_DIR / path.lstrip("/")
        if not f.is_file():
            return self._json(404, {"error": "Bulunamadı."})
        size = f.stat().st_size
        ctype = "video/webm" if f.suffix == ".webm" else "video/mp4"
        start, end, code = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            with open(f, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _host_ok(self):
        port = SERVER["port"]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _handle(self, method):
        if not self._host_ok():
            return self._json(403, {"error": "Yasak."})
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)

        if method == "GET" and path == "/":
            html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            return self._send(200, html.replace("__RIVEN_TOKEN__", SERVER["token"]).encode(),
                              "text/html; charset=utf-8")
        if method == "GET" and path in STATIC:
            fname, ctype = STATIC[path]
            return self._send(200, (WEB_DIR / fname).read_bytes(), ctype)
        if method == "GET" and path in ("/intro.mp4", "/intro.webm"):
            return self._send_video(path)
        if method == "GET" and path == "/favicon.ico":
            ico = BASE_DIR / "riven.ico"
            if not ico.is_file():
                return self._json(404, {"error": "Bulunamadı."})
            return self._send(200, ico.read_bytes(), "image/x-icon")
        skin_match = re.fullmatch(r"/skin/(\w{3,16})\.png", path)
        if method == "GET" and skin_match:
            data = skin_active_bytes() or fetch_skin(skin_match.group(1))
            if not data:
                return self._json(404, {"error": "Skin yok."})
            return self._send(200, data, "image/png")
        lib_match = re.fullmatch(r"/skinlib/([a-f0-9]{10})\.png", path)
        if method == "GET" and lib_match:
            lib_path = skin_file(lib_match.group(1))
            if not lib_path.is_file():
                return self._json(404, {"error": "Skin yok."})
            return self._send(200, lib_path.read_bytes(), "image/png")
        icon_match = re.fullmatch(r"/instance-icon/([a-f0-9]{10})\.png", path)
        if method == "GET" and icon_match:
            try:
                inst = get_instance(icon_match.group(1))
            except ApiError:
                return self._json(404, {"error": "Bulunamadı."})
            icon_path = instance_dir(inst) / "icon.png"
            if not inst.get("custom_icon") or not icon_path.is_file():
                return self._json(404, {"error": "Bulunamadı."})
            raw = icon_path.read_bytes()
            return self._send(200, raw, sniff_image(raw) or "image/png")
        ci = re.fullmatch(r"/content-icon/([a-f0-9]{10})/(mods|resourcepacks|shaders)/([^/]+)", path)
        if method == "GET" and ci:
            try:
                inst = get_instance(ci.group(1))
                fname = loose_filename(urllib.parse.unquote(ci.group(3)), CTYPES[ci.group(2)][1]["ext"])
                target = content_file(inst, ci.group(2), fname)
                member = local_meta(target, ci.group(2)).get("icon_member") if target else None
                if not member:
                    raise ApiError("Yok", 404)
                with zipfile.ZipFile(target) as zf:
                    info = zf.getinfo(member)
                    if info.file_size > MAX_ICON_BYTES:
                        raise ApiError("Büyük", 404)
                    raw = zf.read(info)
                mime = sniff_image(raw)
                if not mime:
                    raise ApiError("Yok", 404)
            except (ApiError, KeyError, zipfile.BadZipFile, OSError):
                return self._json(404, {"error": "Bulunamadı."})
            return self._send(200, raw, mime)
        if not path.startswith("/api/"):
            return self._json(404, {"error": "Bulunamadı."})

        token = self.headers.get("X-Riven-Token", "")
        if not secrets.compare_digest(token, SERVER["token"]):
            return self._json(403, {"error": "Yetkisiz."})

        body = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                return self._json(413, {"error": "İstek çok büyük."})
            if length:
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json(400, {"error": "Geçersiz JSON."})

        api_path = path[4:]
        for rmethod, pattern, fn in ROUTES:
            match = pattern.match(api_path)
            if rmethod == method and match:
                try:
                    return self._json(200, fn(match, query, body if isinstance(body, dict) else {}))
                except ApiError as exc:
                    return self._json(exc.code, {"error": exc.msg})
                except Exception as exc:
                    traceback.print_exc()
                    return self._json(500, {"error": f"Beklenmeyen hata: {exc}"})
        return self._json(404, {"error": "Bulunamadı."})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def brand_window(title, native=False):
    """Windows: Edge 'uygulama modu' penceresini görev çubuğunda ve başlık çubuğunda
    Microsoft Edge yerine kendi adı, simgesi ve kimliğiyle (Riven Launcher) göster."""
    if not sys.platform.startswith("win"):
        return
    try:
        from ctypes import wintypes
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        ico = BASE_DIR / "riven.ico"
        frozen = getattr(sys, "frozen", False)
        relaunch = f'"{sys.executable}"' if frozen else f'"{sys.executable}" "{Path(__file__).resolve()}"'
        icon_res = f"{sys.executable},0" if frozen else f"{ico},0"
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        Enum = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [Enum, wintypes.LPARAM]
        set_class = getattr(user32, "SetClassLongPtrW", None) or getattr(user32, "SetClassLongW", None)
        if set_class is not None:
            set_class.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            set_class.restype = ctypes.c_void_p

        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                        ("d", ctypes.c_ubyte * 8)]

        class KEY(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

        class PV(ctypes.Structure):   # PROPVARIANT (VT_LPWSTR = 31)
            _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                        ("r3", ctypes.c_ushort), ("p", ctypes.c_void_p), ("pad", ctypes.c_void_p)]

        def guid(text):
            return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)

        def find_window():
            found = []

            def cb(hwnd, _lparam):
                if user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    if n:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(hwnd, buf, n + 1)
                        cls = ctypes.create_unicode_buffer(64)
                        user32.GetClassNameW(hwnd, cls, 64)
                        if not buf.value.startswith(title):
                            return True
                        if native:   # pywebview penceresi: kendi sürecimizin üst düzey penceresi
                            pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            if pid.value == os.getpid():
                                found.append(hwnd)
                        elif cls.value.startswith("Chrome_WidgetWin"):
                            found.append(hwnd)
                return True
            user32.EnumWindows(Enum(cb), 0)
            return found[0] if found else None

        def set_identity(hwnd):
            iid, store = guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), ctypes.c_void_p()
            shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, ctypes.POINTER(GUID),
                                                            ctypes.POINTER(ctypes.c_void_p)]
            if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)) != 0:
                return
            vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
                               ctypes.POINTER(ctypes.c_void_p))
            set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(KEY),
                                           ctypes.POINTER(PV))(vtbl[6])
            commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
            fmt, keep = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3", []
            for pid, text in ((5, "Riven.Launcher"), (2, relaunch), (4, title), (3, icon_res)):
                buf = ctypes.create_unicode_buffer(text)
                keep.append(buf)
                pv = PV(31, 0, 0, 0, ctypes.cast(buf, ctypes.c_void_p), None)
                set_value(store, ctypes.byref(KEY(guid(fmt), pid)), ctypes.byref(pv))
            commit(store)
            release(store)

        icons = {}   # simge tutaçlarını canlı tut (yok edilmesinler)

        def load_icon(size):
            if size not in icons:
                icons[size] = user32.LoadImageW(None, str(ico), 1, size, size, 0x10) or None   # IMAGE_ICON, LR_LOADFROMFILE
            return icons[size]

        def set_icons(hwnd):
            if not ico.is_file():
                return
            big = max(user32.GetSystemMetrics(11), 32)    # SM_CXICON
            small = max(user32.GetSystemMetrics(49), 16)  # SM_CXSMICON
            for size, which, gcl in ((big, 1, -14), (small, 0, -34)):   # ICON_BIG/GCLP_HICON, ICON_SMALL/GCLP_HICONSM
                hicon = load_icon(size)
                if not hicon:
                    continue
                user32.SendMessageW(hwnd, 0x80, which, hicon)   # WM_SETICON
                if set_class is not None:
                    set_class(hwnd, gcl, hicon)                  # pencere sınıfı simgesi (yedek)

        hwnd = None
        for _ in range(120):   # pencere en geç ~48 sn içinde çıkar
            hwnd = find_window()
            if hwnd:
                break
            time.sleep(0.4)
        if not hwnd:
            add_log("Pencere kimliği: pencere bulunamadı (görev çubuğu simgesi ayarlanamadı).")
            return
        for wait in (0, 1, 2, 4, 8, 15, 30):   # pencere simgeyi sonradan geri yazabilir, birkaç kez uygula
            time.sleep(wait)
            hwnd = find_window() or hwnd
            try:
                set_identity(hwnd)
            except Exception as exc:
                add_log(f"Görev çubuğu kimliği: {exc}")
            set_icons(hwnd)
    except Exception as exc:
        add_log(f"Pencere kimliği ayarlanamadı: {exc}")


def open_app_window(url):
    """Edge/Chrome'u adres çubuksuz 'uygulama modu'nda, ayrı profille aç."""
    candidates = []
    if sys.platform.startswith("win"):
        for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                candidates += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                               Path(base) / "Google/Chrome/Application/chrome.exe"]
    else:
        for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
    for exe in candidates:
        if exe.exists():
            subprocess.Popen([str(exe), f"--app={url}", "--window-size=1240,800",
                              f"--user-data-dir={HOME_DIR / 'browser'}", "--no-first-run",
                              "--no-default-browser-check"])
            threading.Thread(target=brand_window, args=(APP,), daemon=True).start()
            return
    webbrowser.open(url)


def open_native_window(url, httpd):
    """Arayüzü tarayıcı olmadan, kendi uygulama penceresinde aç (pywebview).
    Başarılıysa True döner (pencere kapanınca çağrılan taraf çıkmalıdır)."""
    try:
        import webview
    except Exception:
        return False
    if sys.platform.startswith("win"):
        try:   # görev çubuğunda "Riven Launcher" kimliği
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Riven.Launcher")
        except Exception:
            pass
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    threading.Thread(target=brand_window, args=(APP, True), daemon=True).start()   # görev çubuğu simgesi
    ico = BASE_DIR / "riven.ico"
    try:
        win = webview.create_window(APP, url, width=1240, height=800, min_size=(960, 640),
                                    background_color="#0b0b12")

        def set_form_icon(*_a):
            """WinForms penceresinin kendi Icon özelliğini ayarla (görev çubuğu + başlık çubuğu)."""
            if not (sys.platform.startswith("win") and ico.is_file()):
                return
            try:
                import clr  # noqa: F401  (pythonnet)
                from System import Action
                from System.Drawing import Icon
                form = getattr(win, "native", None)
                if form is None:
                    return
                icon = Icon(str(ico))

                def setter():
                    form.Icon = icon
                try:
                    form.Invoke(Action(setter))
                except Exception:
                    setter()
            except Exception as exc:
                add_log(f"Form simgesi ayarlanamadı: {exc}")
        try:
            win.events.shown += set_form_icon
            win.events.loaded += set_form_icon
        except Exception:
            pass
        start_kw = dict(private_mode=False, storage_path=str(HOME_DIR / "webview"))
        try:
            if ico.is_file() and "icon" in inspect.signature(webview.start).parameters:
                start_kw["icon"] = str(ico)
        except Exception:
            pass
        webview.start(**start_kw)
    except Exception as exc:
        add_log(f"Yerel pencere açılamadı, tarayıcı moduna geçiliyor: {exc}")
        httpd.shutdown()
        server_thread.join(timeout=3)
        return False
    # Pencere kapandı: oyun açıksa bitene kadar arka planda bekle, sonra kapat.
    while RUNNING or PREPARING["id"]:
        time.sleep(2)
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass
    return True


def watchdog():
    """Pencere kapanınca (ve oyun açık değilse) sunucuyu kapat."""
    while True:
        time.sleep(2)
        if RUNNING or PREPARING["id"]:
            PING["last"] = time.time()
            continue
        now = time.time()
        bye = PING["bye"]
        if (bye and now - bye > 4) or now - PING["last"] > IDLE_TIMEOUT:
            SERVER["httpd"].shutdown()
            return


def main():
    if sys.stdout is None or sys.stderr is None:  # --windowed exe'de konsol yok
        sys.stdout = sys.stderr = open(os.devnull, "w")
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    INSTANCES_DIR.mkdir(parents=True, exist_ok=True)
    if not (WEB_DIR / "index.html").exists():
        sys.exit("web/ klasörü bulunamadı. riven.py ile aynı klasörde olmalı.")
    CFG.update(read_json(CONFIG_FILE, {}))
    migrate_old_config()
    migrate_skins()
    save_cfg()
    auto_login()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    SERVER.update(port=httpd.server_address[1], httpd=httpd)
    url = f"http://127.0.0.1:{SERVER['port']}/"
    print(f"{APP} çalışıyor: {url}  (kapatmak için pencereyi kapat veya Ctrl+C)")
    threading.Thread(target=install_riven_tag_all, daemon=True).start()
    threading.Thread(target=update_worker, daemon=True).start()
    threading.Thread(target=refresh_fabric_loaders, daemon=True).start()
    threading.Thread(target=discord_worker, daemon=True).start()
    if open_native_window(url, httpd):
        return
    threading.Thread(target=watchdog, daemon=True).start()
    open_app_window(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
