from pydantic import BaseModel, Field

from gpt_auto_register.modules.auth.schemas import SessionResponse


class SetupStatusResponse(BaseModel):
    initialized: bool
    authentication_enabled: bool


class SetupPreflightResponse(BaseModel):
    database: str
    data_directory_writable: bool
    master_key_file: str


class SetupInitializeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=1024)


class SetupInitializeResponse(SessionResponse):
    initialized: bool = True
