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
_BROADCAST_BUFFER_BYTES = 2 * 1024 * 1024  # 2MB replay for late-joining consumers (e.g. Apple TV after another client)


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


def _producer_merge(stream_id: str, broadcast_queue: queue.Queue) -> None:
    """Run ffmpeg merge and put chunks into broadcast queue. Call from background thread."""
    first_chunk = True
    chunk_count = 0
    try:
        for chunk in _run_ffmpeg_merge(stream_id):
            if chunk:
                chunk_count += 1
                if first_chunk:
                    logger.info("[stream %s] FFmpeg: first data ready (pre-warm)", stream_id)
                    first_chunk = False
                broadcast_queue.put(chunk)
    except Exception as e:
        logger.warning("Merge producer error for %s: %s", stream_id, e)
    finally:
        broadcast_queue.put(None)
        if chunk_count == 0:
            logger.warning("[stream %s] FFmpeg: stream finished with no data (check FFmpeg exit log above)", stream_id)
        else:
            logger.info("[stream %s] FFmpeg: stream finished (%s chunks)", stream_id, chunk_count)


def _broadcaster_merge(stream_id: str, broadcast_queue: queue.Queue, consumers: list, buffer_list: list, buffer_lock: threading.Lock) -> None:
    """Read from broadcast_queue, keep a bounded buffer, and put each chunk into every consumer queue."""
    buffer_bytes = 0
    try:
        while True:
            chunk = broadcast_queue.get()
            if chunk is None:
                with buffer_lock:
                    for q in list(consumers):
                        try:
                            q.put(None)
                        except Exception:
                            pass
                return
            with buffer_lock:
                buffer_list.append(chunk)
                buffer_bytes += len(chunk)
                while buffer_bytes > _BROADCAST_BUFFER_BYTES and buffer_list:
                    old = buffer_list.pop(0)
                    buffer_bytes -= len(old)
                for q in list(consumers):
                    try:
                        q.put(chunk)
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("[stream %s] Broadcaster error: %s", stream_id, e)


def create_merge_session(video_url: str, audio_url: str, height: Optional[int] = None) -> str:
    """Store a merge session, start ffmpeg + broadcaster so multiple clients (e.g. Apple TV + browser) can get the same stream."""
    import time
    stream_id = str(uuid.uuid4())[:12]
    broadcast_queue = queue.Queue(maxsize=_PREWARM_QUEUE_MAXSIZE)
    consumers: list = []
    buffer_list: list = []
    buffer_lock = threading.Lock()
    _sessions[stream_id] = {
        "video_url": video_url,
        "audio_url": audio_url,
        "height": height,
        "created_at": time.time(),
        "broadcast_queue": broadcast_queue,
        "consumers": consumers,
        "buffer_list": buffer_list,
        "buffer_lock": buffer_lock,
        "requested": False,  # Track if Apple TV requested the stream
    }
    t = threading.Thread(target=_producer_merge, args=(stream_id, broadcast_queue), daemon=True)
    t.start()
    b = threading.Thread(
        target=_broadcaster_merge,
        args=(stream_id, broadcast_queue, consumers, buffer_list, buffer_lock),
        daemon=True,
    )
    b.start()
    logger.info("[stream %s] Merge session created, FFmpeg started in background (Apple TV will request GET /stream/%s)", stream_id, stream_id)
    return stream_id


def _producer_hls(stream_id: str, broadcast_queue: queue.Queue) -> None:
    """Run HLS→MP4 ffmpeg and put chunks into broadcast queue. Call from background thread."""
    first_chunk = True
    chunk_count = 0
    try:
        for chunk in _run_ffmpeg_hls_to_mp4(stream_id):
            if chunk:
                chunk_count += 1
                if first_chunk:
                    logger.info("[stream %s] HLS→MP4: first data ready (pre-warm)", stream_id)
                    first_chunk = False
                broadcast_queue.put(chunk)
    except Exception as e:
        logger.warning("[stream %s] HLS producer error: %s", stream_id, e)
    finally:
        broadcast_queue.put(None)
        if chunk_count == 0:
            logger.warning("[stream %s] HLS→MP4: no data (check ffmpeg)", stream_id)
        else:
            logger.info("[stream %s] HLS→MP4 finished (%s chunks)", stream_id, chunk_count)


def create_hls_session(hls_url: str) -> str:
    """Store HLS URL, start ffmpeg in background (pre-warm) so Apple TV gets data immediately."""
    import time
    stream_id = str(uuid.uuid4())[:12]
    broadcast_queue = queue.Queue(maxsize=_PREWARM_QUEUE_MAXSIZE)
    consumers: list = []
    buffer_list: list = []
    buffer_lock = threading.Lock()
    _sessions[stream_id] = {
        "hls_url": hls_url,
        "created_at": time.time(),
        "broadcast_queue": broadcast_queue,
        "consumers": consumers,
        "buffer_list": buffer_list,
        "buffer_lock": buffer_lock,
        "requested": False,  # Track if Apple TV requested the stream
    }
    t = threading.Thread(target=_producer_hls, args=(stream_id, broadcast_queue), daemon=True)
    t.start()
    b = threading.Thread(
        target=_broadcaster_merge,
        args=(stream_id, broadcast_queue, consumers, buffer_list, buffer_lock),
        daemon=True,
    )
    b.start()
    logger.info("[stream %s] HLS session created, FFmpeg pre-warming (GET /stream/%s)", stream_id, stream_id)
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
        "-probesize", "32K", "-analyzeduration", "500000",
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
            stderr=subprocess.PIPE,
            bufsize=256 * 1024,
        )
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            if chunk:
                yield chunk
        proc.wait()
        if proc.returncode != 0:
            err = (proc.stderr.read() or b"").decode("utf-8", errors="replace").strip()
            if err:
                logger.warning("[stream %s] FFmpeg exit %s: %s", stream_id, proc.returncode, err)
    except Exception as e:
        logger.warning("Stream merge ffmpeg error: %s", e)


def _run_ffmpeg_hls_to_mp4(stream_id: str):
    """Run ffmpeg HLS→MP4 (remux, no re-encode) and yield chunks (blocking generator).
    Optimized for AirPlay compatibility: fragmented MP4 with AAC bitstream filter."""
    session = get_merge_session(stream_id)
    if not session or "hls_url" not in session:
        return
    import subprocess
    hls_url = session["hls_url"]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-probesize", "32K", "-analyzeduration", "500000",
        "-protocol_whitelist", "file,http,https,tcp,tls",
        "-allowed_extensions", "ALL",
        "-i", hls_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",  # Convert AAC ADTS to MP4-compatible format (HLS often uses ADTS)
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",  # faststart not needed for streaming
        "-f", "mp4", "pipe:1",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=256 * 1024,
        )
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            if chunk:
                yield chunk
        proc.wait()
        if proc.returncode != 0:
            err = (proc.stderr.read() or b"").decode("utf-8", errors="replace").strip()
            if err:
                logger.warning("[stream %s] HLS→MP4 ffmpeg exit %s: %s", stream_id, proc.returncode, err[:500])
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


def _register_consumer(stream_id: str):
    """Create a consumer queue, replay buffer into it, add to consumers. Returns (queue, unregister_cb) or (None, None)."""
    session = get_merge_session(stream_id)
    if not session or "consumers" not in session:
        return None, None
    consumers = session["consumers"]
    buffer_list = session["buffer_list"]
    buffer_lock = session["buffer_lock"]
    q = queue.Queue(maxsize=_PREWARM_QUEUE_MAXSIZE * 2)

    def unregister():
        try:
            consumers.remove(q)
        except ValueError:
            pass

    with buffer_lock:
        for c in buffer_list:
            try:
                q.put(c)
            except Exception:
                break
        consumers.append(q)
    return q, unregister


async def wait_hls_prewarm(stream_id: str, timeout: float = 15.0, min_bytes: int = 65536) -> bool:
    """Wait until HLS session buffer has at least min_bytes so Apple TV gets immediate response. Returns True if ready."""
    import time
    session = get_merge_session(stream_id)
    if not session or "buffer_list" not in session or "buffer_lock" not in session:
        return False
    buffer_list = session["buffer_list"]
    buffer_lock = session["buffer_lock"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with buffer_lock:
            total = sum(len(c) for c in buffer_list)
        if total >= min_bytes:
            logger.info("[stream %s] Pre-warm ready (%s bytes)", stream_id, total)
            return True
        await asyncio.sleep(0.15)
    logger.warning("[stream %s] Pre-warm timeout (got %s bytes)", stream_id, sum(len(c) for c in buffer_list))
    return False


async def wait_first_chunk_merge(stream_id: str, timeout: float = 25.0, min_buffer_bytes: int = 262144):
    """Register a consumer, wait for initial data (at least min_buffer_bytes or first chunk). Returns (initial_bytes, queue, unregister_cb) or (None, None, None)."""
    import time
    session = get_merge_session(stream_id)
    if not session or "consumers" not in session:
        return None, None, None
    chunk_queue, unregister = _register_consumer(stream_id)
    if not chunk_queue:
        return None, None, None
    loop = asyncio.get_event_loop()
    chunks = []
    total = 0
    deadline = time.monotonic() + timeout

    def get_next():
        return chunk_queue.get()

    try:
        while total < min_buffer_bytes:
            remaining = max(0.1, deadline - time.monotonic())
            chunk = await asyncio.wait_for(
                loop.run_in_executor(None, get_next),
                timeout=remaining,
            )
            if chunk is None:
                break
            chunks.append(chunk)
            total += len(chunk)
        if not chunks:
            unregister()
            return None, None, None
        return b"".join(chunks), chunk_queue, unregister
    except asyncio.TimeoutError:
        if chunks:
            return b"".join(chunks), chunk_queue, unregister
        unregister()
        logger.warning("Stream %s: no first chunk within %.0fs", stream_id, timeout)
        return None, None, None


async def stream_merged_mp4_async(
    stream_id: str,
    first_chunk: Optional[bytes] = None,
    chunk_queue: Optional[queue.Queue] = None,
    unregister_cb: Optional[Any] = None,
):
    """Async generator: yield chunks. Merge sessions use pre-warmed queue (ffmpeg already running)."""
    session = get_merge_session(stream_id)
    if not session:
        return

    if first_chunk is not None and chunk_queue is not None:
        # Merge: first chunk already received by caller; yield it then rest from queue
        try:
            yield first_chunk
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
        finally:
            if unregister_cb:
                unregister_cb()
        return

    if "chunk_queue" in session:
        # Merge but no first chunk passed: yield from queue (e.g. HLS path)
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
