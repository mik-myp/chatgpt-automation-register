from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RegistrationSettings(BaseModel):
    concurrency: int = Field(default=10, ge=1, le=50)
    otp_timeout: int = Field(default=60, ge=1, le=300)
    allow_existing_login: bool = True
    password_mode: Literal["none", "random", "fixed"] = "random"
    fixed_password: str = Field(default="", max_length=256)
    enable_authenticator_mfa: bool = False
    mfa_otp_timeout: int = Field(default=180, ge=30, le=600)
    want_access_token: bool = True
    want_session_token: bool = True
    want_refresh_token: bool = True

    @model_validator(mode="after")
    def validate_fixed_password(self) -> "RegistrationSettings":
        if self.password_mode == "fixed" and not self.fixed_password:
            raise ValueError("固定密码模式必须填写密码")
        return self


class KakaoSettings(BaseModel):
    # Kept for reading historical settings; local extraction does not use the old service.
    base_url: str = ""
    timeout: int = Field(default=30, ge=5, le=300)
    poll_timeout: int = Field(default=120, ge=30, le=300)
    verify_proxy_countries: bool = True
    card_usage_limit: int = Field(default=10, ge=1, le=1000)
    plan_type: Literal["plus"] = "plus"
    promo_code: str = "plus-1-month-free"


PipelineStep = Literal["registration", "account_security", "kakao"]


def default_pipeline_order() -> list[PipelineStep]:
    return ["registration", "account_security", "kakao"]


class ProxySettings(BaseModel):
    api_url: str = ""
    max_attempts_per_account: int = Field(default=3, ge=1, le=10)
    request_timeout: int = Field(default=30, ge=5, le=120)


class PipelineSettings(BaseModel):
    step_order: list[PipelineStep] = Field(
        default_factory=default_pipeline_order
    )
    registration_task_concurrency: int = Field(default=1, ge=1, le=20)
    account_security_task_concurrency: int = Field(default=1, ge=1, le=20)
    kakao_task_concurrency: int = Field(default=1, ge=1, le=20)
    account_security_email_concurrency: int = Field(default=10, ge=1, le=50)
    kakao_email_concurrency: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_step_order(self) -> "PipelineSettings":
        expected = {"registration", "account_security", "kakao"}
        if len(self.step_order) != 3 or set(self.step_order) != expected:
            raise ValueError("流水线步骤顺序必须且只能包含注册、设置密码与 MFA、Kakao")
        return self


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


DeliveryCopyField = Literal[
    "payment_url",
    "email",
    "mail_url",
    "chatgpt_password",
    "totp_secret",
]
DeliveryCopyType = Literal["payment_links", "account_info"]


class DeliveryCopyRow(BaseModel):
    fields: list[DeliveryCopyField] = Field(min_length=1)
    separator: str = Field(default=" --- ", max_length=32)


class DeliveryFormatSettings(BaseModel):
    sequence_style: Literal["none", "number", "chinese_number", "chinese"] = "chinese"
    record_separator: Literal["newline", "blank_line"] = "blank_line"
    show_labels: bool = False
    missing_policy: Literal["placeholder", "skip"] = "placeholder"
    placeholder: str = Field(default="-", max_length=16)
    rows: list[DeliveryCopyRow] = Field(
        default_factory=lambda: [DeliveryCopyRow(fields=["email"])],
        min_length=1,
        max_length=10,
    )


class DeliveryCopySettings(BaseModel):
    only_copy_plus: bool = False
    payment_links: DeliveryFormatSettings = Field(
        default_factory=lambda: DeliveryFormatSettings(
            rows=[DeliveryCopyRow(fields=["payment_url"], separator="")]
        )
    )
    mail_access: DeliveryFormatSettings = Field(
        default_factory=lambda: DeliveryFormatSettings(
            sequence_style="none",
            missing_policy="skip",
            rows=[DeliveryCopyRow(fields=["email", "mail_url"])],
        )
    )
    security_credentials: DeliveryFormatSettings = Field(
        default_factory=lambda: DeliveryFormatSettings(
            sequence_style="none",
            missing_policy="skip",
            rows=[DeliveryCopyRow(fields=["email", "chatgpt_password", "totp_secret"])],
        )
    )

    @model_validator(mode="after")
    def validate_copy_fields(self) -> "DeliveryCopySettings":
        payment_fields = {field for row in self.payment_links.rows for field in row.fields}
        mail_fields = {field for row in self.mail_access.rows for field in row.fields}
        security_fields = {field for row in self.security_credentials.rows for field in row.fields}
        if payment_fields != {"payment_url"}:
            raise ValueError("支付链接配置只能包含支付链接字段")
        if mail_fields != {"email", "mail_url"}:
            raise ValueError("邮箱访问格式必须包含邮箱和邮件查询地址")
        if security_fields != {"email", "chatgpt_password", "totp_secret"}:
            raise ValueError("安全凭证格式必须包含邮箱、ChatGPT 密码和 Authenticator 密钥")
        return self


class MaintenanceSettings(BaseModel):
    job_log_retention_days: int = Field(default=14, ge=1, le=365)
    max_runtime_log_lines: int = Field(default=2000, ge=100, le=20000)


class SystemSettingsResponse(BaseModel):
    registration: RegistrationSettings
    proxy: ProxySettings
    pipeline: PipelineSettings
    mail: MailSettings
    kakao: KakaoSettings
    sms: SmsSettings
    export: ExportSettings
    delivery_copy: DeliveryCopySettings
    maintenance: MaintenanceSettings


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
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    mail: MailSettingsUpdate
    kakao: KakaoSettings
    sms: SmsSettingsUpdate
    export: ExportSettingsUpdate
    delivery_copy: DeliveryCopySettings
    maintenance: MaintenanceSettings = Field(default_factory=MaintenanceSettings)


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


class BackupScope(BaseModel):
    included: list[BackupSection]
    excluded: list[str]
    description: str


class BackupBundle(BaseModel):
    format: Literal["gpt-auto-register-backup"]
    version: Literal[3]
    exported_at: datetime
    scope: BackupScope
    sections: dict[str, list[dict[str, Any]]]
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


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
    recovery_snapshot: str | None = None


class StorageStatsResponse(BaseModel):
    database_bytes: int
    job_events: int
    expired_job_events: int
    backup_files: int
    backup_bytes: int


class StorageCleanupResponse(BaseModel):
    removed_job_events: int
    removed_backup_files: int
