from uuid import UUID
from schemander import (
    Date,
    Email,
    IANATimeZone,
    Phone,
    Schema,
)


class User(Schema):
    id: UUID
    name_first: str
    name_middle: str | None
    name_last: str
    email: Email
    phone: Phone | None
    date_of_birth: Date
    timezone: IANATimeZone


# This would be a usual result when decoding a JSON.
data = {
    "id": "5f85b586-a08b-4a1f-8086-4e6228a7aa7f",
    "name_first": "Jenny",
    "name_last": "Totone",
    "date_of_birth": "1990-01-01",
    "email": "example@example.com",
    "phone": "+1 (619) 867-5309",
    "timezone": "America/Los_Angeles",
}

obj = User.from_dict(data)
print(obj)
