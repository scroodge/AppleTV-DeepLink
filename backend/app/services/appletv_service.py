"""Apple TV service using pyatv."""
import asyncio
import logging
import os
from typing import List, Optional, Dict, Any, Tuple, Union
from pyatv import scan, pair, connect
from pyatv.const import Protocol, PairingRequirement
from pyatv.interface import AppleTV, PairingHandler
from app.services.storage_service import DatabaseStorage

logger = logging.getLogger(__name__)

# Optional: resolve YouTube/page URLs to direct stream for AirPlay
try:
    import yt_dlp
    HAS_YT_DLP = True
except ImportError:
    HAS_YT_DLP = False
    yt_dlp = None


class AppleTVService:
    """Service for Apple TV operations."""
    
    def __init__(self):
        self._pairing_sessions: Dict[str, Union[PairingHandler, Tuple[PairingHandler, str]]] = {}
    
    async def scan_devices(self, timeout: int = 5) -> List[Dict[str, Any]]:
        """Scan for Apple TV devices on the local network."""
        try:
            logger.info("Scanning for Apple TV devices...")
            # pyatv scan() returns a list when awaited
            loop = asyncio.get_event_loop()
            try:
                # Use asyncio.wait_for to add timeout
                atvs = await asyncio.wait_for(scan(loop=loop), timeout=timeout)
            except asyncio.TimeoutError:
                logger.info(f"Scan timeout after {timeout} seconds")
                atvs = []  # Return empty list on timeout
            
            devices = []
            for atv in atvs:
                protocols = []
                if atv.get_service(Protocol.AirPlay):
                    protocols.append("airplay")
                if atv.get_service(Protocol.Companion):
                    protocols.append("companion")
                if atv.get_service(Protocol.MRP):
                    protocols.append("mrp")
                
                # If no protocols found, might be Apple TV 1st generation
                device_type = "modern"
                if not protocols:
                    device_type = "legacy"
                    logger.info(f"Device {atv.name} has no modern protocols - likely Apple TV 1st generation")
                
                device_info = {
                    "device_id": f"{atv.address}_{atv.name}",
                    "name": atv.name,
                    "address": str(atv.address),
                    "protocols": protocols,
                    "identifier": str(atv.identifier) if hasattr(atv, 'identifier') else None,
                    "device_type": device_type,  # "modern" or "legacy"
                }
                devices.append(device_info)
                logger.info(f"Found device: {device_info['name']} at {device_info['address']} (protocols: {protocols})")
            
            return devices
        except Exception as e:
            logger.error(f"Error scanning for devices: {e}", exc_info=True)
            raise
    
    async def start_pairing(
        self, 
        device_id: str, 
        address: str, 
        protocol: str,
        credentials_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start pairing process with an Apple TV."""
        try:
            logger.info(f"Starting pairing for {device_id} with protocol {protocol}")
            
            # Map protocol string to Protocol enum
            protocol_map = {
                "airplay": Protocol.AirPlay,
                "companion": Protocol.Companion,
                "mrp": Protocol.MRP,
            }
            
            if protocol not in protocol_map:
                raise ValueError(f"Unsupported protocol: {protocol}")
            
            target_protocol = protocol_map[protocol]
            
            # Scan for the specific device
            loop = asyncio.get_event_loop()
            atvs = await scan(loop=loop, hosts=[str(address)])
            # scan() returns a list, take first result if available
            if not atvs:
                raise ValueError(f"Device not found at {address}")
            
            atv = atvs[0]
            service = atv.get_service(target_protocol)
            if not service:
                raise ValueError(f"Protocol {protocol} not supported by device")
            
            # Map protocol to storage key (AirPlay, Companion, MRP) so we store two separate credentials
            protocol_storage_key = {"airplay": "AirPlay", "companion": "Companion", "mrp": "MRP"}.get(protocol, "AirPlay")
            
            # Create storage from existing credentials if available
            db_storage = DatabaseStorage(credentials_json)
            device_identifier = str(atv.identifier)
            
            # Storage adapter: pyatv may pass a raw string for one protocol; we always store dict by protocol key
            class StorageAdapter:
                def __init__(self, db_storage: DatabaseStorage, identifier: str, protocol_key: str):
                    self._db_storage = db_storage
                    self._identifier = identifier
                    self._protocol_key = protocol_key
                
                def save(self, credentials: Any) -> None:
                    """Save credentials. If pyatv passes a string, store as { protocol_key: credentials }."""
                    if isinstance(credentials, str):
                        credentials = {self._protocol_key: credentials}
                    elif not isinstance(credentials, dict):
                        credentials = {self._protocol_key: credentials}
                    self._db_storage.save(self._identifier, credentials)
                
                def load(self) -> Optional[Dict[str, Any]]:
                    return self._db_storage.load(self._identifier)
                
                def get_settings(self, identifier: str) -> Optional[Dict[str, Any]]:
                    return self._db_storage.load(identifier)
            
            storage_adapter = StorageAdapter(db_storage, device_identifier, protocol_storage_key)
            
            # Start pairing - pyatv pair() signature may vary by version
            loop = asyncio.get_event_loop()
            try:
                pairing = await pair(atv, target_protocol, loop=loop, storage=storage_adapter)
            except TypeError:
                pairing = await pair(atv, target_protocol, loop=loop)
            
            # Store (pairing, protocol_key) so submit_pin can save under the right key
            self._pairing_sessions[device_id] = (pairing, protocol_storage_key)
            
            # Start the pairing process (required so Apple TV shows PIN)
            await pairing.begin()
            
            # Check pairing requirement
            if pairing.device_provides_pin:
                return {
                    "status": "PIN_REQUIRED",
                    "message": "Enter PIN shown on Apple TV",
                }
            elif pairing.requires_credentials:
                return {
                    "status": "CREDENTIALS_REQUIRED",
                    "message": "Credentials required",
                }
            else:
                # Pairing completed automatically
                await pairing.finish()
                return {
                    "status": "COMPLETED",
                    "message": "Pairing completed",
                }
        except Exception as e:
            logger.error(f"Error starting pairing: {e}", exc_info=True)
            raise
    
    async def submit_pin(
        self, 
        device_id: str, 
        pin: str,
        address: str,
        protocol: str,
        credentials_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit PIN for pairing."""
        try:
            logger.info(f"Submitting PIN for {device_id}")
            
            session = self._pairing_sessions.get(device_id)
            if not session:
                raise ValueError("No active pairing session found")
            pairing = session[0] if isinstance(session, tuple) else session
            protocol_storage_key = session[1] if isinstance(session, tuple) and len(session) > 1 else "AirPlay"
            
            pairing.pin(pin)
            await pairing.finish()
            
            db_storage = DatabaseStorage(credentials_json)
            loop = asyncio.get_event_loop()
            atvs = await scan(loop=loop, hosts=[str(address)])
            if atvs:
                device_identifier = str(atvs[0].identifier)
                # Save under protocol key so we have two separate codes for AirPlay and Companion
                try:
                    if hasattr(pairing, 'service') and hasattr(pairing.service, 'credentials'):
                        creds = pairing.service.credentials
                        if creds:
                            db_storage.save(device_identifier, {protocol_storage_key: creds})
                except Exception:
                    pass
                
                del self._pairing_sessions[device_id]
                
                return {
                    "status": "COMPLETED",
                    "message": "Pairing completed successfully",
                    "credentials": db_storage.to_json(),  # Return updated credentials JSON
                }
            else:
                raise ValueError("Device not found after pairing")
        except Exception as e:
            logger.error(f"Error submitting PIN: {e}", exc_info=True)
            if device_id in self._pairing_sessions:
                del self._pairing_sessions[device_id]
            raise
    
    @staticmethod
    def _format_for_quality(quality: str) -> str:
        """yt-dlp format string. YouTube 720p+ is usually DASH (video-only); we take best single URL.
        Combined (video+audio) is often only 360p. For 720p/1080p we use bestvideo to get resolution (no audio)."""
        q = (quality or "auto").lower().strip()
        if q == "auto" or not q:
            # Prefer best combined format (video+audio) for AirPlay RTSP compatibility
            # DASH-only streams (video-only or audio-only) cause RTSP SETUP 400 errors
            return "best[ext=mp4]/best"
        if q == "1080p":
            # YouTube 1080p = DASH only; take bestvideo for resolution (video-only, no audio)
            return "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]/best[height<=1080]/best"
        if q == "720p":
            return "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[height<=720]/best"
        if q == "480p":
            return "best[height<=480][ext=mp4]/best[height<=480]/best"
        if q == "360p":
            return "best[height<=360][ext=mp4]/best[height<=360]/best"
        return "best[ext=mp4]/best[ext=m4a]/best"

    @staticmethod
    def _resolve_stream_url_blocking(url: str, quality: str = "auto") -> Optional[Dict[str, Any]]:
        """Resolve YouTube/page URL to direct stream URL; return dict with url and optional height/quality info."""
        if not HAS_YT_DLP or not yt_dlp:
            return None
        try:
            format_str = AppleTVService._format_for_quality(quality)
            opts = {
                "format": format_str,
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None
            result_url = info.get("url")
            if not result_url:
                for f in info.get("formats") or []:
                    if f.get("url"):
                        result_url = f["url"]
                        break
            if not result_url:
                return None
            # Build quality label so user can see chosen quality (e.g. in auto mode)
            height = info.get("height")
            if height is None and info.get("resolution"):
                try:
                    height = info["resolution"].split("x")[-1].strip()
                except Exception:
                    height = None
            if height is None and info.get("requested_formats"):
                for f in info["requested_formats"]:
                    if f.get("height"):
                        height = f["height"]
                        break
            format_note = info.get("format_note") or ""
            if height:
                quality_label = f"{height}p"
            elif format_note:
                quality_label = format_note
            else:
                quality_label = None
            return {"url": result_url, "quality_label": quality_label}
        except Exception as e:
            logger.warning(f"Could not resolve stream URL: {e}")
            return None

    async def _resolve_stream_url(self, url: str, quality: str = "auto") -> Optional[Dict[str, Any]]:
        """Resolve YouTube/page URL to direct stream URL (non-blocking). Returns dict with url and optional quality_label."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._resolve_stream_url_blocking, url, quality)

    def _is_direct_media_url(self, url: Optional[str]) -> bool:
        """Check if URL looks like direct media (stream), not a web/page link."""
        if not url or not isinstance(url, str):
            return False
        url_lower = url.lower().split("?")[0]
        direct_extensions = (".mp4", ".m4v", ".m3u8", ".ts", ".mov", ".webm", ".mkv")
        if any(url_lower.endswith(ext) or ext in url_lower for ext in direct_extensions):
            return True
        # Common streaming path patterns
        if "/stream/" in url_lower or "/video/" in url_lower or "/hls/" in url_lower:
            return True
        return False

    def _is_hls_url(self, url: Optional[str]) -> bool:
        """Check if URL is HLS (.m3u8) for server-side remux to MP4."""
        if not url or not isinstance(url, str):
            return False
        return ".m3u8" in url.lower()

    def _is_deep_link(self, url: Optional[str]) -> bool:
        """Check if URL is a deep link (app link) vs media URL."""
        if not url or not isinstance(url, str):
            return False
        deep_link_patterns = [
            'tv.apple.com',
            'disneyplus.com',
            'netflix.com',
            'hbomax.com',
            'hulu.com',
            'youtube.com',
            'youtu.be',
            'play.hbomax.com',
            'www.disneyplus.com',
            'www.netflix.com',
        ]
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in deep_link_patterns) or url.startswith('http')

    @staticmethod
    def _youtube_deep_link_url(url: str) -> Optional[str]:
        """Convert YouTube page URL to youtube:// deep link for Apple TV (plays in YouTube app, no conversion).
        See https://www.home-assistant.io/integrations/apple_tv/ — YouTube: youtube://www.youtube.com/watch?v=VIDEO_ID"""
        if not url or "youtube.com" not in url.lower() and "youtu.be" not in url.lower():
            return None
        video_id = None
        if "youtu.be/" in url.lower():
            try:
                from urllib.parse import urlparse
                path = urlparse(url).path.strip("/")
                video_id = path.split("?")[0].split("/")[0] if path else None
            except Exception:
                pass
        if not video_id and "watch?v=" in url.lower():
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(url)
                video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            except Exception:
                pass
        if video_id:
            return f"youtube://www.youtube.com/watch?v={video_id}"
        return None
    
    async def play_url(
        self,
        url: str,
        device_id: str,
        address: str,
        credentials_json: Optional[str] = None,
        quality: str = "auto",
    ) -> Dict[str, Any]:
        """Play a URL on Apple TV using AirPlay or launch deep link via Apps."""
        try:
            if not url or not isinstance(url, str) or not url.strip():
                raise ValueError("URL is required and must be a non-empty string")
            url = url.strip()
            logger.info(f"Playing/Launching URL {url} on device {device_id}")
            
            # Create storage from credentials
            storage = DatabaseStorage(credentials_json)
            
            # Scan for device (exclude DMAP to avoid pyatv login_id None error on Apple TV 3rd gen)
            loop = asyncio.get_event_loop()
            atvs = await scan(
                loop=loop,
                hosts=[str(address)],
                protocol={Protocol.AirPlay, Protocol.Companion, Protocol.MRP},
            )
            if not atvs:
                raise ValueError(f"Device not found at {address}")
            
            atv = atvs[0]
            
            # Set credentials on config before connecting
            device_identifier = str(atv.identifier) if hasattr(atv, 'identifier') else str(atv.address)
            stored_creds = storage.load(device_identifier)
            
            logger.info(f"Loading credentials for device {device_identifier}, found: {stored_creds is not None}")
            
            if stored_creds:
                # Apply credentials to config services
                try:
                    creds_dict = stored_creds if isinstance(stored_creds, dict) else {}
                    
                    # Set AirPlay credentials
                    airplay_service = atv.get_service(Protocol.AirPlay)
                    if airplay_service:
                        airplay_creds = None
                        if 'airplay' in creds_dict:
                            airplay_creds = creds_dict['airplay']
                        elif 'AirPlay' in creds_dict:
                            airplay_creds = creds_dict['AirPlay']
                        elif 'credentials' in creds_dict:
                            airplay_creds = creds_dict['credentials']
                        
                        if airplay_creds:
                            if isinstance(airplay_creds, str):
                                airplay_service.credentials = airplay_creds
                            elif isinstance(airplay_creds, dict):
                                airplay_service.credentials = airplay_creds.get('credentials') or airplay_creds
                            else:
                                airplay_service.credentials = airplay_creds
                            logger.info(f"Set AirPlay credentials for {device_identifier}")
                    
                    # Set Companion/MRP credentials for app launching
                    companion_service = atv.get_service(Protocol.Companion)
                    if companion_service:
                        companion_creds = creds_dict.get('companion') or creds_dict.get('Companion')
                        if companion_creds:
                            if isinstance(companion_creds, str):
                                companion_service.credentials = companion_creds
                            elif isinstance(companion_creds, dict):
                                companion_service.credentials = companion_creds.get('credentials') or companion_creds
                            else:
                                companion_service.credentials = companion_creds
                            logger.info(f"Set Companion credentials for {device_identifier}")
                except Exception as e:
                    logger.warning(f"Could not set credentials from storage: {e}", exc_info=True)
            
            # Check if we have AirPlay credentials (required for stream.play_url / YouTube playback)
            airplay_service = atv.get_service(Protocol.AirPlay)
            has_airplay_creds = False
            if stored_creds and isinstance(stored_creds, dict):
                creds_dict = stored_creds
                ap = creds_dict.get("airplay") or creds_dict.get("AirPlay") or creds_dict.get("credentials")
                has_airplay_creds = bool(ap)
            if airplay_service and not has_airplay_creds:
                logger.warning("AirPlay credentials missing - playback will likely fail with 'not authenticated'")
            
            # Connect to device
            atv_instance = await connect(atv, loop=loop)
            
            try:
                # Check available protocols
                available_protocols = []
                if atv.get_service(Protocol.AirPlay):
                    available_protocols.append("AirPlay")
                if atv.get_service(Protocol.Companion):
                    available_protocols.append("Companion")
                if atv.get_service(Protocol.MRP):
                    available_protocols.append("MRP")
                
                logger.info(f"Available protocols: {available_protocols}")
                
                # Apple TV 1st generation doesn't support AirPlay/Companion/MRP
                # For older devices, we can only provide basic info
                if not available_protocols:
                    logger.warning("No modern protocols available - this might be Apple TV 1st generation")
                    return {
                        "status": "LIMITED_SUPPORT",
                        "message": f"Apple TV 1st generation detected. Direct URL playback not supported. Please use iTunes sync or manual playback.",
                        "device_name": atv.name,
                        "address": str(atv.address),
                        "note": "Apple TV 1st generation does not support AirPlay or modern protocols",
                    }
                
                # Check if URL is a deep link (app link) or media URL
                is_deep_link = self._is_deep_link(url)
                is_direct_media = self._is_direct_media_url(url)
                has_apps = getattr(atv_instance, "apps", None) is not None

                # Don't try launch_app for direct media (.m3u8, .mp4): use AirPlay (and HLS→MP4 remux for .m3u8)
                if is_deep_link and has_apps and not is_direct_media:
                    # Try to launch as deep link via Apps interface (requires Companion/MRP)
                    # For YouTube use youtube:// scheme so the YouTube app plays natively (no conversion/ffmpeg)
                    try:
                        apps = atv_instance.apps
                        if apps:
                            launch_url = self._youtube_deep_link_url(url) or url
                            if launch_url != url:
                                logger.info(f"Launching YouTube deep link (no conversion): {launch_url}")
                            else:
                                logger.info(f"Launching deep link: {launch_url}")
                            await apps.launch_app(launch_url)
                            return {
                                "status": "SUCCESS",
                                "message": f"Открыто на {atv.name}" + (" (приложение YouTube)" if "youtube://" in launch_url else ""),
                                "method": "deep_link",
                            }
                    except Exception as e:
                        logger.warning(f"Failed to launch as deep link: {e}, falling back to AirPlay")
                
                # AirPlay: first try "Home Assistant way" (no conversion); on error retry with our remux/merge
                stream = atv_instance.stream
                if stream:
                    if not has_airplay_creds:
                        return {
                            "status": "NEED_AIRPLAY_PAIRING",
                            "message": "Для воспроизведения видео нужна сопряжение по AirPlay. Откройте настройки устройства, выберите этот Apple TV и выполните сопряжение по протоколу «AirPlay» (не только Companion).",
                            "device_name": atv.name,
                        }
                    self._last_merge_used = False
                    resolved_quality = None
                    base = (os.environ.get("STREAM_BASE_URL") or "http://localhost:8000").rstrip("/")
                    # Step 1: build URL the simple way (like HA — pass URL or single resolved stream)
                    if is_direct_media:
                        play_url_final = url
                    else:
                        # Page link (YouTube etc.): resolve to single stream URL
                        resolved = await self._resolve_stream_url(url, quality)
                        if not resolved:
                            return {
                                "status": "UNSUPPORTED_URL",
                                "message": "Не удалось получить прямую ссылку на видео. Поддерживаются YouTube и похожие сайты (нужен yt-dlp). Для Netflix/приложений используйте Apple TV 4-го поколения (tvOS) или вставьте прямую ссылку (.mp4, .m3u8).",
                                "device_name": atv.name,
                            }
                        play_url_final = resolved["url"]
                        resolved_quality = resolved.get("quality_label")
                    logger.info("Playing URL via AirPlay (HA-style): %s", play_url_final[:80] + ("..." if len(play_url_final) > 80 else ""))
                    try:
                        await stream.play_url(play_url_final)
                    except Exception as play_err:
                        err_str = str(play_err).lower()
                        # Retry with conversion if Apple TV rejected (RTSP 400 / format)
                        if "400" in err_str or "rtsp" in err_str or "bad request" in err_str:
                            if is_direct_media and self._is_hls_url(url):
                                try:
                                    from app.stream_merge import create_hls_session, wait_hls_prewarm
                                    stream_id = create_hls_session(url)
                                    play_url_final = f"{base}/api/appletv/stream/{stream_id}"
                                    self._last_merge_used = True
                                    logger.info("HLS failed, retrying with HLS→MP4 remux: %s", stream_id)
                                    # Wait for pre-warm (64KB) so Apple TV gets data immediately and RTSP SETUP succeeds
                                    await wait_hls_prewarm(stream_id, timeout=15.0, min_bytes=65536)
                                    await stream.play_url(play_url_final)
                                except Exception as e2:
                                    err_detail = str(e2).strip() or type(e2).__name__
                                    logger.warning("HLS remux retry failed: %s", e2, exc_info=True)
                                    return {
                                        "status": "HLS_REMUX_FAILED",
                                        "message": f"HLS-поток не воспроизводится напрямую. Remux не удался: {err_detail}. Убедитесь, что STREAM_BASE_URL ({base}) доступен с Apple TV (откройте в браузере с телефона в той же Wi‑Fi).",
                                        "device_name": atv.name,
                                    }
                            elif is_deep_link and not is_direct_media and quality in ("720p", "1080p", "auto"):
                                try:
                                    from app.stream_merge import get_video_audio_urls, create_merge_session
                                    merge_info = await get_video_audio_urls(url, quality if quality != "auto" else "720p")
                                    if merge_info:
                                        stream_id = create_merge_session(
                                            merge_info["video_url"],
                                            merge_info["audio_url"],
                                            merge_info.get("height"),
                                        )
                                        play_url_final = f"{base}/api/appletv/stream/{stream_id}"
                                        resolved_quality = f"{merge_info.get('height') or (quality if quality != 'auto' else '720')}p" if merge_info.get("height") else (quality if quality != "auto" else "720p")
                                        self._last_merge_used = True
                                        logger.info("Direct stream failed, retrying with merge (quality: %s)", resolved_quality)
                                        await stream.play_url(play_url_final)
                                    else:
                                        raise play_err
                                except Exception as e2:
                                    if e2 is play_err:
                                        raise
                                    logger.warning("Merge retry failed: %s", e2)
                                    raise play_err
                            else:
                                raise play_err
                        else:
                            raise play_err
                    msg = f"Воспроизведение на {atv.name}"
                    if resolved_quality:
                        msg += f" • качество: {resolved_quality}"
                    if self._last_merge_used:
                        msg += " • склейка на сервере"
                    return {
                        "status": "SUCCESS",
                        "message": msg,
                        "method": "airplay",
                        "resolved_quality": resolved_quality,
                        "merge_used": self._last_merge_used,
                    }
                else:
                    raise ValueError("Neither Apps nor Stream interface available on this device")
            finally:
                atv_instance.close()
        except Exception as e:
            logger.error(f"Error playing/launching URL: {e}", exc_info=True)
            err_lower = str(e).lower()
            if "not authenticated" in err_lower or "authentication" in err_lower or "pairing" in err_lower:
                raise ValueError(
                    "Устройство не авторизовано для AirPlay. Выполните сопряжение по протоколу AirPlay: настройки → выберите этот Apple TV → сопряжение по AirPlay."
                ) from e
            raise

    async def stop_playback(
        self,
        device_id: str,
        address: str,
        credentials_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stop AirPlay stream: send Menu (back) to exit playback and end the stream."""
        try:
            loop = asyncio.get_event_loop()
            atvs = await scan(
                loop=loop,
                hosts=[str(address)],
                protocol={Protocol.AirPlay, Protocol.Companion, Protocol.MRP},
            )
            if not atvs:
                raise ValueError(f"Device not found at {address}")
            atv = atvs[0]
            storage = DatabaseStorage(credentials_json)
            device_identifier = str(atv.identifier) if hasattr(atv, "identifier") else str(atv.address)
            stored_creds = storage.load(device_identifier)
            if stored_creds:
                creds_dict = stored_creds if isinstance(stored_creds, dict) else {}
                airplay_service = atv.get_service(Protocol.AirPlay)
                if airplay_service:
                    airplay_creds = creds_dict.get("airplay") or creds_dict.get("AirPlay") or creds_dict.get("credentials")
                    if airplay_creds:
                        airplay_service.credentials = airplay_creds if isinstance(airplay_creds, str) else airplay_creds.get("credentials") or airplay_creds
            atv_instance = await connect(atv, loop=loop)
            try:
                rc = atv_instance.remote_control
                if rc:
                    await rc.menu()
                    return {"status": "SUCCESS", "message": f"Трансляция остановлена на {atv.name}"}
                raise ValueError("Remote control not available")
            finally:
                atv_instance.close()
        except Exception as e:
            logger.error(f"Error stopping playback: {e}", exc_info=True)
            raise

    def get_stored_credentials(self, credentials_json: Optional[str]) -> Dict[str, Any]:
        """Get credentials from database JSON."""
        storage = DatabaseStorage(credentials_json)
        return storage.get_all()
    
    async def add_device_manually(self, address: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Manually add a device by IP address."""
        try:
            logger.info(f"Manually adding device at {address}")
            loop = asyncio.get_event_loop()
            
            # Try to scan for the device at the given address
            atvs = await scan(loop=loop, hosts=[str(address)])
            
            if not atvs:
                # Device not found, but create entry anyway with provided info
                device_info = {
                    "device_id": f"{address}_{name or 'Apple TV'}",
                    "name": name or "Apple TV",
                    "address": address,
                    "protocols": ["airplay", "companion"],  # Default assumptions
                    "identifier": None,
                }
                logger.warning(f"Device not found at {address}, creating entry anyway")
                return device_info
            
            # Device found, get real info
            atv = atvs[0]
            protocols = []
            if atv.get_service(Protocol.AirPlay):
                protocols.append("airplay")
            if atv.get_service(Protocol.Companion):
                protocols.append("companion")
            if atv.get_service(Protocol.MRP):
                protocols.append("mrp")
            
            device_info = {
                "device_id": f"{atv.address}_{atv.name}",
                "name": atv.name,
                "address": str(atv.address),
                "protocols": protocols,
                "identifier": str(atv.identifier) if hasattr(atv, 'identifier') else None,
            }
            
            logger.info(f"Found device: {device_info['name']} at {device_info['address']}")
            return device_info
        except Exception as e:
            logger.error(f"Error manually adding device: {e}", exc_info=True)
            # Return device info anyway so user can add it
            return {
                "device_id": f"{address}_{name or 'Apple TV'}",
                "name": name or "Apple TV",
                "address": address,
                "protocols": ["airplay", "companion"],
                "identifier": None,
            }
