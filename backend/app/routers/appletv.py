"""Apple TV API routes."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from app.database import get_db
from app.stream_merge import stream_merged_mp4_async, get_merge_session
from app.models import Device, DefaultDevice
from app.services.appletv_service import AppleTVService
from app.activity_log import add as log_add, get as log_get

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appletv", tags=["appletv"])

appletv_service = AppleTVService()


# Request/Response models
class DeviceInfo(BaseModel):
    device_id: str
    name: str
    address: str
    protocols: List[str]


class PairedDevice(BaseModel):
    id: int
    device_id: str
    name: str
    address: str
    protocols: List[str]
    last_seen: Optional[str] = None
    created_at: str


class PairStartRequest(BaseModel):
    protocol: str


class PairPinRequest(BaseModel):
    pin: str


class PlayRequest(BaseModel):
    url: str
    device_id: Optional[str] = None
    quality: Optional[str] = "auto"  # auto | 1080p | 720p | 480p | 360p


class DefaultDeviceRequest(BaseModel):
    device_id: str


class AddDeviceRequest(BaseModel):
    address: str
    name: Optional[str] = None


class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class ApiResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


def success_response(data: dict) -> ApiResponse:
    """Create success response."""
    return ApiResponse(ok=True, data=data)


def error_response(code: str, message: str, details: Optional[dict] = None) -> ApiResponse:
    """Create error response."""
    return ApiResponse(
        ok=False,
        error={"code": code, "message": message, "details": details or {}}
    )


@router.get("/scan", response_model=ApiResponse)
async def scan_devices():
    """Scan for Apple TV devices on the local network."""
    try:
        devices = await appletv_service.scan_devices()
        return success_response({"devices": devices})
    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        return error_response("SCAN_FAILED", str(e))


@router.get("/devices", response_model=ApiResponse)
async def get_paired_devices(db: Session = Depends(get_db)):
    """Get list of paired devices."""
    try:
        devices = db.query(Device).all()
        result = []
        for device in devices:
            import json
            protocols = json.loads(device.protocols) if device.protocols else []
            
            # Check if device is actually paired (has non-empty credentials)
            credentials = json.loads(device.credentials) if device.credentials else {}
            is_paired = bool(credentials and credentials != {})
            
            result.append({
                "id": device.id,
                "device_id": device.device_id,
                "name": device.name,
                "address": device.address,
                "protocols": protocols,
                "is_paired": is_paired,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                "created_at": device.created_at.isoformat() if device.created_at else None,
            })
        return success_response({"devices": result})
    except Exception as e:
        logger.error(f"Get devices error: {e}", exc_info=True)
        return error_response("GET_DEVICES_FAILED", str(e))


@router.get("/stream/{stream_id}")
async def stream_merged(stream_id: str):
    """Stream merged video+audio (e.g. YouTube 1080p). Used by Apple TV when playing merge URL."""
    if not get_merge_session(stream_id):
        raise HTTPException(status_code=404, detail="Stream not found or expired")
    return StreamingResponse(
        stream_merged_mp4_async(stream_id),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"},
    )


@router.get("/activity", response_model=ApiResponse)
async def get_activity(limit: int = 50):
    """Get recent URL operation log (newest first)."""
    try:
        entries = log_get(limit=min(limit, 100))
        return success_response({"entries": entries})
    except Exception as e:
        logger.error(f"Get activity error: {e}", exc_info=True)
        return error_response("GET_ACTIVITY_FAILED", str(e))


@router.delete("/devices/{device_id}", response_model=ApiResponse)
async def delete_device(device_id: str, db: Session = Depends(get_db)):
    """Remove a device from the database."""
    try:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            return error_response("DEVICE_NOT_FOUND", f"Device {device_id} not found")
        # Clear default if this device was default
        default = db.query(DefaultDevice).filter(DefaultDevice.device_id == device_id).first()
        if default:
            db.delete(default)
        db.delete(device)
        db.commit()
        return success_response({"message": "Device removed"})
    except Exception as e:
        logger.error(f"Delete device error: {e}", exc_info=True)
        return error_response("DELETE_DEVICE_FAILED", str(e))


@router.patch("/devices/{device_id}", response_model=ApiResponse)
async def update_device(
    device_id: str,
    request: UpdateDeviceRequest,
    db: Session = Depends(get_db)
):
    """Update device name or address."""
    try:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            return error_response("DEVICE_NOT_FOUND", f"Device {device_id} not found")
        if request.name is not None:
            device.name = (request.name or "").strip() or device.name
        if request.address is not None:
            device.address = (request.address or "").strip() or device.address
        db.commit()
        import json
        protocols = json.loads(device.protocols) if device.protocols else []
        return success_response({
            "device": {
                "id": device.id,
                "device_id": device.device_id,
                "name": device.name,
                "address": device.address,
                "protocols": protocols,
            },
            "message": "Device updated",
        })
    except Exception as e:
        logger.error(f"Update device error: {e}", exc_info=True)
        return error_response("UPDATE_DEVICE_FAILED", str(e))


@router.post("/{device_id}/pair/start", response_model=ApiResponse)
async def start_pairing(
    device_id: str,
    request: PairStartRequest,
    db: Session = Depends(get_db)
):
    """Start pairing process with a device."""
    try:
        # Get device info from scan or database
        device = db.query(Device).filter(Device.device_id == device_id).first()
        
        if device:
            # Use stored device info
            address = device.address
            credentials_json = device.credentials
        else:
            # Device not in DB yet, need to scan
            scanned = await appletv_service.scan_devices()
            device_info = next((d for d in scanned if d["device_id"] == device_id), None)
            if not device_info:
                return error_response("DEVICE_NOT_FOUND", f"Device {device_id} not found")
            address = device_info["address"]
            credentials_json = None
        
        result = await appletv_service.start_pairing(
            device_id=device_id,
            address=address,
            protocol=request.protocol,
            credentials_json=credentials_json
        )
        
        return success_response(result)
    except Exception as e:
        logger.error(f"Start pairing error: {e}", exc_info=True)
        return error_response("PAIRING_START_FAILED", str(e))


@router.post("/{device_id}/pair/pin", response_model=ApiResponse)
async def submit_pin(
    device_id: str,
    request: PairPinRequest,
    db: Session = Depends(get_db)
):
    """Submit PIN for pairing."""
    try:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        credentials_json = device.credentials if device else None
        
        # Get device address and protocol from pairing session or device
        if not device:
            # Try to get from scan
            scanned = await appletv_service.scan_devices()
            device_info = next((d for d in scanned if d["device_id"] == device_id), None)
            if not device_info:
                return error_response("DEVICE_NOT_FOUND", f"Device {device_id} not found")
            address = device_info["address"]
            # Default to airplay if not specified
            protocol = device_info["protocols"][0] if device_info["protocols"] else "airplay"
        else:
            address = device.address
            import json
            protocols = json.loads(device.protocols) if device.protocols else []
            protocol = protocols[0] if protocols else "airplay"
        
        result = await appletv_service.submit_pin(
            device_id=device_id,
            pin=request.pin,
            address=address,
            protocol=protocol,
            credentials_json=credentials_json
        )
        
        if result["status"] == "COMPLETED":
            # Save/update device in database with credentials
            import json
            from datetime import datetime
            
            # Get updated credentials from result
            updated_credentials = result.get("credentials", credentials_json or "{}")
            
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                # Create new device entry
                scanned = await appletv_service.scan_devices()
                device_info = next((d for d in scanned if d["device_id"] == device_id), None)
                if device_info:
                    device = Device(
                        device_id=device_id,
                        name=device_info["name"],
                        address=device_info["address"],
                        protocols=json.dumps(device_info["protocols"]),
                        credentials=updated_credentials,
                        last_seen=datetime.now()
                    )
                    db.add(device)
                else:
                    # Create device entry with minimal info
                    device = Device(
                        device_id=device_id,
                        name="Apple TV",
                        address=address,
                        protocols=json.dumps([protocol]),
                        credentials=updated_credentials,
                        last_seen=datetime.now()
                    )
                    db.add(device)
            else:
                device.credentials = updated_credentials
                device.last_seen = datetime.now()
            
            db.commit()
        
        return success_response(result)
    except Exception as e:
        logger.error(f"Submit PIN error: {e}", exc_info=True)
        return error_response("PAIRING_PIN_FAILED", str(e))


@router.post("/play", response_model=ApiResponse)
async def play_url(request: PlayRequest, db: Session = Depends(get_db)):
    """Play a URL on Apple TV."""
    device_id = None
    device_name = ""
    url_truncated = (request.url or "")[:80] + ("..." if len(request.url or "") > 80 else "")

    try:
        device_id = request.device_id

        # If no device_id provided, use default
        if not device_id:
            default = db.query(DefaultDevice).first()
            if not default:
                log_add({"status": "error", "url": url_truncated, "device": "", "message": "No default device set"})
                return error_response("NO_DEFAULT_DEVICE", "No default device set")
            device_id = default.device_id

        # Get device from database
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            log_add({"status": "error", "url": url_truncated, "device": "", "message": "Device not found"})
            return error_response("DEVICE_NOT_FOUND", f"Device {device_id} not found")
        device_name = device.name or device_id

        log_add({"status": "start", "url": url_truncated, "device": device_name, "message": "Отправка на Apple TV…"})

        result = await appletv_service.play_url(
            url=request.url,
            device_id=device_id,
            address=device.address,
            credentials_json=device.credentials,
            quality=request.quality or "auto",
        )

        if result.get("status") == "UNSUPPORTED_URL":
            msg = result.get("message", "This URL is not supported for playback on this device.")
            log_add({"status": "error", "url": url_truncated, "device": device_name, "message": msg})
            return error_response("UNSUPPORTED_URL", msg)
        log_add({
            "status": "success",
            "url": url_truncated,
            "device": device_name,
            "message": result.get("message") or "Воспроизведение запущено",
            "method": result.get("method"),
            "merge_used": result.get("merge_used", False),
        })
        return success_response(result)
    except Exception as e:
        err_msg = str(e)
        log_add({"status": "error", "url": url_truncated, "device": device_name or (device_id or ""), "message": err_msg})
        logger.error(f"Play URL error: {e}", exc_info=True)
        return error_response("PLAY_FAILED", err_msg)


@router.post("/stop", response_model=ApiResponse)
async def stop_playback(db: Session = Depends(get_db)):
    """Stop (pause) playback on default Apple TV."""
    try:
        default = db.query(DefaultDevice).first()
        if not default:
            log_add({"status": "error", "url": "", "device": "", "message": "Устройство по умолчанию не задано"})
            return error_response("NO_DEFAULT_DEVICE", "No default device set")
        device = db.query(Device).filter(Device.device_id == default.device_id).first()
        if not device:
            log_add({"status": "error", "url": "", "device": "", "message": "Устройство не найдено"})
            return error_response("DEVICE_NOT_FOUND", "Device not found")
        result = await appletv_service.stop_playback(
            device_id=device.device_id,
            address=device.address,
            credentials_json=device.credentials,
        )
        log_add({
            "status": "success",
            "url": "",
            "device": device.name or device.device_id,
            "message": result.get("message") or "Трансляция остановлена",
        })
        return success_response(result)
    except Exception as e:
        log_add({"status": "error", "url": "", "device": "", "message": str(e)})
        logger.error(f"Stop playback error: {e}", exc_info=True)
        return error_response("STOP_FAILED", str(e))


@router.post("/default", response_model=ApiResponse)
async def set_default_device(request: DefaultDeviceRequest, db: Session = Depends(get_db)):
    """Set default Apple TV device."""
    try:
        # Verify device exists
        device = db.query(Device).filter(Device.device_id == request.device_id).first()
        if not device:
            return error_response("DEVICE_NOT_FOUND", f"Device {request.device_id} not found")
        
        # Update or create default device
        default = db.query(DefaultDevice).first()
        if default:
            default.device_id = request.device_id
        else:
            default = DefaultDevice(device_id=request.device_id)
            db.add(default)
        
        db.commit()
        
        return success_response({"device_id": request.device_id})
    except Exception as e:
        logger.error(f"Set default device error: {e}", exc_info=True)
        return error_response("SET_DEFAULT_FAILED", str(e))


@router.get("/default", response_model=ApiResponse)
async def get_default_device(db: Session = Depends(get_db)):
    """Get default Apple TV device."""
    try:
        default = db.query(DefaultDevice).first()
        if not default:
            return success_response({"device_id": None})
        
        device = db.query(Device).filter(Device.device_id == default.device_id).first()
        if not device:
            return success_response({"device_id": None})
        
        import json
        protocols = json.loads(device.protocols) if device.protocols else []
        
        return success_response({
            "device_id": device.device_id,
            "name": device.name,
            "address": device.address,
            "protocols": protocols,
        })
    except Exception as e:
        logger.error(f"Get default device error: {e}", exc_info=True)
        return error_response("GET_DEFAULT_FAILED", str(e))


@router.post("/add", response_model=ApiResponse)
async def add_device_manually(request: AddDeviceRequest, db: Session = Depends(get_db)):
    """Manually add an Apple TV device by IP address."""
    try:
        # Get device info from service
        device_info = await appletv_service.add_device_manually(
            address=request.address,
            name=request.name
        )
        
        # Check if device already exists
        existing = db.query(Device).filter(Device.device_id == device_info["device_id"]).first()
        
        if existing:
            # Update existing device
            import json
            from datetime import datetime
            existing.name = device_info["name"]
            existing.address = device_info["address"]
            existing.protocols = json.dumps(device_info["protocols"])
            existing.last_seen = datetime.now()
            db.commit()
            
            # Check if actually paired
            credentials = json.loads(existing.credentials) if existing.credentials else {}
            is_paired = bool(credentials and credentials != {})
            
            return success_response({
                "device": {
                    "id": existing.id,
                    "device_id": existing.device_id,
                    "name": existing.name,
                    "address": existing.address,
                    "protocols": device_info["protocols"],
                    "is_paired": is_paired,
                },
                "message": "Device updated",
            })
        else:
            # Create new device entry
            import json
            from datetime import datetime
            
            device = Device(
                device_id=device_info["device_id"],
                name=device_info["name"],
                address=device_info["address"],
                protocols=json.dumps(device_info["protocols"]),
                credentials="{}",  # Empty credentials, will be set during pairing
                last_seen=datetime.now()
            )
            db.add(device)
            db.commit()
            db.refresh(device)
            
            return success_response({
                "device": {
                    "id": device.id,
                    "device_id": device.device_id,
                    "name": device.name,
                    "address": device.address,
                    "protocols": device_info["protocols"],
                    "is_paired": False,  # Not paired yet, needs pairing
                },
                "message": "Device added successfully",
            })
    except Exception as e:
        logger.error(f"Add device error: {e}", exc_info=True)
        return error_response("ADD_DEVICE_FAILED", str(e))
