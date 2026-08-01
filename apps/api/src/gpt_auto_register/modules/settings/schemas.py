from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RegistrationSettings(BaseModel):
    concurrency: int = Field(default=10, ge=1, le=50)
    otp_timeout: int = Field(default=10, ge=1, le=300)
    allow_existing_login: bool = True
    password_mode: Literal["none", "random", "fixed"] = "random"
    fixed_password: str = Field(default="", max_length=256)
    enable_authenticator_mfa: bool = False
    want_access_token: bool = True
    want_session_token: bool = True
    want_refresh_token: bool = True
    proxy: str = ""
    proxy_pool: str = ""

    @model_validator(mode="after")
    def validate_fixed_password(self) -> "RegistrationSettings":
        if self.password_mode == "fixed" and not self.fixed_password:
            raise ValueError("固定密码模式必须填写密码")
        return self


class KakaoSettings(BaseModel):
    base_url: str = ""
    timeout: int = Field(default=30, ge=5, le=300)
    card_usage_limit: int = Field(default=10, ge=1, le=1000)
    plan_type: Literal["plus"] = "plus"
    promo_code: str = ""


class MailSettings(BaseModel):
    source: Literal["outlook", "cf_temp"] = "outlook"
    cf_api_url: str = ""
    cf_domain: str = ""
    cf_admin_token_configured: bool = False


class MailSettingsUpdate(BaseModel):
    source: Literal["outlook", "cf_temp"] = "outlook"
    cf_api_url: str = ""
    cf_domain: str = ""
    cf_admin_token: str = ""


class SmsSettings(BaseModel):
    enabled: bool = False
    provider: Literal["smsbower", "herosms", "grizzlysms"] = "smsbower"
    country: str = "52"
    service: str = "dr"
    max_price: str = ""
    reuse_phone: bool = False
    phone_success_max: int = Field(default=3, ge=1, le=20)
    auto_country: bool = False
    strict_whitelist: bool = False
    allowed_countries: str = ""
    auto_min_stock: int = Field(default=20, ge=0)
    auto_max_price: str = ""
    max_phone_attempts: int = Field(default=3, ge=1, le=20)
    per_phone_timeout: int = Field(default=80, ge=40, le=600)
    api_key_configured: bool = False


class ExportTargetSettings(BaseModel):
    enabled: bool = False
    url: str = ""
    timeout: int = Field(default=30, ge=5, le=300)
    key_configured: bool = False


class ExportSettings(BaseModel):
    cpa: ExportTargetSettings = Field(default_factory=ExportTargetSettings)
    sub2api: ExportTargetSettings = Field(default_factory=ExportTargetSettings)
    sub2api_group_ids: str = ""


class SystemSettingsResponse(BaseModel):
    registration: RegistrationSettings
    mail: MailSettings
    kakao: KakaoSettings
    sms: SmsSettings
    export: ExportSettings


class SmsSettingsUpdate(BaseModel):
    enabled: bool = False
    provider: Literal["smsbower", "herosms", "grizzlysms"] = "smsbower"
    country: str = "52"
    service: str = "dr"
    max_price: str = ""
    reuse_phone: bool = False
    phone_success_max: int = Field(default=3, ge=1, le=20)
    auto_country: bool = False
    strict_whitelist: bool = False
    allowed_countries: str = ""
    auto_min_stock: int = Field(default=20, ge=0)
    auto_max_price: str = ""
    max_phone_attempts: int = Field(default=3, ge=1, le=20)
    per_phone_timeout: int = Field(default=80, ge=40, le=600)
    api_key: str = ""


class ExportTargetUpdate(BaseModel):
    enabled: bool = False
    url: str = ""
    timeout: int = Field(default=30, ge=5, le=300)
    key: str = ""


class ExportSettingsUpdate(BaseModel):
    cpa: ExportTargetUpdate = Field(default_factory=ExportTargetUpdate)
    sub2api: ExportTargetUpdate = Field(default_factory=ExportTargetUpdate)
    sub2api_group_ids: str = ""


class SystemSettingsUpdate(BaseModel):
    registration: RegistrationSettings
    mail: MailSettingsUpdate
    kakao: KakaoSettings
    sms: SmsSettingsUpdate
    export: ExportSettingsUpdate


class SmsTestResponse(BaseModel):
    balance: float


class SmsCountry(BaseModel):
    id: str
    name: str
    safe: bool
    price: float | None = None
    count: int | None = None


class SmsCountryListResponse(BaseModel):
    items: list[SmsCountry]
    live: bool


class ConnectionTestResponse(BaseModel):
    message: str


BackupSection = Literal["settings", "accounts", "credentials", "card_batches", "cards"]


class BackupBundle(BaseModel):
    format: Literal["gpt-auto-register-backup"]
    version: Literal[1]
    exported_at: datetime
    sections: dict[str, list[dict[str, Any]]]


class BackupPreviewRequest(BaseModel):
    bundle: BackupBundle
    sections: list[BackupSection]
    mode: Literal["merge", "overwrite"] = "merge"


class BackupSectionPreview(BaseModel):
    incoming: int
    added: int
    updated: int
    unchanged: int
    removable: int = 0
    protected: int = 0


class BackupPreviewResponse(BaseModel):
    sections: dict[str, BackupSectionPreview]


class BackupImportRequest(BackupPreviewRequest):
    conflict_policy: Literal["incoming", "local"] = "incoming"


class BackupImportResponse(BaseModel):
    added: int
    updated: int
    unchanged: int
    removed: int
    protected: int
