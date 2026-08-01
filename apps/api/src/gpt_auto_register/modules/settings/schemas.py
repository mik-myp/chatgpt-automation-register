from typing import Literal

from pydantic import BaseModel, Field


class RegistrationSettings(BaseModel):
    concurrency: int = Field(default=10, ge=1, le=50)
    otp_timeout: int = Field(default=10, ge=1, le=300)
    allow_existing_login: bool = True
    want_access_token: bool = True
    want_session_token: bool = True
    want_refresh_token: bool = True
    proxy: str = ""
    proxy_pool: str = ""


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
    mail: MailSettingsUpdate = Field(default_factory=MailSettingsUpdate)
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
