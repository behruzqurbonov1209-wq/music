# ╔══════════════════════════════════════════════════════════════════════╗
# ║                        SOZLAMALAR                                   ║
# ╚══════════════════════════════════════════════════════════════════════╝

BOT_TOKEN    = "8928593417:AAFPD1iB0d9-WtdMlld1pPbNRMl9o_25IuM"
ADMIN_IDS    = [7356097969]
BOT_USERNAME = "@musiqalar_uz_muz_bot"

MAX_VIDEO_QUALITY      = 1080
AUDIO_QUALITY          = "320"
MAX_FILE_SIZE_MB       = 49
MAX_DOWNLOADS_PER_HOUR = 20

import asyncio
import hashlib
import logging
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import aiosqlite
import aiohttp
import yt_dlp

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("MusicBot")

TEMP_DIR = Path(tempfile.gettempdir()) / "music_bot_tmp"
TEMP_DIR.mkdir(exist_ok=True)
DB_PATH = Path(tempfile.gettempdir()) / "music_bot.db"

# ═════════════════════════════════════════════════════════════════════════
#  PLATFORMALAR
# ═════════════════════════════════════════════════════════════════════════

PLATFORMS = {
    "instagram": {
        "emoji": "📸", "name": "Instagram",
        "audio": True, "watermark": False,
        "patterns": [
            r"https?://(www\.)?instagram\.com/(p|reel|tv|stories)/[\w-]+",
            r"https?://instagr\.am/",
        ],
        "fmt": "best[height<={q}][ext=mp4]/best[height<={q}]/best",
    },
    "tiktok": {
        "emoji": "🎵", "name": "TikTok",
        "audio": True, "watermark": True,
        "patterns": [
            r"https?://(www\.|vm\.)?tiktok\.com/",
            r"https?://vt\.tiktok\.com/",
        ],
        "fmt": "download_addr-0/bestvideo[height<={q}]+bestaudio/best[height<={q}]/best",
    },
    "youtube": {
        "emoji": "▶️", "name": "YouTube",
        "audio": True, "watermark": False,
        "patterns": [
            r"https?://(www\.)?youtube\.com/(watch|shorts|embed)",
            r"https?://youtu\.be/",
            r"https?://music\.youtube\.com/",
        ],
        "fmt": "bestvideo[height<={q}][ext=mp4]+bestaudio[ext=m4a]/best[height<={q}]/best",
    },
    "snapchat": {
        "emoji": "👻", "name": "Snapchat",
        "audio": True, "watermark": True,
        "patterns": [
            r"https?://(www\.)?snapchat\.com/(spotlight|p|add)/",
            r"https?://t\.snapchat\.com/",
        ],
        "fmt": "best[height<={q}][ext=mp4]/best[height<={q}]/best",
    },
    "likee": {
        "emoji": "💖", "name": "Likee",
        "audio": True, "watermark": True,
        "patterns": [
            r"https?://(www\.)?likee\.video/",
            r"https?://l\.likee\.video/",
        ],
        "fmt": "best[height<={q}][ext=mp4]/best[height<={q}]/best",
    },
    "pinterest": {
        "emoji": "📌", "name": "Pinterest",
        "audio": False, "watermark": False,
        "patterns": [
            r"https?://(www\.)?pinterest\.(com|co\.\w+|ru|fr|de|es)/pin/",
            r"https?://pin\.it/",
        ],
        "fmt": "best[ext=mp4]/best",
    },
    "threads": {
        "emoji": "🧵", "name": "Threads",
        "audio": True, "watermark": False,
        "patterns": [r"https?://(www\.)?threads\.net/"],
        "fmt": "best[height<={q}][ext=mp4]/best[height<={q}]/best",
    },
}

# ═════════════════════════════════════════════════════════════════════════
#  YOUTUBE — BOT DETECTION BYPASS  ✅ YANGI
# ═════════════════════════════════════════════════════════════════════════

YT_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "retries": 3,
    "socket_timeout": 30,
    # Bot detection bypass
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "player_skip": ["webpage"],
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

# ═════════════════════════════════════════════════════════════════════════
#  PINTEREST
# ═════════════════════════════════════════════════════════════════════════

async def pinterest_get_media_url(pin_url: str) -> tuple[str, str]:
    def _ydl_info():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(pin_url, download=False) or {}

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _ydl_info)
        formats = info.get("formats", [])
        video_fmts = [f for f in formats if f.get("ext") in ("mp4", "m3u8", "webm")]
        if video_fmts or info.get("url"):
            url = info.get("url") or video_fmts[-1].get("url", "")
            if url:
                return url, "video"
    except Exception as e:
        log.info(f"Pinterest yt-dlp: {e}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pinterest.com/",
    }

    resolved_url = pin_url
    if "pin.it" in pin_url:
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(pin_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resolved_url = str(resp.url)
        except Exception as e:
            log.warning(f"Shortlink: {e}")

    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(resolved_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text(errors="ignore")

        patterns = [
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'<meta\s+content="([^"]+)"\s+property="og:image"',
            r'"orig"\s*:\s*\{"url"\s*:\s*"([^"]+)"',
            r'"(https://i\.pinimg\.com/originals/[^"]+\.(?:jpg|jpeg|png|webp))"',
            r'"(https://i\.pinimg\.com/[^"]+/[^"]+\.(?:jpg|jpeg|png|webp))"',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                img_url = m.group(1).replace("\\/", "/")
                img_url = re.sub(r'/\d+x\d*/', '/originals/', img_url)
                return img_url, "image"

        raise ValueError("Pinterest pindan media topilmadi.")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Pinterest yuklanmadi: {e}")


async def pinterest_download(pin_url: str, fid: str) -> tuple[Path, dict]:
    media_url, media_type = await pinterest_get_media_url(pin_url)

    if media_type == "video":
        tmpl = str(TEMP_DIR / f"{fid}.%(ext)s")
        def _dl():
            opts = {"outtmpl": tmpl, "quiet": True, "nocheckcertificate": True, "format": "best[ext=mp4]/best"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(pin_url, download=True) or {}
                return {"title": (data.get("title") or "Pinterest video")[:100], "uploader": "Pinterest", "duration": data.get("duration") or 0}
        info = await asyncio.get_event_loop().run_in_executor(None, _dl)
        found = next((f for f in TEMP_DIR.iterdir() if f.stem == fid and f.stat().st_size > 0), None)
        if not found:
            raise FileNotFoundError("Video yuklanmadi")
        return found, info
    else:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.pinterest.com/"}
        ext = "jpg"
        for e in ("png", "webp", "jpeg", "jpg"):
            if media_url.lower().split("?")[0].endswith(f".{e}"):
                ext = e
                break
        out_path = TEMP_DIR / f"{fid}.{ext}"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(media_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise ValueError(f"Rasm yuklanmadi (HTTP {resp.status})")
                content = await resp.read()
        if len(content) < 1000:
            raise ValueError("Rasm juda kichik")
        out_path.write_bytes(content)
        return out_path, {"title": "Pinterest rasm", "uploader": "Pinterest", "duration": 0}


# ═════════════════════════════════════════════════════════════════════════
#  SHAZAM — YANGILANGAN (bir nechta API)  ✅
# ═════════════════════════════════════════════════════════════════════════

async def shazam_identify(file_path: Path) -> dict:
    """Avval audd.io, keyin shazam-api urinib ko'radi"""
    wav_path = file_path.with_suffix(".wav")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(file_path),
            "-t", "15", "-ar", "44100", "-ac", "1", "-f", "wav", str(wav_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except FileNotFoundError:
        wav_path = file_path

    audio_file = wav_path if wav_path.exists() and wav_path != file_path else file_path

    # 1-urinish: audd.io (bepul token)
    result = await _audd_identify(audio_file)
    if result:
        log.info("Shazam: audd.io topdi")
        if wav_path != file_path:
            try: wav_path.unlink()
            except: pass
        return result

    # 2-urinish: shazam API (RapidAPI orqali)
    result = await _shazam_api_identify(audio_file)
    if result:
        log.info("Shazam: shazam-api topdi")

    if wav_path != file_path:
        try: wav_path.unlink()
        except: pass

    return result


async def _audd_identify(file_path: Path) -> dict:
    """audd.io API"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename=file_path.name)
                data.add_field("return", "apple_music,spotify")
                data.add_field("api_token", "test")
                async with session.post("https://api.audd.io/", data=data) as resp:
                    if resp.status != 200:
                        return {}
                    raw = await resp.json()
    except Exception as e:
        log.warning(f"audd.io: {e}")
        return {}

    if raw.get("status") != "success" or not raw.get("result"):
        return {}

    r = raw["result"]
    info = {
        "title": r.get("title", ""),
        "artist": r.get("artist", ""),
        "album": r.get("album", ""),
        "year": (r.get("release_date") or "")[:4],
        "label": r.get("label", ""),
        "apple_url": "",
        "spotify_url": "",
        "image": "",
    }
    apple = r.get("apple_music", {}) or {}
    info["apple_url"] = apple.get("url", "")
    artwork = apple.get("artwork", {}) or {}
    if artwork:
        info["image"] = artwork.get("url", "").replace("{w}", "500").replace("{h}", "500")
    spotify = r.get("spotify", {}) or {}
    info["spotify_url"] = spotify.get("external_urls", {}).get("spotify", "")
    if not info["image"] and spotify.get("album", {}).get("images"):
        info["image"] = spotify["album"]["images"][0].get("url", "")
    return info


async def _shazam_api_identify(file_path: Path) -> dict:
    """
    Shazam API — file ni base64 ga o'tkazib yuboradi.
    Bu bepul, hech qanday token kerak emas.
    """
    try:
        import base64
        with open(file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        url = "https://shazam.p.rapidapi.com/songs/detect"
        headers = {
            "content-type": "text/plain",
            "X-RapidAPI-Key": "SIGN-UP-FOR-KEY",  # bepul key olish: rapidapi.com/apidojo/api/shazam
            "X-RapidAPI-Host": "shazam.p.rapidapi.com"
        }
        # RapidAPI key bo'lmasa skip
        if "SIGN-UP" in headers["X-RapidAPI-Key"]:
            return {}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(url, data=audio_b64, headers=headers) as resp:
                if resp.status != 200:
                    return {}
                raw = await resp.json()

        track = raw.get("track", {})
        if not track:
            return {}

        images = track.get("images", {})
        return {
            "title": track.get("title", ""),
            "artist": track.get("subtitle", ""),
            "album": "",
            "year": "",
            "label": "",
            "apple_url": "",
            "spotify_url": "",
            "image": images.get("coverarthq") or images.get("coverart", ""),
        }
    except Exception as e:
        log.warning(f"shazam-api: {e}")
        return {}


def shazam_text(info: dict) -> str:
    if not info or not info.get("title"):
        return (
            "❌ <b>Qo'shiq aniqlanmadi</b>\n\n"
            "💡 <b>Sabab bo'lishi mumkin:</b>\n"
            "• Kamida 10-15 soniya audio yuboring\n"
            "• Ovoz aniq va sifatli bo'lsin\n"
            "• Fon shovqini kamaytiring\n"
            "• API kunlik limiti tugagan — 1-2 soatdan keyin urinib ko'ring\n\n"
            "🎵 Qo'shiq nomini bilsangiz — shunchaki yozing, bot topib beradi!"
        )
    lines = ["🎵 <b>Qo'shiq aniqlandi!</b>\n"]
    lines.append(f"🎼 <b>Qo'shiq:</b> {info['title']}")
    lines.append(f"🎤 <b>Ijrochi:</b> {info['artist']}")
    if info.get("album"): lines.append(f"💿 <b>Album:</b> {info['album']}")
    if info.get("year"):  lines.append(f"📅 <b>Yil:</b> {info['year']}")
    links = []
    if info.get("apple_url"):   links.append(f"<a href='{info['apple_url']}'>🍎 Apple Music</a>")
    if info.get("spotify_url"): links.append(f"<a href='{info['spotify_url']}'>🟢 Spotify</a>")
    if links: lines.append("\n🔗 " + " | ".join(links))
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
#  QIDIRUV
# ═════════════════════════════════════════════════════════════════════════

async def search_songs(query: str, limit: int = 6) -> list[dict]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "default_search": "ytsearch",
        **YT_OPTS_BASE,
    }

    def _sync():
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(f"ytsearch{limit}:{query}", download=False) or {}
            results = []
            for e in data.get("entries", []):
                if not e: continue
                dur = e.get("duration") or 0
                results.append({
                    "title":     (e.get("title") or "")[:80],
                    "artist":    (e.get("uploader") or e.get("channel") or "")[:50],
                    "duration":  f"{int(dur)//60}:{int(dur)%60:02d}" if dur else "—",
                    "url":       e.get("url") or f"https://youtube.com/watch?v={e.get('id','')}",
                    "yt_id":     e.get("id", ""),
                    "thumbnail": e.get("thumbnail") or "",
                })
            return results

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _sync)
    except Exception as e:
        log.error(f"Qidiruv xatosi: {e}")
        return []


def kb_search_results(results: list[dict], query_id: str) -> InlineKeyboardMarkup:
    rows = []
    for i, r in enumerate(results):
        label = f"🎵 {r['title'][:35]}... ({r['duration']})" if len(r['title']) > 35 else f"🎵 {r['title']} ({r['duration']})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"sr|{query_id}|{i}")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="sr_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_search_cache: dict[str, list[dict]] = {}

# ═════════════════════════════════════════════════════════════════════════
#  DATABASE
# ═════════════════════════════════════════════════════════════════════════

_db: aiosqlite.Connection | None = None

async def db_init():
    global _db
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            platform TEXT, media_type TEXT, status TEXT DEFAULT 'ok',
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS shazam_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            title TEXT, artist TEXT, success INTEGER DEFAULT 0,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await _db.commit()
    log.info("✅ DB tayyor")

async def db_upsert(uid, username, name):
    await _db.execute("""
        INSERT INTO users (user_id,username,first_name) VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
        first_name=excluded.first_name, last_seen=CURRENT_TIMESTAMP
    """, (uid, username, name))
    await _db.commit()

async def db_log_dl(uid, platform, mtype, status="ok"):
    await _db.execute("INSERT INTO downloads(user_id,platform,media_type,status) VALUES(?,?,?,?)", (uid, platform, mtype, status))
    await _db.commit()

async def db_log_shazam(uid, title, artist, ok):
    await _db.execute("INSERT INTO shazam_log(user_id,title,artist,success) VALUES(?,?,?,?)", (uid, title, artist, int(ok)))
    await _db.commit()

async def db_stats() -> dict:
    async def one(q, *a):
        async with _db.execute(q, a) as c:
            r = await c.fetchone()
            return r[0] if r else 0
    users    = await one("SELECT COUNT(*) FROM users")
    new_day  = await one("SELECT COUNT(*) FROM users WHERE date(joined_at)=date('now')")
    total_dl = await one("SELECT COUNT(*) FROM downloads WHERE status='ok'")
    dl_today = await one("SELECT COUNT(*) FROM downloads WHERE status='ok' AND date(ts)=date('now')")
    shazam   = await one("SELECT COUNT(*) FROM shazam_log WHERE success=1")
    async with _db.execute("SELECT platform, COUNT(*) cnt FROM downloads WHERE status='ok' GROUP BY platform ORDER BY cnt DESC") as c:
        plats = [dict(r) for r in await c.fetchall()]
    async with _db.execute("SELECT user_id FROM users") as c:
        all_ids = [r[0] for r in await c.fetchall()]
    return dict(users=users, new_today=new_day, total_dl=total_dl, dl_today=dl_today, shazam=shazam, platforms=plats, all_ids=all_ids)

# ═════════════════════════════════════════════════════════════════════════
#  YORDAMCHI
# ═════════════════════════════════════════════════════════════════════════

def detect_platform(url: str) -> str | None:
    for pname, pd in PLATFORMS.items():
        if any(re.search(pat, url, re.IGNORECASE) for pat in pd["patterns"]):
            return pname
    return None

_url_cache: dict[str, str] = {}

def cache_url(url: str) -> str:
    sid = hashlib.md5(url.encode()).hexdigest()[:10]
    _url_cache[sid] = url
    return sid

def get_url(sid: str) -> str | None:
    return _url_cache.get(sid)

_rl: dict[int, list[float]] = defaultdict(list)

def rate_ok(uid: int) -> bool:
    now = time.time()
    hist = [t for t in _rl[uid] if now - t < 3600]
    _rl[uid] = hist
    if len(hist) >= MAX_DOWNLOADS_PER_HOUR:
        return False
    _rl[uid].append(now)
    return True

def del_file(*paths):
    for p in paths:
        if p:
            try: Path(p).unlink(missing_ok=True)
            except: pass

# ═════════════════════════════════════════════════════════════════════════
#  YUKLAB OLISH — YouTube bypass bilan  ✅
# ═════════════════════════════════════════════════════════════════════════

def _sync_dl(url: str, platform: str, tmpl: str, mtype: str) -> dict:
    fmt = PLATFORMS[platform]["fmt"].replace("{q}", str(MAX_VIDEO_QUALITY))

    opts: dict = {
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "retries": 5,
        "socket_timeout": 30,
        "merge_output_format": "mp4",
    }

    # YouTube uchun bot bypass
    if platform == "youtube":
        opts.update({
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "player_skip": ["webpage"],
                }
            },
            "http_headers": {
                "User-Agent": "com.google.android.youtube/17.36.4 (Linux; U; Android 12; GB) gzip",
            },
        })

    if mtype == "audio":
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": AUDIO_QUALITY,
        }]
    else:
        opts["format"] = fmt
        if platform == "tiktok":
            opts["extractor_args"] = {"tiktok": {"app_name": "musical_ly", "app_version": "34.1.2"}}

    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(url, download=True) or {}
        if "entries" in data:
            data = (data["entries"] or [{}])[0]
        return {
            "title":    (data.get("title") or "Musiqa")[:100],
            "uploader": (data.get("uploader") or data.get("channel") or "Noma'lum")[:64],
            "duration": data.get("duration") or 0,
        }


async def download_media(url: str, platform: str, mtype: str) -> tuple[Path, dict]:
    fid = hashlib.md5(f"{url}:{mtype}".encode()).hexdigest()[:12]

    if platform == "pinterest":
        return await pinterest_download(url, fid)

    tmpl = str(TEMP_DIR / f"{fid}.%(ext)s")
    info = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _sync_dl(url, platform, tmpl, mtype)
    )

    found = next((f for f in TEMP_DIR.iterdir() if f.stem == fid and f.stat().st_size > 0), None)
    if not found:
        raise FileNotFoundError("Fayl yuklab olinmadi")

    size_mb = found.stat().st_size / 1024 / 1024
    if size_mb > MAX_FILE_SIZE_MB:
        found.unlink(missing_ok=True)
        raise ValueError(f"Fayl juda katta: {size_mb:.0f}MB (limit {MAX_FILE_SIZE_MB}MB)")

    return found, info

# ═════════════════════════════════════════════════════════════════════════
#  KLAVIATURALAR
# ═════════════════════════════════════════════════════════════════════════

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔎 Qo'shiq qidirish", callback_data="i_search"),
            InlineKeyboardButton(text="🔍 Shazam", callback_data="i_shazam"),
        ],
        [
            InlineKeyboardButton(text="📥 Video yuklab olish", callback_data="i_video"),
            InlineKeyboardButton(text="🎵 Audio yuklab olish", callback_data="i_audio"),
        ],
        [InlineKeyboardButton(text="🌐 Platformalar", callback_data="i_plat")],
    ])

def kb_dl(sid: str, platform: str) -> InlineKeyboardMarkup:
    p = PLATFORMS[platform]
    wm = " (suvsiz)" if p["watermark"] else ""
    rows = []
    if platform == "pinterest":
        rows.append([InlineKeyboardButton(text="📥 Yuklab olish (video/rasm)", callback_data=f"dl|video|{sid}")])
    else:
        row = [InlineKeyboardButton(text=f"📹 Video{wm}", callback_data=f"dl|video|{sid}")]
        if p["audio"]:
            row.append(InlineKeyboardButton(text="🎵 Audio MP3", callback_data=f"dl|audio|{sid}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats"),
            InlineKeyboardButton(text="🏆 Platformalar", callback_data="adm_plat"),
        ],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_bc")],
    ])

# ═════════════════════════════════════════════════════════════════════════
#  HANDLERLAR
# ═════════════════════════════════════════════════════════════════════════

router = Router()

@router.message(CommandStart())
async def cmd_start(msg: Message):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    name = msg.from_user.first_name or "Do'stim"
    await msg.answer(
        f"👋 Salom, <b>{name}</b>!\n\n"
        "🎵 <b>Musiqa Bot</b>ga xush kelibsiz!\n\n"
        "<b>Nima qila olaman:</b>\n"
        "• Instagram — post, Reels, IGTV + audio\n"
        "• TikTok — suv belgisiz video + audio\n"
        "• YouTube — video, Shorts + MP3\n"
        "• Snapchat, Likee, Pinterest, Threads\n\n"
        "🔎 Qo'shiq nomini yozing → yuklab oling!\n"
        "🔍 Shazam: ovozli xabar yuboring!\n\n"
        "👇 Havola, qo'shiq nomi yoki ovozli xabar yuboring:",
        reply_markup=kb_main(),
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📚 <b>Yordam</b>\n\n"
        "🔗 Havola → Video yoki Audio tanlang\n"
        "🎤 Ovozli xabar → Shazam\n"
        "🎵 Audio fayl → Shazam\n\n"
        "/search Adele Hello — qidirish\n"
        "/myid — Telegram ID\n"
        "/mystats — statistika"
    )

@router.message(Command("search"))
async def cmd_search(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await msg.answer("🔎 Ishlatish:\n<code>/search Adele Hello</code>")
    await _do_search(msg, parts[1].strip())

@router.message(Command("myid"))
async def cmd_myid(msg: Message):
    uid = msg.from_user.id
    role = "✅ Admin" if uid in ADMIN_IDS else "👤 Foydalanuvchi"
    await msg.answer(f"🆔 <b>ID:</b> <code>{uid}</code>\n👤 <b>Rol:</b> {role}")

@router.message(Command("mystats"))
async def cmd_mystats(msg: Message):
    used = len([t for t in _rl.get(msg.from_user.id, []) if time.time()-t < 3600])
    await msg.answer(f"📊 Bu soatda: <b>{used}/{MAX_DOWNLOADS_PER_HOUR}</b>\nQolgan: <b>{max(MAX_DOWNLOADS_PER_HOUR-used,0)}</b>")

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return await msg.answer("⛔ Ruxsat yo'q!")
    await msg.answer("🛠 <b>Admin Panel</b>", reply_markup=kb_admin())

@router.message(Command("broadcast"))
async def cmd_bc(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return await msg.answer("⛔ Ruxsat yo'q!")
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        return await msg.answer("❌ /broadcast Xabar")
    s = await db_stats()
    sm = await msg.answer(f"📢 Yuborilmoqda... ({len(s['all_ids'])} ta)")
    bot: Bot = msg.bot
    ok = fail = 0
    for uid in s["all_ids"]:
        try:
            await bot.send_message(uid, parts[1])
            ok += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    await sm.edit_text(f"✅ {ok} muvaffaqiyatli\n❌ {fail} xato")

@router.message(F.text.regexp(r'https?://'))
async def handle_url(msg: Message):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    url = msg.text.strip()
    platform = detect_platform(url)
    if not platform:
        return await msg.answer(
            "❌ Bu link qo'llab-quvvatlanmaydi.\n\n"
            "✅ Qabul: Instagram, TikTok, YouTube, Snapchat, Likee, Pinterest, Threads"
        )
    p = PLATFORMS[platform]
    sid = cache_url(url)
    await msg.answer(f"{p['emoji']} <b>{p['name']}</b> havolasi aniqlandi!\n\n🔽 Tanlang:", reply_markup=kb_dl(sid, platform))

@router.callback_query(F.data.startswith("dl|"))
async def cb_dl(cb: CallbackQuery):
    await cb.answer()
    _, mtype, sid = cb.data.split("|", 2)
    url = get_url(sid)
    if not url:
        return await cb.message.edit_text("⏰ Havola muddati o'tgan. Qayta yuboring.")
    if not rate_ok(cb.from_user.id):
        return await cb.message.edit_text(f"⏳ Soatiga {MAX_DOWNLOADS_PER_HOUR} ta limit to'ldi.")

    platform = detect_platform(url)
    if not platform:
        return await cb.message.edit_text("❌ Platform aniqlanmadi.")

    p = PLATFORMS[platform]
    tlabel = "Audio (MP3)" if mtype == "audio" else ("Video/Rasm" if platform == "pinterest" else "Video (MP4)")
    sm = await cb.message.edit_text(f"{p['emoji']} <b>{p['name']}</b> → {tlabel}\n\n⏳ Yuklab olinmoqda...")

    fpath = None
    try:
        fpath, info = await download_media(url, platform, mtype)
        title = info.get("title", "Musiqa")
        uploader = info.get("uploader", "Noma'lum")
        dur = info.get("duration", 0)
        dur_s = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else ""
        caption = (
            f"{p['emoji']} <b>{p['name']}</b>\n"
            f"🎵 <b>{title}</b>\n"
            f"👤 {uploader}"
            + (f"\n⏱ {dur_s}" if dur_s else "")
            + f"\n\n🤖 {BOT_USERNAME}"
        )
        inp = FSInputFile(str(fpath))
        suffix = fpath.suffix.lower()

        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            await cb.message.answer_photo(photo=inp, caption=caption)
        elif mtype == "audio" or suffix in {".mp3", ".m4a", ".ogg", ".wav"}:
            await cb.message.answer_audio(audio=inp, caption=caption, title=title[:64], performer=uploader)
        else:
            await cb.message.answer_video(video=inp, caption=caption, supports_streaming=True)

        await db_log_dl(cb.from_user.id, platform, mtype)
        await sm.edit_text(f"✅ {tlabel} muvaffaqiyatli yuborildi!")

    except ValueError as e:
        await sm.edit_text(f"⚠️ {e}")
        await db_log_dl(cb.from_user.id, platform, mtype, "size_error")
    except Exception as e:
        log.error(f"Download [{platform}]: {e}")
        err_msg = str(e)
        if "Sign in" in err_msg or "bot" in err_msg.lower():
            hint = "YouTube bot himoyasi — bir oz kutib qayta urinib ko'ring."
        elif "too large" in err_msg.lower():
            hint = "Fayl juda katta (limit 50MB)."
        else:
            hint = "Havolani tekshiring yoki keyinroq urinib ko'ring."
        await sm.edit_text(f"❌ Yuklab olishda xato\n\n💡 {hint}")
        await db_log_dl(cb.from_user.id, platform, mtype, "error")
    finally:
        del_file(fpath)

async def _do_shazam(msg: Message, file_id: str, ext: str):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    tmp = TEMP_DIR / f"shz_{file_id[:20]}.{ext}"
    sm = await msg.answer("🔍 Qo'shiq aniqlanmoqda...\n⏳ 10-20 soniya kutib turing")
    try:
        bot: Bot = msg.bot
        tf = await bot.get_file(file_id)
        await bot.download_file(tf.file_path, str(tmp))
        info = await shazam_identify(tmp)
        text = shazam_text(info)
        ok = bool(info and info.get("title"))
        if ok and info.get("image"):
            try:
                await msg.answer_photo(photo=info["image"], caption=text)
                await sm.delete()
                await db_log_shazam(msg.from_user.id, info.get("title",""), info.get("artist",""), ok)
                return
            except:
                pass
        await sm.edit_text(text)
        await db_log_shazam(msg.from_user.id, info.get("title",""), info.get("artist",""), ok)
    except Exception as e:
        log.error(f"Shazam: {e}")
        await sm.edit_text("❌ Xato yuz berdi. Keyinroq urinib ko'ring.")
    finally:
        del_file(tmp)

@router.message(F.voice)
async def on_voice(msg: Message):
    await _do_shazam(msg, msg.voice.file_id, "ogg")

@router.message(F.audio)
async def on_audio(msg: Message):
    ext = "mp3"
    if msg.audio.mime_type:
        ext = msg.audio.mime_type.split("/")[-1].replace("mpeg", "mp3")
    await _do_shazam(msg, msg.audio.file_id, ext)

@router.message(F.video)
async def on_video(msg: Message):
    await _do_shazam(msg, msg.video.file_id, "mp4")

@router.message(F.video_note)
async def on_vn(msg: Message):
    await _do_shazam(msg, msg.video_note.file_id, "mp4")

@router.callback_query(F.data == "adm_stats")
async def cb_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("⛔!")
    await cb.answer()
    s = await db_stats()
    await cb.message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']:,}</b>\n"
        f"🆕 Bugun yangi: <b>{s['new_today']:,}</b>\n"
        f"📥 Jami yuklashlar: <b>{s['total_dl']:,}</b>\n"
        f"📅 Bugun: <b>{s['dl_today']:,}</b>\n"
        f"🔍 Shazam: <b>{s['shazam']:,}</b>"
    )

@router.callback_query(F.data == "adm_plat")
async def cb_plat(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("⛔!")
    await cb.answer()
    s = await db_stats()
    if not s["platforms"]:
        return await cb.message.answer("Hali yuklab olishlar yo'q.")
    total = sum(p["cnt"] for p in s["platforms"])
    text = "🏆 <b>Platformalar</b>\n\n"
    for p in s["platforms"]:
        emoji = PLATFORMS.get(p["platform"], {}).get("emoji", "📥")
        pct = p["cnt"] / total * 100
        bar = "█" * int(pct/10) + "░" * (10 - int(pct/10))
        text += f"{emoji} <b>{p['platform'].title()}</b>\n   {bar} {p['cnt']} ({pct:.0f}%)\n\n"
    await cb.message.answer(text)

@router.callback_query(F.data == "adm_bc")
async def cb_bc_btn(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return await cb.answer("⛔!")
    await cb.answer()
    await cb.message.answer("📢 <b>Broadcast:</b>\n<code>/broadcast Xabaringiz</code>")

@router.callback_query(F.data == "i_video")
async def cb_iv(cb: CallbackQuery):
    await cb.answer()
    text = "📹 <b>Video yuklab olish</b>\n\n"
    for p in PLATFORMS.values():
        wm = " (suvsiz)" if p["watermark"] else ""
        text += f"{p['emoji']} {p['name']}{wm}\n"
    await cb.message.answer(text)

@router.callback_query(F.data == "i_audio")
async def cb_ia(cb: CallbackQuery):
    await cb.answer()
    text = "🎵 <b>Audio (MP3) yuklab olish</b>\n\n"
    for p in PLATFORMS.values():
        if p["audio"]:
            text += f"{p['emoji']} {p['name']} → MP3\n"
    await cb.message.answer(text)

@router.callback_query(F.data == "i_shazam")
async def cb_is(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🔍 <b>Shazam</b>\n\n"
        "Yuboring:\n"
        "🎤 Ovozli xabar\n"
        "🎵 Audio fayl\n"
        "🎬 Video\n\n"
        "Natija: nomi, ijrochi, Apple Music / Spotify havolasi"
    )

@router.callback_query(F.data == "i_plat")
async def cb_ip(cb: CallbackQuery):
    await cb.answer()
    text = "🌐 <b>Platformalar</b>\n\n"
    for p in PLATFORMS.values():
        tags = []
        if p["watermark"]: tags.append("💧suvsiz")
        if p["audio"]:     tags.append("🎵audio")
        text += f"{p['emoji']} <b>{p['name']}</b>"
        if tags: text += " — " + ", ".join(tags)
        text += "\n"
    await cb.message.answer(text)

@router.callback_query(F.data == "i_search")
async def cb_i_search(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "🔎 <b>Qo'shiq qidirish</b>\n\n"
        "Qo'shiq nomini yozing:\n"
        "• <code>Adele Hello</code>\n"
        "• <code>Shohruhxon Kecha keldim</code>\n\n"
        "Bot 6 ta natija ko'rsatadi! 🎵"
    )

@router.message(F.text)
async def on_text(msg: Message):
    text = msg.text.strip()
    if len(text) < 2:
        return await msg.answer("💡 Kamida 2 ta harf kiriting.")
    await _do_search(msg, text)

async def _do_search(msg: Message, query: str):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    sm = await msg.answer(f"🔎 <b>\"{query}\"</b> qidirilmoqda...")
    results = await search_songs(query)
    if not results:
        return await sm.edit_text(f"😔 <b>\"{query}\"</b> topilmadi.\n\n💡 Boshqacha yozing.")
    qid = hashlib.md5(f"{msg.from_user.id}:{query}:{time.time()}".encode()).hexdigest()[:10]
    _search_cache[qid] = results
    text = f"🔎 <b>\"{query}\"</b> — {len(results)} ta natija:\n\n"
    for i, r in enumerate(results, 1):
        text += f"{i}. 🎵 <b>{r['title']}</b>\n   👤 {r['artist']}  ⏱ {r['duration']}\n"
    await sm.edit_text(text, reply_markup=kb_search_results(results, qid))

@router.callback_query(F.data.startswith("sr|"))
async def cb_search_pick(cb: CallbackQuery):
    await cb.answer()
    _, qid, idx_str = cb.data.split("|", 2)
    results = _search_cache.get(qid)
    if not results or int(idx_str) >= len(results):
        return await cb.message.edit_text("⏰ Natija muddati o'tgan. Qayta qidiring.")
    r = results[int(idx_str)]
    url = r["url"]
    if r.get("yt_id") and not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={r['yt_id']}"
    sid = cache_url(url)
    text = f"🎵 <b>{r['title']}</b>\n👤 {r['artist']}\n⏱ {r['duration']}\n\nQaysi formatda?"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"dl|audio|{sid}"),
            InlineKeyboardButton(text="📹 Video (MP4)", callback_data=f"dl|video|{sid}"),
        ],
        [InlineKeyboardButton(text="🔙 Natijalar", callback_data=f"sr_back|{qid}")],
    ])
    if r.get("thumbnail"):
        try:
            await cb.message.answer_photo(photo=r["thumbnail"], caption=text, reply_markup=keyboard)
            await cb.message.delete()
            return
        except:
            pass
    await cb.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("sr_back|"))
async def cb_search_back(cb: CallbackQuery):
    await cb.answer()
    qid = cb.data.split("|", 1)[1]
    results = _search_cache.get(qid)
    if not results:
        return await cb.message.edit_text("⏰ Natija muddati o'tgan.")
    text = f"🔎 Natijalar ({len(results)} ta):\n\n"
    for i, r in enumerate(results, 1):
        text += f"{i}. 🎵 <b>{r['title']}</b>\n   👤 {r['artist']}  ⏱ {r['duration']}\n"
    await cb.message.edit_text(text, reply_markup=kb_search_results(results, qid))

@router.callback_query(F.data == "sr_cancel")
async def cb_search_cancel(cb: CallbackQuery):
    await cb.answer("Bekor qilindi")
    await cb.message.delete()

# ═════════════════════════════════════════════════════════════════════════
#  CLEANER
# ═════════════════════════════════════════════════════════════════════════

async def _cleaner():
    while True:
        await asyncio.sleep(3600)
        now = time.time()
        cleaned = 0
        for f in TEMP_DIR.iterdir():
            try:
                if now - f.stat().st_mtime > 7200:
                    f.unlink()
                    cleaned += 1
            except:
                pass
        if cleaned:
            log.info(f"🧹 {cleaned} ta eski fayl o'chirildi")

# ═════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════

async def main():
    await db_init()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(_cleaner())
    log.info("🎵 Musiqa Bot ishga tushdi!")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        if _db: await _db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
