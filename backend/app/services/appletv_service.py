"""Apple TV service using pyatv."""
import asyncio
import logging
from typing import List, Optional, Dict, Any
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
        self._pairing_sessions: Dict[str, PairingHandler] = {}
    
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
            
            # Create storage from existing credentials if available
            db_storage = DatabaseStorage(credentials_json)
            device_identifier = str(atv.identifier)
            
            # Create a simple storage adapter for pyatv
            # pyatv's pair() function accepts a storage parameter that should have save/load/get_settings
            class StorageAdapter:
                def __init__(self, db_storage: DatabaseStorage, identifier: str):
                    self._db_storage = db_storage
                    self._identifier = identifier
                
                def save(self, credentials: Dict[str, Any]) -> None:
                    """Save credentials for the device."""
                    self._db_storage.save(self._identifier, credentials)
                
                def load(self) -> Optional[Dict[str, Any]]:
                    """Load credentials for the device."""
                    return self._db_storage.load(self._identifier)
                
                def get_settings(self, identifier: str) -> Optional[Dict[str, Any]]:
                    """Get settings for a device identifier."""
                    return self._db_storage.load(identifier)
            
            storage_adapter = StorageAdapter(db_storage, device_identifier)
            
            # Start pairing - pyatv pair() signature may vary by version
            loop = asyncio.get_event_loop()
            # Try with storage parameter first
            try:
                pairing = await pair(atv, target_protocol, loop=loop, storage=storage_adapter)
            except TypeError:
                # Fallback if storage parameter not supported
                pairing = await pair(atv, target_protocol, loop=loop)
            
            # Store pairing session
            self._pairing_sessions[device_id] = pairing
            
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
            
            pairing = self._pairing_sessions.get(device_id)
            if not pairing:
                raise ValueError("No active pairing session found")
            
            pairing.pin(pin)
            await pairing.finish()
            
            # Get updated credentials from storage
            db_storage = DatabaseStorage(credentials_json)
            # The pairing process should have saved credentials via the adapter
            # Get the device identifier to retrieve credentials
            loop = asyncio.get_event_loop()
            atvs = await scan(loop=loop, hosts=[str(address)])
            # scan() returns a list
            if atvs:
                device_identifier = str(atvs[0].identifier)
                # Ensure credentials are saved
                # If storage adapter was used, credentials should already be saved
                # Otherwise, we need to get them from the pairing result
                try:
                    # Try to get credentials from pairing
                    if hasattr(pairing, 'service') and hasattr(pairing.service, 'credentials'):
                        creds = pairing.service.credentials
                        if creds:
                            db_storage.save(device_identifier, creds)
                except Exception:
                    pass  # Credentials may already be saved via adapter
                
                # Clean up pairing session
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
        """yt-dlp format string for requested quality (single stream preferred)."""
        q = (quality or "auto").lower().strip()
        if q == "auto" or not q:
            return "best[ext=mp4]/best[ext=m4a]/best"
        if q == "1080p":
            return "best[height<=1080][ext=mp4]/best[height<=1080]/best"
        if q == "720p":
            return "best[height<=720][ext=mp4]/best[height<=720]/best"
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

                if is_deep_link and has_apps:
                    # Try to launch as deep link via Apps interface (requires Companion/MRP)
                    try:
                        apps = atv_instance.apps
                        if apps:
                            logger.info(f"Launching deep link: {url}")
                            await apps.launch_app(url)
                            return {
                                "status": "SUCCESS",
                                "message": f"Launched deep link {url} on {atv.name}",
                                "method": "deep_link",
                            }
                    except Exception as e:
                        logger.warning(f"Failed to launch as deep link: {e}, falling back to AirPlay")
                
                # AirPlay: only direct media URLs work; page links (YouTube, etc.) can be resolved via yt-dlp
                stream = atv_instance.stream
                if stream:
                    play_url_final = url
                    resolved_quality = None
                    if is_deep_link and not is_direct_media:
                        # Try to resolve to direct stream (e.g. YouTube -> direct URL)
                        resolved = await self._resolve_stream_url(url, quality)
                        if resolved:
                            play_url_final = resolved["url"]
                            resolved_quality = resolved.get("quality_label")
                            logger.info(f"Resolved URL to direct stream (quality: {resolved_quality or '?'}), playing via AirPlay")
                        else:
                            return {
                                "status": "UNSUPPORTED_URL",
                                "message": "Не удалось получить прямую ссылку на видео. Поддерживаются YouTube и похожие сайты (нужен yt-dlp). Для Netflix/приложений используйте Apple TV 4-го поколения (tvOS) или вставьте прямую ссылку (.mp4, .m3u8).",
                                "device_name": atv.name,
                            }
                    logger.info("Playing URL via AirPlay: %s", play_url_final[:80] + ("..." if len(play_url_final) > 80 else ""))
                    await stream.play_url(play_url_final)
                    msg = f"Воспроизведение на {atv.name}"
                    if resolved_quality:
                        msg += f" • качество: {resolved_quality}"
                    return {
                        "status": "SUCCESS",
                        "message": msg,
                        "method": "airplay",
                        "resolved_quality": resolved_quality,
                    }
                else:
                    raise ValueError("Neither Apps nor Stream interface available on this device")
            finally:
                atv_instance.close()
        except Exception as e:
            logger.error(f"Error playing/launching URL: {e}", exc_info=True)
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
