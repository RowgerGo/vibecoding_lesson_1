from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Username = Annotated[str, StringConstraints(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")]
PositiveId = Annotated[int, Field(strict=True, gt=0)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: Username
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ChangePassword(Input):
    old_password: str = Field(max_length=128)
    new_password: Password


class ResetPassword(Input):
    new_password: Password


class DepartmentCreate(Input):
    name: Text80


class Enabled(Input):
    enabled: bool = Field(strict=True)


class Head(Input):
    user_id: PositiveId


class UserCreate(Input):
    username: Username
    name: Text80
    password: Password
    department_id: PositiveId | None = None
    is_admin: bool = Field(default=False, strict=True)
    enabled: bool = Field(default=True, strict=True)


class ApplicationCreate(Input):
    event_date: date
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    approval_department_id: PositiveId


class Decision(Input):
    decision: Literal["approved", "rejected"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
