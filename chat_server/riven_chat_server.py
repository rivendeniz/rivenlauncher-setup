#!/usr/bin/env python3
"""Riven Mesaj Sunucusu: launcher'lar arası mesajlaşma için küçük bir aktarıcı.

Ek paket gerektirmez (yalnızca Python 3.9+). Bir PC'de ya da VPS'te çalıştır:

    python riven_chat_server.py --port 8780 --password GIZLI_SIFRE

Launcher'da Mesajlar sayfasından  http://SUNUCU_ADRESI:8780  ve aynı şifreyi gir.
Şifre koymak (--password) önerilir; yalnızca şifreyi bilenler sunucuyu kullanabilir.

Güvenlik notu: kullanıcı adı ilk gelene verilir; kayıt sırasında üretilen gizli anahtar
launcher'da saklanır. Anahtar olmadan o isim adına kimse mesaj gönderemez/okuyamaz.
Mesajlar sunucuda düz metin saklanır (30 gün sonra silinir). Şifre ve mesajlar HTTP'de
şifresiz gider; internete açacaksan HTTPS veren bir tünel/ters vekil (Cloudflare Tunnel,
Caddy vb.) arkasına koy.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VERSION = "1.0"
NAME_RE = re.compile(r"\w{3,16}")
MAX_TEXT = 500
KEEP_DAYS = 30
MAX_MESSAGES = 20000
SEND_LIMIT = (30, 60)        # 60 saniyede en fazla 30 mesaj
REGISTER_LIMIT = (10, 3600)  # IP başına saatte 10 kayıt

LOCK = threading.Lock()
STATE = {"users": {}, "messages": [], "next_id": 1}
HITS = {}
CONFIG = {"password": "", "data": Path("chat_data.json")}


def load():
    try:
        data = json.loads(CONFIG["data"].read_text(encoding="utf-8"))
        STATE.update(users=data.get("users", {}), messages=data.get("messages", []),
                     next_id=data.get("next_id", 1))
    except (OSError, ValueError):
        pass


def save():
    tmp = CONFIG["data"].with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CONFIG["data"])


def prune():
    cutoff = time.time() - KEEP_DAYS * 86400
    msgs = [m for m in STATE["messages"] if m["ts"] >= cutoff]
    STATE["messages"] = msgs[-MAX_MESSAGES:]


def rate_ok(key, limit):
    count, window = limit
    now = time.time()
    hits = [t for t in HITS.get(key, []) if now - t < window]
    if len(hits) >= count:
        HITS[key] = hits
        return False
    hits.append(now)
    HITS[key] = hits
    return True


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Err(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


class Handler(BaseHTTPRequestHandler):
    server_version = "RivenChat/" + VERSION

    def log_message(self, *args):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _auth_server(self):
        pw = CONFIG["password"]
        if pw and not secrets.compare_digest(self.headers.get("X-Chat-Key", ""), pw):
            raise Err(403, "Sunucu şifresi yanlış.")

    def _auth_user(self):
        name = self.headers.get("X-Chat-User", "").strip()
        token = self.headers.get("X-Chat-Token", "")
        user = STATE["users"].get(name.lower())
        if not user or not secrets.compare_digest(user["token"], hash_token(token)):
            raise Err(401, "Kimlik doğrulanamadı. Mesajlar sayfasından sunucuya yeniden bağlan.")
        return user["name"]

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 20_000:
            raise Err(413, "İstek çok büyük.")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise Err(400, "Geçersiz JSON.")
        return data if isinstance(data, dict) else {}

    def _handle(self, method):
        try:
            parsed = urlparse(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            self._auth_server()
            ip = self.client_address[0]
            if method == "GET" and path == "/ping":
                return self._reply(200, {"ok": True, "name": "Riven Chat", "version": VERSION})

            if method == "POST" and path == "/register":
                name = str(self._body().get("name", "")).strip()
                if not NAME_RE.fullmatch(name):
                    raise Err(400, "Ad 3-16 karakter olmalı (harf, rakam, _).")
                with LOCK:
                    if name.lower() in STATE["users"]:
                        raise Err(409, "Bu isim sunucuda zaten alınmış.")
                    if not rate_ok(("reg", ip), REGISTER_LIMIT):
                        raise Err(429, "Çok fazla kayıt denemesi, daha sonra tekrar dene.")
                    token = secrets.token_hex(24)
                    STATE["users"][name.lower()] = {"name": name, "token": hash_token(token),
                                                    "created": int(time.time())}
                    save()
                return self._reply(200, {"token": token, "name": name})

            if method == "POST" and path == "/send":
                me = self._auth_user()
                body = self._body()
                target = STATE["users"].get(str(body.get("to", "")).strip().lower())
                text = "".join(c for c in str(body.get("text", "")) if c == "\n" or c.isprintable()).strip()
                if not target:
                    raise Err(404, "Bu kişi henüz bu mesaj sunucusuna bağlanmamış.")
                if not text:
                    raise Err(400, "Mesaj boş.")
                with LOCK:
                    if not rate_ok(("send", me.lower()), SEND_LIMIT):
                        raise Err(429, "Çok hızlı mesaj gönderiyorsun, biraz bekle.")
                    msg = {"id": STATE["next_id"], "from": me, "to": target["name"],
                           "text": text[:MAX_TEXT], "ts": int(time.time())}
                    STATE["next_id"] += 1
                    STATE["messages"].append(msg)
                    prune()
                    save()
                return self._reply(200, {"message": msg})

            if method == "GET" and path == "/poll":
                me = self._auth_user()
                try:
                    since = max(0, int(query.get("since", ["0"])[0]))
                except ValueError:
                    since = 0
                with LOCK:
                    mine = [m for m in STATE["messages"]
                            if m["id"] > since and me.lower() in (m["from"].lower(), m["to"].lower())]
                return self._reply(200, {"messages": mine[-200:], "last_id": STATE["next_id"] - 1})

            raise Err(404, "Bulunamadı.")
        except Err as exc:
            self._reply(exc.code, {"error": exc.msg})
        except Exception as exc:  # noqa: BLE001
            self._reply(500, {"error": f"Sunucu hatası: {exc}"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def lan_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # varsayılan çıkış arayüzü (veri göndermez)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith(("127.", "169.254.")) and i != "0.0.0.0")


def main():
    parser = argparse.ArgumentParser(description="Riven Mesaj Sunucusu")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8780)))
    parser.add_argument("--password", default=os.environ.get("RIVEN_CHAT_PASSWORD", ""))
    parser.add_argument("--data", default=os.environ.get("RIVEN_CHAT_DATA", "chat_data.json"))
    args = parser.parse_args()
    CONFIG["password"], CONFIG["data"] = args.password, Path(args.data)
    load()
    print(f"Riven Mesaj Sunucusu {VERSION}  (port {args.port})")
    print("Launcher'a girilecek adres (0.0.0.0 YAZMA, o bir bağlanma adresi değildir):")
    print(f"   Bu bilgisayardaki launcher için : http://127.0.0.1:{args.port}")
    for ip in lan_ips():
        print(f"   Aynı ağdaki arkadaşlar için     : http://{ip}:{args.port}")
    print("Şifre:", "var" if args.password else "YOK (herkes bağlanabilir, --password önerilir)")
    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        raise SystemExit(f"HATA: {args.port} portu açılamadı ({exc}). Sunucu zaten açık olabilir; "
                         f"kapatıp tekrar dene ya da --port ile başka bir port ver.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
