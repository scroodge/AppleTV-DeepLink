"""Database models."""
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class Device(Base):
    """Apple TV device model."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)  # IP address
    protocols = Column(Text)  # JSON array of supported protocols
    credentials = Column(Text)  # JSON blob of pyatv credentials
    last_seen = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Device(id={self.id}, name={self.name}, address={self.address})>"


class DefaultDevice(Base):
    """Default Apple TV device selection."""
    __tablename__ = "default_device"

    device_id = Column(String, primary_key=True, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<DefaultDevice(device_id={self.device_id})>"
