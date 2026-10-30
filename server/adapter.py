#!/usr/bin/env python3
import base64, html, re, sys, threading, time, urllib.parse, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = {
    "opml.radiotime.com": "opml.radiotime.com",
    "feed.tunein.com": "feed.tunein.com",
    "feed.radiotime.com": "feed.radiotime.com",
    "tin.serverlele.de": "opml.radiotime.com",
}
PUBLIC = "http://tin.serverlele.de"
UA = "WayForward/0000.00.01"
STREAM_UA = "Mozilla/5.0 (PSVita; TuneIn)"
PLAYLIST_TYPES = ("audio/x-mpegurl", "audio/mpegurl", "application/vnd.apple.mpegurl",
                  "application/x-mpegurl", "audio/x-scpls", "audio/scpls",
                  "video/x-ms-asf", "audio/x-ms-wax", "text/")
URL_RE = re.compile(rb"https?://[^\s\"'<>]+")

def safe(path):
    return re.sub(r"(password=)[^&]*", r"\1***", path)[:140]

def wrap(u):
    return PUBLIC + "/stream?u=" + base64.urlsafe_b64encode(u.encode()).decode().rstrip("=")

def unwrap(s):
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s).decode()

def wrap_urls(body):
    return URL_RE.sub(lambda m: wrap(m.group(0).decode("utf-8", "replace")).encode(), body)

def log(msg):
    sys.stderr.write(time.strftime("%H:%M:%S ") + msg + "\n")

SAFE_CHARS = "/?&=%+:,;@!$'()*[]~-._"

def fix_path(p):
    try:
        raw = p.encode("latin-1")
    except UnicodeEncodeError:
        raw = p.encode("utf-8")
    return urllib.parse.quote(raw, safe=SAFE_CHARS)

SONG_CACHE = {}
SONG_LOCK = threading.Lock()
SONG_TTL = 600
SONG_EMPTY = (b'<?xml version="1.0" encoding="UTF-8"?>\n<opml version="1">\n\t<head>\n'
              b'\t<status>200</status>\n\t</head>\n\t<body>\n'
              b'<outline text="content" guide_id="o0"/>\n\t</body>\n</opml>')

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def reply(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def stream(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        try:
            url = unwrap(q["u"][0])
        except Exception:
            self.reply(400, "text/plain", b"")
            return
        hdr = {"User-Agent": STREAM_UA}
        if self.headers.get("Icy-MetaData"):
            hdr["Icy-MetaData"] = self.headers["Icy-MetaData"]
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=20)
        except Exception as e:
            log("STREAM-FEHLER %s: %s" % (url, e))
            self.reply(502, "text/plain", b"")
            return
        ctype = (r.headers.get("Content-Type") or "audio/mpeg").split(";")[0].strip().lower()
        if ctype.startswith(PLAYLIST_TYPES):
            body = wrap_urls(r.read(200000).replace(b"&amp;", b"&"))
            r.close()
            self.reply(200, ctype, body)
            log("PLAYLIST %s (%s) -> %dB" % (url[:90], ctype, len(body)))
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        for k, v in r.headers.items():
            if k.lower().startswith("icy-"):
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        n, t = 0, time.time()
        log("STREAM start %s (%s)" % (r.geturl()[:90], ctype))
        try:
            while True:
                chunk = r.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                n += len(chunk)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            r.close()
        log("STREAM ende %s %.1f MB in %.0fs" % (url[:60], n / 1e6, time.time() - t))

    def handle_any(self, data=None):
        self.path = fix_path(self.path)
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        t = time.time()
        if self.path.startswith("/stream?"):
            self.stream()
            return
        if host == "home.wayforward.com" or self.path.startswith("/esportadb/"):
            self.reply(200, "text/plain", b"")
            log("%s %s -> 200 (WayForward-Upload verworfen)" % (host, safe(self.path)))
            return
        up = UPSTREAM.get(host)
        if not up:
            self.reply(404, "text/plain", b"")
            return
        is_song = self.path.lower().startswith("/songlookup.ashx")
        if is_song:
            with SONG_LOCK:
                hit = SONG_CACHE.get(self.path)
            if hit and time.time() - hit[0] < SONG_TTL:
                self.reply(200, hit[1], hit[2])
                return
        url = "https://%s%s" % (up, self.path)
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": self.headers.get("User-Agent", UA)})
            with urllib.request.urlopen(req, timeout=15) as r:
                status, ctype, body = r.status, r.headers.get("Content-Type", "text/xml"), r.read()
        except urllib.error.HTTPError as e:
            status, ctype, body = e.code, e.headers.get("Content-Type", "text/xml"), e.read()
        except Exception as e:
            log("UPSTREAM-FEHLER %s%s: %s" % (up, safe(self.path), e))
            if not is_song:
                self.reply(502, "text/plain", b"")
                return
            status, ctype, body = 200, "text/xml", SONG_EMPTY
        if is_song:
            if status != 200 or b"<outline" not in body:
                status, ctype, body = 200, "text/xml", SONG_EMPTY
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            title = (q.get("title") or [""])[0]
            if b' title="' not in body and title:
                body = body.replace(b'<outline text="content"',
                    b'<outline text="content" title="' + html.escape(title, quote=True).encode("utf-8") + b'"', 1)
            with SONG_LOCK:
                if len(SONG_CACHE) > 500:
                    SONG_CACHE.clear()
                SONG_CACHE[self.path] = (time.time(), ctype, body)
        if self.path.startswith("/Tune.ashx") and not body.lstrip().startswith(b"<"):
            lines = [l.strip() for l in body.splitlines() if l.strip()]
            lines.sort(key=lambda l: 0 if b"mp3" in l.lower() else 1)
            body = b"\n".join(wrap_urls(l) for l in lines) + b"\n"
        elif ctype.startswith(("text/", "application/xml", "application/json")):
            body = body.replace(b"https://", b"http://")
        self.reply(status, ctype, body)
        log("%s %s -> %d %dB %.0fms" % (host, safe(self.path), status, len(body), (time.time() - t) * 1000))

    def do_GET(self):
        self.handle_any()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.handle_any(self.rfile.read(n) if n else b"")

    def log_message(self, *a):
        pass

ThreadingHTTPServer(("127.0.0.1", 8445), H).serve_forever()
