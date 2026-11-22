from datetime import date, time
from pydantic import BaseModel, ConfigDict, Field


class AdvisorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    email: str | None = None


class BookingCreate(BaseModel):
    customer_name: str
    phone: str
    vehicle_number: str
    vehicle_model: str
    booking_date: date
    booking_time: time
    service_type: str
    status: str = "Scheduled"
    advisor_id: int


class BookingOut(BookingCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class BookingCreateRequest(BaseModel):
    customer_name: str
    phone: str
    vehicle_number: str
    vehicle_model: str
    booking_date: date
    booking_time: time
    service_type: str
    status: str = "Scheduled"
    advisor_id: int