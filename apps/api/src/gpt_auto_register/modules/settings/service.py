from typing import Any

from sqlalchemy.orm import Session

from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.settings.schemas import (
    ExportSettings,
    ExportSettingsUpdate,
    ExportTargetSettings,
    KakaoSettings,
    MailSettings,
    MailSettingsUpdate,
    RegistrationSettings,
    SmsSettings,
    SmsSettingsUpdate,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)


class SettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> SystemSettingsResponse:
        registration = RegistrationSettings.model_validate(
            self._value("registration", RegistrationSettings().model_dump())
        )
        registration = registration.model_copy(
            update={
                "want_access_token": True,
                "want_session_token": True,
                "want_refresh_token": True,
            }
        )
        kakao = KakaoSettings.model_validate(self._value("kakao", KakaoSettings().model_dump()))
        mail_value = self._value("mail", {})
        mail = MailSettings(
            **{key: value for key, value in mail_value.items() if key != "cf_admin_token"},
            cf_admin_token_configured=bool(mail_value.get("cf_admin_token")),
        )
        sms_value = self._value("sms", {})
        export_value = self._value("export", {})
        sms = SmsSettings(
            **{key: value for key, value in sms_value.items() if key != "api_key"},
            api_key_configured=bool(sms_value.get("api_key")),
        )
        export = ExportSettings(
            cpa=self._export_view(export_value.get("cpa", {})),
            sub2api=self._export_view(export_value.get("sub2api", {})),
            sub2api_group_ids=str(export_value.get("sub2api_group_ids", "")),
        )
        return SystemSettingsResponse(
            registration=registration,
            mail=mail,
            kakao=kakao,
            sms=sms,
            export=export,
        )

    def update(self, values: SystemSettingsUpdate) -> SystemSettingsResponse:
        current_sms = self._value("sms", {})
        current_mail = self._value("mail", {})
        current_export = self._value("export", {})
        registration = values.registration.model_dump()
        registration.update(
            want_access_token=True,
            want_session_token=True,
            want_refresh_token=True,
        )
        self._set("registration", registration)
        self._set("mail", self._merge_mail(values.mail, current_mail), sensitive=True)
        self._set("kakao", values.kakao.model_dump())
        self._set("sms", self._merge_sms(values.sms, current_sms), sensitive=True)
        self._set("export", self._merge_export(values.export, current_export), sensitive=True)
        self.session.commit()
        return self.get()

    def kakao_internal(self) -> KakaoSettings:
        return KakaoSettings.model_validate(self._value("kakao", KakaoSettings().model_dump()))

    def registration_internal(self) -> RegistrationSettings:
        return self.get().registration

    def sms_internal(self) -> dict[str, Any]:
        return SmsSettingsUpdate.model_validate(self._value("sms", {})).model_dump()

    def mail_internal(self) -> dict[str, Any]:
        return MailSettingsUpdate.model_validate(self._value("mail", {})).model_dump()

    def export_internal(self) -> dict[str, Any]:
        return ExportSettingsUpdate.model_validate(self._value("export", {})).model_dump()

    def _value(self, key: str, default: dict[str, Any]) -> dict[str, Any]:
        row = self.session.get(AppSetting, key)
        return dict(row.value) if row and isinstance(row.value, dict) else default

    def _set(self, key: str, value: dict[str, Any], *, sensitive: bool = False) -> None:
        row = self.session.get(AppSetting, key)
        if row is None:
            self.session.add(AppSetting(key=key, value=value, sensitive=sensitive))
        else:
            row.value = value
            row.sensitive = sensitive

    @staticmethod
    def _merge_sms(update: SmsSettingsUpdate, current: dict[str, Any]) -> dict[str, Any]:
        value = update.model_dump(exclude={"api_key"})
        value["api_key"] = update.api_key.strip() or current.get("api_key", "")
        return value

    @staticmethod
    def _merge_mail(update: MailSettingsUpdate, current: dict[str, Any]) -> dict[str, Any]:
        value = update.model_dump(exclude={"cf_admin_token"})
        value["cf_admin_token"] = update.cf_admin_token.strip() or current.get("cf_admin_token", "")
        return value

    @staticmethod
    def _merge_export(update: ExportSettingsUpdate, current: dict[str, Any]) -> dict[str, Any]:
        value: dict[str, Any] = {"sub2api_group_ids": update.sub2api_group_ids}
        for name in ("cpa", "sub2api"):
            target = getattr(update, name)
            old_target = current.get(name, {})
            target_value = target.model_dump(exclude={"key"})
            target_value["key"] = target.key.strip() or old_target.get("key", "")
            value[name] = target_value
        return value

    @staticmethod
    def _export_view(value: dict[str, Any]) -> ExportTargetSettings:
        return ExportTargetSettings(
            **{key: item for key, item in value.items() if key != "key"},
            key_configured=bool(value.get("key")),
        )
