"""Merge video+audio streams (e.g. YouTube DASH) and serve for AirPlay. HLS→MP4 remux for direct .m3u8 URLs."""
import asyncio
import logging
import os
import queue
import threading
import uuid
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# In-memory sessions: stream_id -> { "video_url", "audio_url" } for merge, or { "hls_url" } for HLS→MP4
_sessions: Dict[str, Dict[str, Any]] = {}
_SESSION_TTL_SEC = 3600
_PREWARM_QUEUE_MAXSIZE = 128


def _get_video_audio_urls_blocking(url: str, quality: str) -> Optional[Dict[str, Any]]:
    """Get separate video and audio URLs from yt-dlp for merging (run in executor)."""
    try:
        import yt_dlp
    except ImportError:
        return None
    try:
        if quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best"
        elif quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best"
        else:
            format_str = "bestvideo+bestaudio/best"
        opts = {
            "format": format_str,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info or not info.get("requested_formats") or len(info["requested_formats"]) < 2:
            return None
        video_url = None
        audio_url = None
        for f in info["requested_formats"]:
            u = f.get("url")
            if not u:
                continue
            if f.get("vcodec") != "none":
                video_url = u
            if f.get("acodec") != "none":
                audio_url = u
        if video_url and audio_url:
            height = info.get("height")
            if not height and info.get("requested_formats"):
                for rf in info["requested_formats"]:
                    if rf.get("height"):
                        height = rf["height"]
                        break
            return {"video_url": video_url, "audio_url": audio_url, "height": height}
        return None
    except Exception as e:
        logger.warning("Could not get video+audio URLs: %s", e)
        return None


def _producer_merge(stream_id: str, chunk_queue: queue.Queue) -> None:
    """Run ffmpeg merge and put chunks into queue. Call from background thread."""
    try:
        for chunk in _run_ffmpeg_merge(stream_id):
            if chunk:
                chunk_queue.put(chunk)
    except Exception as e:
        logger.warning("Merge producer error for %s: %s", stream_id, e)
    finally:
        chunk_queue.put(None)


def create_merge_session(video_url: str, audio_url: str, height: Optional[int] = None) -> str:
    """Store a merge session, start ffmpeg in background so data is ready when Apple TV requests. Return stream_id."""
    import time
    stream_id = str(uuid.uuid4())[:12]
    chunk_queue = queue.Queue(maxsize=_PREWARM_QUEUE_MAXSIZE)
    _sessions[stream_id] = {
        "video_url": video_url,
        "audio_url": audio_url,
        "height": height,
        "created_at": time.time(),
        "chunk_queue": chunk_queue,
    }
    t = threading.Thread(target=_producer_merge, args=(stream_id, chunk_queue), daemon=True)
    t.start()
    logger.info("Merge session %s: ffmpeg started in background", stream_id)
    return stream_id


def create_hls_session(hls_url: str) -> str:
    """Store an HLS URL for remux to MP4; return stream_id."""
    stream_id = str(uuid.uuid4())[:12]
    import time
    _sessions[stream_id] = {
        "hls_url": hls_url,
        "created_at": time.time(),
    }
    return stream_id


def get_merge_session(stream_id: str) -> Optional[Dict[str, Any]]:
    """Get session by id; remove if expired."""
    import time
    s = _sessions.get(stream_id)
    if not s:
        return None
    if time.time() - s["created_at"] > _SESSION_TTL_SEC:
        del _sessions[stream_id]
        return None
    return s


async def get_video_audio_urls(url: str, quality: str) -> Optional[Dict[str, Any]]:
    """Async wrapper for getting video+audio URLs."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_video_audio_urls_blocking, url, quality)


def _run_ffmpeg_merge(stream_id: str):
    """Run ffmpeg merge (video+audio) and yield chunks (blocking generator)."""
    session = get_merge_session(stream_id)
    if not session or "video_url" not in session:
        return
    import subprocess
    # Faster start: minimal probe so first bytes arrive sooner (Apple TV may timeout otherwise)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-probesize", "32K", "-analyze_duration", "500000",
        "-i", session["video_url"],
        "-i", session["audio_url"],
        "-c", "copy",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=256 * 1024,
        )
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            if chunk:
                yield chunk
        proc.wait()
    except Exception as e:
        logger.warning("Stream merge ffmpeg error: %s", e)


def _run_ffmpeg_hls_to_mp4(stream_id: str):
    """Run ffmpeg HLS→MP4 (remux, no re-encode) and yield chunks (blocking generator)."""
    session = get_merge_session(stream_id)
    if not session or "hls_url" not in session:
        return
    import subprocess
    hls_url = session["hls_url"]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-probesize", "32K", "-analyze_duration", "500000",
        "-allowed_extensions", "ALL",
        "-i", hls_url,
        "-c", "copy",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4", "pipe:1",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=256 * 1024,
        )
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            if chunk:
                yield chunk
        proc.wait()
    except Exception as e:
        logger.warning("Stream HLS→MP4 ffmpeg error: %s", e)


def _run_ffmpeg_stream(stream_id: str):
    """Dispatch to merge or HLS→MP4 based on session type."""
    session = get_merge_session(stream_id)
    if not session:
        return
    if "hls_url" in session:
        for chunk in _run_ffmpeg_hls_to_mp4(stream_id):
            yield chunk
    else:
        for chunk in _run_ffmpeg_merge(stream_id):
            yield chunk


async def stream_merged_mp4_async(stream_id: str):
    """Async generator: yield chunks. Merge sessions use pre-warmed queue (ffmpeg already running)."""
    session = get_merge_session(stream_id)
    if not session:
        return

    if "chunk_queue" in session:
        # Merge: data is already being produced by background thread; yield from queue
        chunk_queue = session["chunk_queue"]
        loop = asyncio.get_event_loop()
        while True:
            try:
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(None, chunk_queue.get),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Stream %s: no data within 60s", stream_id)
                break
            if chunk is None:
                break
            yield chunk
        return

    # HLS→MP4: no pre-warm, run ffmpeg in executor
    q = queue.Queue(maxsize=16)

    def run():
        for chunk in _run_ffmpeg_stream(stream_id):
            q.put(chunk)
        q.put(None)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run)
    while True:
        try:
            chunk = await asyncio.wait_for(
                loop.run_in_executor(None, q.get),
                timeout=45.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Stream %s: no data from ffmpeg within 45s", stream_id)
            break
        if chunk is None:
            break
        yield chunk
