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

# ╔══════════════════════════════════════════════════════════════════════╗
# ║              QUYIDAGINI O'ZGARTIRMANG                               ║
# ╚══════════════════════════════════════════════════════════════════════╝

import asyncio
import hashlib
import json
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
#  PINTEREST — MAXSUS YUKLAB OLISH
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
                log.info(f"Pinterest: video URL topildi (yt-dlp)")
                return url, "video"
    except Exception as e:
        log.info(f"Pinterest yt-dlp xatosi (normal — rasm bo'lishi mumkin): {e}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.pinterest.com/",
    }

    resolved_url = pin_url
    if "pin.it" in pin_url:
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    pin_url, headers=headers,
                    allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    resolved_url = str(resp.url)
        except Exception as e:
            log.warning(f"Shortlink resolve xatosi: {e}")

    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                resolved_url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                html = await resp.text(errors="ignore")

        patterns = [
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'<meta\s+content="([^"]+)"\s+property="og:image"',
            r'"orig"\s*:\s*\{"url"\s*:\s*"([^"]+)"',
            r'"url_with_signature"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"',
            r'"(https://i\.pinimg\.com/originals/[^"]+\.(?:jpg|jpeg|png|webp))"',
            r'"(https://i\.pinimg\.com/[^"]+/[^"]+\.(?:jpg|jpeg|png|webp))"',
        ]

        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                img_url = m.group(1).replace("\\/", "/").replace("\\u002F", "/")
                img_url = re.sub(r'/\d+x\d*/', '/originals/', img_url)
                img_url = re.sub(r'/\d+x/', '/originals/', img_url)
                return img_url, "image"

        vid_patterns = [
            r'"video_url"\s*:\s*"([^"]+\.(?:mp4|m3u8)[^"]*)"',
            r'"url"\s*:\s*"(https://v\.pinimg\.com/[^"]+\.(?:mp4|m3u8)[^"]*)"',
        ]
        for pat in vid_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                vid_url = m.group(1).replace("\\/", "/")
                return vid_url, "video"

        raise ValueError("Pinterest pindan media topilmadi. Bu pin faqat matn yoki maxfiy bo'lishi mumkin.")

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Pinterest pin yuklanmadi: {e}")


async def pinterest_download(pin_url: str, fid: str) -> tuple[Path, dict]:
    media_url, media_type = await pinterest_get_media_url(pin_url)

    if media_type == "video":
        tmpl = str(TEMP_DIR / f"{fid}.%(ext)s")

        def _dl():
            opts = {
                "outtmpl": tmpl,
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "retries": 3,
                "format": "best[ext=mp4]/best",
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(pin_url, download=True) or {}
                return {
                    "title": (data.get("title") or "Pinterest video")[:100],
                    "uploader": (data.get("uploader") or "Pinterest")[:64],
                    "duration": data.get("duration") or 0,
                }

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _dl)

        found = None
        for f in TEMP_DIR.iterdir():
            if f.stem == fid and f.stat().st_size > 0:
                found = f
                break
        if not found:
            raise FileNotFoundError("Video fayl yuklab olinmadi")
        return found, info

    else:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.pinterest.com/",
        }

        ext = "jpg"
        url_lower = media_url.lower().split("?")[0]
        for e in ("png", "webp", "jpeg", "jpg"):
            if url_lower.endswith(f".{e}"):
                ext = "jpeg" if e == "jpeg" else e
                break

        out_path = TEMP_DIR / f"{fid}.{ext}"

        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                media_url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"Rasm yuklanmadi (HTTP {resp.status})")
                content = await resp.read()

        if len(content) < 1000:
            raise ValueError("Rasm juda kichik — URL noto'g'ri bo'lishi mumkin")

        size_mb = len(content) / 1024 / 1024
        if size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(f"Rasm juda katta: {size_mb:.0f}MB (limit {MAX_FILE_SIZE_MB}MB)")

        out_path.write_bytes(content)
        return out_path, {
            "title": "Pinterest rasm",
            "uploader": "Pinterest",
            "duration": 0,
        }


# ═════════════════════════════════════════════════════════════════════════
#  SHAZAM
# ═════════════════════════════════════════════════════════════════════════

async def shazam_identify(file_path: Path) -> dict:
    wav_path = file_path.with_suffix(".wav")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", str(file_path),
            "-t", "10",
            "-ar", "44100",
            "-ac", "1",
            "-f", "wav",
            str(wav_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except FileNotFoundError:
        log.warning("ffmpeg topilmadi, original fayl ishlatiladi")
        wav_path = file_path

    result = await _audd_identify(wav_path if wav_path.exists() else file_path)

    if wav_path != file_path:
        try:
            wav_path.unlink()
        except Exception:
            pass

    return result


async def _audd_identify(file_path: Path) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            with open(file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename=file_path.name)
                data.add_field("return", "apple_music,spotify,lyrics")
                data.add_field("api_token", "test")
                async with session.post("https://api.audd.io/", data=data) as resp:
                    if resp.status != 200:
                        return {}
                    raw = await resp.json()
    except Exception as e:
        log.error(f"audd.io xatosi: {e}")
        return {}

    if raw.get("status") != "success" or not raw.get("result"):
        return {}

    r = raw["result"]
    info = {
        "title":       r.get("title", ""),
        "artist":      r.get("artist", ""),
        "album":       r.get("album", ""),
        "year":        r.get("release_date", "")[:4] if r.get("release_date") else "",
        "label":       r.get("label", ""),
        "lyrics":      "",
        "apple_url":   "",
        "spotify_url": "",
        "image":       "",
    }

    apple = r.get("apple_music", {})
    if apple:
        info["apple_url"] = apple.get("url", "")
        artwork = apple.get("artwork", {})
        if artwork:
            img_url = artwork.get("url", "").replace("{w}", "500").replace("{h}", "500")
            info["image"] = img_url
        lyrics_data = apple.get("lyrics", {})
        if lyrics_data:
            info["lyrics"] = lyrics_data.get("ttml", "")[:500]

    spotify = r.get("spotify", {})
    if spotify:
        info["spotify_url"] = spotify.get("external_urls", {}).get("spotify", "")
        if not info["image"] and spotify.get("album", {}).get("images"):
            info["image"] = spotify["album"]["images"][0].get("url", "")

    lyrics = r.get("lyrics", {})
    if lyrics and not info["lyrics"]:
        info["lyrics"] = lyrics.get("lyrics", "")[:500]

    return info


def shazam_text(info: dict) -> str:
    if not info:
        return (
            "❌ <b>Qo'shiq aniqlanmadi</b>\n\n"
            "💡 Maslahat:\n"
            "• Kamida 5–10 soniya audio yuboring\n"
            "• Ovoz sifati yaxshi bo'lsin\n"
            "• Fon shovqini kamaytiring\n"
            "• Kunlik limit tugagan bo'lishi mumkin — keyinroq urinib ko'ring"
        )
    lines = ["🎵 <b>Qo'shiq aniqlandi!</b>\n"]
    lines.append(f"🎼 <b>Qo'shiq:</b> {info['title']}")
    lines.append(f"🎤 <b>Ijrochi:</b> {info['artist']}")
    if info.get("album"):  lines.append(f"💿 <b>Album:</b> {info['album']}")
    if info.get("year"):   lines.append(f"📅 <b>Yil:</b> {info['year']}")
    if info.get("label"):  lines.append(f"🏷 <b>Label:</b> {info['label']}")
    links = []
    if info.get("apple_url"):   links.append(f"<a href='{info['apple_url']}'>🍎 Apple Music</a>")
    if info.get("spotify_url"): links.append(f"<a href='{info['spotify_url']}'>🟢 Spotify</a>")
    if links: lines.append("\n🔗 " + " | ".join(links))
    if info.get("lyrics"):
        lyr = info["lyrics"].strip()
        if len(lyr) > 500: lyr = lyr[:500] + "..."
        lines.append(f"\n📜 <b>Qo'shiq matni:</b>\n<i>{lyr}</i>")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
#  QIDIRUV
# ═════════════════════════════════════════════════════════════════════════

async def search_songs(query: str, limit: int = 6) -> list[dict]:
    search_query = f"ytsearch{limit}:{query}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "default_search": "ytsearch",
    }

    def _sync_search():
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(search_query, download=False) or {}
            results = []
            for e in data.get("entries", []):
                if not e:
                    continue
                dur = e.get("duration") or 0
                dur_s = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else "—"
                results.append({
                    "title":     (e.get("title") or "")[:80],
                    "artist":    (e.get("uploader") or e.get("channel") or "")[:50],
                    "duration":  dur_s,
                    "url":       e.get("url") or f"https://youtube.com/watch?v={e.get('id','')}",
                    "yt_id":     e.get("id", ""),
                    "thumbnail": e.get("thumbnail") or "",
                    "views":     e.get("view_count") or 0,
                })
            return results

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _sync_search)
    except Exception as e:
        log.error(f"Qidiruv xatosi: {e}")
        return []


def kb_search_results(results: list[dict], query_id: str) -> InlineKeyboardMarkup:
    rows = []
    for i, r in enumerate(results):
        label = f"🎵 {r['title'][:35]}... ({r['duration']})" if len(r['title']) > 35 \
                else f"🎵 {r['title']} ({r['duration']})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"sr|{query_id}|{i}")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="sr_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_search_cache: dict[str, list[dict]] = {}


# ═════════════════════════════════════════════════════════════════════════
#  MA'LUMOTLAR BAZASI
# ═════════════════════════════════════════════════════════════════════════

_db: aiosqlite.Connection | None = None


async def db_init():
    global _db
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            first_name TEXT,
            joined_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS downloads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            platform   TEXT,
            media_type TEXT,
            status     TEXT DEFAULT 'ok',
            ts         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS shazam_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title   TEXT,
            artist  TEXT,
            success INTEGER DEFAULT 0,
            ts      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    for col in ("last_seen", "joined_at"):
        try:
            await _db.execute(f"ALTER TABLE users ADD COLUMN {col} TIMESTAMP DEFAULT NULL")
            await _db.commit()
        except Exception:
            pass
    await _db.commit()
    log.info("✅ DB tayyor")


async def db_upsert(uid: int, username, name):
    await _db.execute("""
        INSERT INTO users (user_id,username,first_name) VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_seen=CURRENT_TIMESTAMP
    """, (uid, username, name))
    await _db.commit()


async def db_log_dl(uid: int, platform: str, mtype: str, status: str = "ok"):
    await _db.execute(
        "INSERT INTO downloads(user_id,platform,media_type,status) VALUES(?,?,?,?)",
        (uid, platform, mtype, status)
    )
    await _db.commit()


async def db_log_shazam(uid: int, title: str, artist: str, ok: bool):
    await _db.execute(
        "INSERT INTO shazam_log(user_id,title,artist,success) VALUES(?,?,?,?)",
        (uid, title, artist, int(ok))
    )
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

    async with _db.execute("""
        SELECT platform, COUNT(*) cnt FROM downloads
        WHERE status='ok' GROUP BY platform ORDER BY cnt DESC
    """) as c:
        plats = [dict(r) for r in await c.fetchall()]

    async with _db.execute("SELECT user_id FROM users") as c:
        all_ids = [r[0] for r in await c.fetchall()]

    return dict(users=users, new_today=new_day, total_dl=total_dl,
                dl_today=dl_today, shazam=shazam, platforms=plats, all_ids=all_ids)


# ═════════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
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
    now  = time.time()
    hist = [t for t in _rl[uid] if now - t < 3600]
    _rl[uid] = hist
    if len(hist) >= MAX_DOWNLOADS_PER_HOUR:
        return False
    _rl[uid].append(now)
    return True


def del_file(*paths):
    for p in paths:
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════
#  UMUMIY YUKLAB OLISH
# ═════════════════════════════════════════════════════════════════════════

def _sync_dl(url: str, platform: str, tmpl: str, mtype: str) -> dict:
    fmt = PLATFORMS[platform]["fmt"].replace("{q}", str(MAX_VIDEO_QUALITY))
    opts: dict = {
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "retries": 3,
        "socket_timeout": 30,
        "merge_output_format": "mp4",
    }
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
            opts["extractor_args"] = {
                "tiktok": {"app_name": "musical_ly", "app_version": "34.1.2"}
            }

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

    found = None
    for f in TEMP_DIR.iterdir():
        if f.stem == fid and f.stat().st_size > 0:
            found = f
            break

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
            InlineKeyboardButton(text="🔍 Shazam",            callback_data="i_shazam"),
        ],
        [
            InlineKeyboardButton(text="📥 Video yuklab olish", callback_data="i_video"),
            InlineKeyboardButton(text="🎵 Audio yuklab olish", callback_data="i_audio"),
        ],
        [
            InlineKeyboardButton(text="🌐 Platformalar", callback_data="i_plat"),
        ],
    ])


def kb_dl(sid: str, platform: str) -> InlineKeyboardMarkup:
    p  = PLATFORMS[platform]
    wm = " (suvsiz)" if p["watermark"] else ""
    rows = []
    if platform == "pinterest":
        rows.append([InlineKeyboardButton(
            text="📥 Yuklab olish (video/rasm)",
            callback_data=f"dl|video|{sid}"
        )])
    else:
        row = [InlineKeyboardButton(text=f"📹 Video{wm}", callback_data=f"dl|video|{sid}")]
        if p["audio"]:
            row.append(InlineKeyboardButton(text="🎵 Audio MP3", callback_data=f"dl|audio|{sid}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika",   callback_data="adm_stats"),
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
        "• Snapchat — suv belgisiz + audio\n"
        "• Likee — suv belgisiz + audio\n"
        "• Pinterest — video va rasmlar ✅\n"
        "• Threads — video, rasmlar + audio\n\n"
        "🔎 <b>Qo'shiq qidirish:</b>\n"
        "Qo'shiq nomini yozing → yuklab oling!\n\n"
        "🔍 <b>Shazam:</b> ovozli xabar, audio yoki video yuboring!\n\n"
        "👇 Havola, qo'shiq nomi yoki ovozli xabar yuboring:",
        reply_markup=kb_main(),
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📚 <b>Yordam</b>\n\n"
        "🔗 Havola → Video yoki Audio tanlang\n"
        "🎤 Ovozli xabar → Shazam\n"
        "🎵 Audio fayl → Shazam\n"
        "🎬 Video → Shazam\n"
        "📹 Video note → Shazam\n\n"
        "🔎 <b>Qo'shiq qidirish:</b>\n"
        "/search Adele Hello — qidirish\n"
        "Yoki shunchaki matn yozing → qidiriladi\n\n"
        "/start — bosh menyu\n"
        "/myid — Telegram ID\n"
        "/mystats — statistika"
    )


@router.message(Command("search"))
async def cmd_search(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return await msg.answer(
            "🔎 <b>Qidirish</b>\n\n"
            "Ishlatish:\n"
            "<code>/search Adele Hello</code>\n\n"
            "Yoki shunchaki qo'shiq nomini yozing!"
        )
    await _do_search(msg, parts[1].strip())


@router.message(Command("myid"))
async def cmd_myid(msg: Message):
    uid  = msg.from_user.id
    role = "✅ Admin" if uid in ADMIN_IDS else "👤 Foydalanuvchi"
    await msg.answer(f"🆔 <b>ID:</b> <code>{uid}</code>\n👤 <b>Rol:</b> {role}")


@router.message(Command("mystats"))
async def cmd_mystats(msg: Message):
    used = len([t for t in _rl.get(msg.from_user.id, []) if time.time()-t < 3600])
    await msg.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"⚡ Bu soatda: <b>{used}/{MAX_DOWNLOADS_PER_HOUR}</b>\n"
        f"🕐 Qolgan: <b>{max(MAX_DOWNLOADS_PER_HOUR-used,0)}</b>"
    )


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
        return await msg.answer("❌ Matn kiriting:\n/broadcast Xabar")
    text = parts[1]
    s    = await db_stats()
    ids  = s["all_ids"]
    sm   = await msg.answer(f"📢 Yuborilmoqda... ({len(ids)} foydalanuvchi)")
    bot: Bot = msg.bot
    ok = fail = 0
    for uid in ids:
        try:
            await bot.send_message(uid, text)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await sm.edit_text(f"✅ Tugadi!\n✅ {ok} muvaffaqiyatli\n❌ {fail} xato")


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
    p   = PLATFORMS[platform]
    sid = cache_url(url)
    await msg.answer(
        f"{p['emoji']} <b>{p['name']}</b> havolasi aniqlandi!\n\n"
        "🔽 Tanlang:",
        reply_markup=kb_dl(sid, platform),
    )


@router.callback_query(F.data.startswith("dl|"))
async def cb_dl(cb: CallbackQuery):
    await cb.answer()
    _, mtype, sid = cb.data.split("|", 2)
    url = get_url(sid)
    if not url:
        return await cb.message.edit_text("⏰ Havola muddati o'tgan. Qayta yuboring.")

    if not rate_ok(cb.from_user.id):
        return await cb.message.edit_text(
            f"⏳ Soatiga {MAX_DOWNLOADS_PER_HOUR} ta limit to'ldi.\n"
            "Bir soatdan keyin qayta urinib ko'ring."
        )

    platform = detect_platform(url)
    if not platform:
        return await cb.message.edit_text("❌ Platform aniqlanmadi.")

    p      = PLATFORMS[platform]
    tlabel = "Audio (MP3)" if mtype == "audio" else ("Video/Rasm" if platform == "pinterest" else "Video (MP4)")
    sm     = await cb.message.edit_text(
        f"{p['emoji']} <b>{p['name']}</b> → {tlabel}\n\n⏳ Yuklab olinmoqda..."
    )

    fpath = None
    try:
        fpath, info = await download_media(url, platform, mtype)
        title    = info.get("title", "Musiqa")
        uploader = info.get("uploader", "Noma'lum")
        dur      = info.get("duration", 0)
        dur_s    = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else ""

        caption = (
            f"{p['emoji']} <b>{p['name']}</b>\n"
            f"🎵 <b>{title}</b>\n"
            f"👤 {uploader}"
            + (f"\n⏱ {dur_s}" if dur_s else "")
            + f"\n\n🤖 {BOT_USERNAME}"
        )
        inp    = FSInputFile(str(fpath))
        suffix = fpath.suffix.lower()

        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            await cb.message.answer_photo(photo=inp, caption=caption)
        elif mtype == "audio" or suffix in {".mp3", ".m4a", ".ogg", ".wav"}:
            await cb.message.answer_audio(
                audio=inp, caption=caption,
                title=title[:64], performer=uploader,
            )
        else:
            await cb.message.answer_video(
                video=inp, caption=caption, supports_streaming=True,
            )

        await db_log_dl(cb.from_user.id, platform, mtype)
        await sm.edit_text(f"✅ {tlabel} muvaffaqiyatli yuborildi!")

    except ValueError as e:
        await sm.edit_text(f"⚠️ {e}")
        await db_log_dl(cb.from_user.id, platform, mtype, "size_error")
    except Exception as e:
        log.error(f"Download [{platform}]: {e}")
        await sm.edit_text(
            f"❌ Yuklab olishda xato\n\n<i>{str(e)[:200]}</i>\n\n"
            "💡 Havolani tekshiring yoki keyinroq urinib ko'ring."
        )
        await db_log_dl(cb.from_user.id, platform, mtype, "error")
    finally:
        del_file(fpath)


async def _do_shazam(msg: Message, file_id: str, ext: str):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    tmp = TEMP_DIR / f"shz_{file_id[:20]}.{ext}"
    sm  = await msg.answer("🔍 Qo'shiq aniqlanmoqda...")
    try:
        bot: Bot = msg.bot
        tf = await bot.get_file(file_id)
        await bot.download_file(tf.file_path, str(tmp))
        info = await shazam_identify(tmp)
        text = shazam_text(info)
        if info.get("image"):
            try:
                await msg.answer_photo(photo=info["image"], caption=text)
                await sm.delete()
                await db_log_shazam(msg.from_user.id, info.get("title",""), info.get("artist",""), bool(info))
                return
            except Exception:
                pass
        await sm.edit_text(text)
        await db_log_shazam(msg.from_user.id, info.get("title",""), info.get("artist",""), bool(info))
    except Exception as e:
        log.error(f"Shazam: {e}")
        await sm.edit_text("❌ Qo'shiq aniqlanmadi. Keyinroq urinib ko'ring.")
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
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']:,}</b>\n"
        f"🆕 Bugun yangi: <b>{s['new_today']:,}</b>\n\n"
        f"📥 Jami yuklashlar: <b>{s['total_dl']:,}</b>\n"
        f"📅 Bugun: <b>{s['dl_today']:,}</b>\n\n"
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
    text  = "🏆 <b>Platformalar</b>\n\n"
    for p in s["platforms"]:
        emoji = PLATFORMS.get(p["platform"], {}).get("emoji", "📥")
        pct   = p["cnt"] / total * 100
        bar   = "█" * int(pct/10) + "░" * (10 - int(pct/10))
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
        "🎬 Video\n"
        "📹 Video note\n\n"
        "Natijada: nomi, ijrochi, yil, matni, Apple Music / Spotify havolasi"
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
        "Shunchaki qo'shiq nomini yozing:\n\n"
        "<i>Misol:</i>\n"
        "• <code>Adele Hello</code>\n"
        "• <code>The Weeknd Blinding Lights</code>\n"
        "• <code>Shohruhxon Kecha keldim</code>\n\n"
        "Bot 6 ta natija topib ko'rsatadi! 🎵"
    )


@router.message(F.text)
async def on_text(msg: Message):
    text = msg.text.strip()
    if len(text) < 2:
        return await msg.answer("💡 Qidirish uchun kamida 2 ta harf kiriting.")
    await _do_search(msg, text)


async def _do_search(msg: Message, query: str):
    await db_upsert(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    sm = await msg.answer(f"🔎 <b>\"{query}\"</b> qidirilmoqda...")
    results = await search_songs(query, limit=6)
    if not results:
        return await sm.edit_text(
            f"😔 <b>\"{query}\"</b> bo'yicha hech narsa topilmadi.\n\n"
            "💡 Maslahat: boshqacha yozing."
        )
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
    idx     = int(idx_str)
    results = _search_cache.get(qid)
    if not results or idx >= len(results):
        return await cb.message.edit_text("⏰ Natija muddati o'tgan. Qayta qidiring.")
    r   = results[idx]
    url = r["url"]
    if r.get("yt_id") and not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={r['yt_id']}"
    sid = cache_url(url)
    _search_cache[f"sel_{sid}"] = r
    text = (
        f"🎵 <b>{r['title']}</b>\n"
        f"👤 {r['artist']}\n"
        f"⏱ {r['duration']}\n\n"
        "Qaysi formatda yuklab olasiz?"
    )
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
        except Exception:
            pass
    await cb.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("sr_back|"))
async def cb_search_back(cb: CallbackQuery):
    await cb.answer()
    qid     = cb.data.split("|", 1)[1]
    results = _search_cache.get(qid)
    if not results:
        return await cb.message.edit_text("⏰ Natija muddati o'tgan. Qayta qidiring.")
    text = f"🔎 Natijalar ({len(results)} ta):\n\n"
    for i, r in enumerate(results, 1):
        text += f"{i}. 🎵 <b>{r['title']}</b>\n   👤 {r['artist']}  ⏱ {r['duration']}\n"
    await cb.message.edit_text(text, reply_markup=kb_search_results(results, qid))


@router.callback_query(F.data == "sr_cancel")
async def cb_search_cancel(cb: CallbackQuery):
    await cb.answer("Bekor qilindi")
    await cb.message.delete()


# ═════════════════════════════════════════════════════════════════════════
#  BACKGROUND CLEANER
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
            except Exception:
                pass
        if cleaned:
            log.info(f"🧹 {cleaned} ta eski fayl o'chirildi")


# ═════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════

async def main():
    await db_init()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(_cleaner())

    log.info("🎵 Musiqa Bot ishga tushdi!")
    log.info(f"👥 Adminlar: {ADMIN_IDS}")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        if _db:
            await _db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
