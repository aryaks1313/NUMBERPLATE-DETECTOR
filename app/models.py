
from sqlalchemy import (
    Column, Integer, String, Date, Time, Float,
    ForeignKey, DateTime, Text, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Advisor(Base):
    __tablename__ = "advisors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(300), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(150), nullable=True)

    # ADDED: advisor account activation
    is_active = Column(Boolean, default=True, nullable=False)

    bookings = relationship("Booking", back_populates="advisor")
    notifications = relationship("Notification", back_populates="advisor")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=False)
    vehicle_number = Column(String(30), nullable=False, index=True)
    vehicle_model = Column(String(120), nullable=False)
    booking_date = Column(Date, nullable=False, index=True)
    booking_time = Column(String(20))
    service_type = Column(String(150), nullable=False)
    status = Column(String(40), default="Scheduled")

    advisor_id = Column(
        Integer,
        ForeignKey("advisors.id"),
        nullable=False,
        index=True
    )

    advisor = relationship("Advisor", back_populates="bookings")
    detections = relationship("Detection", back_populates="booking")


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(30), nullable=True, index=True)
    ocr_text = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    image_path = Column(String(300))
    match_status = Column(String(40), default="Not matched")

    booking_id = Column(
        Integer,
        ForeignKey("bookings.id"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    booking = relationship("Booking", back_populates="detections")
    notifications = relationship("Notification", back_populates="detection")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    detection_id = Column(
        Integer,
        ForeignKey("detections.id"),
        nullable=False
    )

    advisor_id = Column(
        Integer,
        ForeignKey("advisors.id"),
        nullable=False,
        index=True
    )

    message = Column(Text, nullable=False)
    channel = Column(String(30), nullable=False)
    status = Column(String(40), default="Created")

    
    is_read = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    detection = relationship("Detection", back_populates="notifications")
    advisor = relationship("Advisor", back_populates="notifications")
