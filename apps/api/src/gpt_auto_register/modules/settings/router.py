from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.models.kakao import KakaoCard
from gpt_auto_register.modules.kakao.client import KakaoApiError, KakaoClient
from gpt_auto_register.modules.settings.schemas import (
    ConnectionTestResponse,
    SmsCountry,
    SmsCountryListResponse,
    SmsTestResponse,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.manager import _legacy_call

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SystemSettingsResponse)
def get_settings(db: DatabaseSession) -> SystemSettingsResponse:
    return SettingsService(db).get()


@router.put("", response_model=SystemSettingsResponse)
def update_settings(request: SystemSettingsUpdate, db: DatabaseSession) -> SystemSettingsResponse:
    return SettingsService(db).update(request)


@router.post("/sms/test", response_model=SmsTestResponse)
def test_sms_settings(db: DatabaseSession) -> SmsTestResponse:
    sms = SettingsService(db).sms_internal()
    if not sms.get("api_key"):
        raise HTTPException(status.HTTP_409_CONFLICT, "请先配置 SMS API Key")
    result = _legacy_call({"action": "sms_test", "sms": sms}, timeout=60)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(result.get("error")))
    return SmsTestResponse(balance=float(result.get("balance") or 0))


@router.get("/sms/countries", response_model=SmsCountryListResponse)
def list_sms_countries(db: DatabaseSession) -> SmsCountryListResponse:
    result = _legacy_call(
        {"action": "sms_countries", "sms": SettingsService(db).sms_internal()},
        timeout=60,
    )
    if not result.get("ok"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(result.get("error")))
    return SmsCountryListResponse(
        items=[SmsCountry.model_validate(value) for value in result.get("items", [])],
        live=bool(result.get("live")),
    )


@router.post("/mail/test", response_model=ConnectionTestResponse)
def test_mail_settings(db: DatabaseSession) -> ConnectionTestResponse:
    mail = SettingsService(db).mail_internal()
    if mail.get("source") != "cf_temp":
        return ConnectionTestResponse(message="当前使用 Outlook 号池，无需连接测试")
    if not all(mail.get(key) for key in ("cf_api_url", "cf_domain", "cf_admin_token")):
        raise HTTPException(status.HTTP_409_CONFLICT, "请先完整配置 CF 邮箱地址、域名和管理密钥")
    result = _legacy_call({"action": "mail_test", "mail": mail}, timeout=60)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(result.get("error")))
    return ConnectionTestResponse(message=f"连接成功，测试邮箱：{result.get('email', '')}")


@router.post("/export/{target}/test", response_model=ConnectionTestResponse)
def test_export_settings(target: str, db: DatabaseSession) -> ConnectionTestResponse:
    if target not in {"cpa", "sub2api"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "不支持的导出目标")
    export = SettingsService(db).export_internal()
    value = export.get(target, {})
    if not value.get("url") or not value.get("key"):
        raise HTTPException(status.HTTP_409_CONFLICT, "请先保存 URL 和密钥")
    result = _legacy_call(
        {"action": "export_test", "target": target, "export": export},
        timeout=60,
    )
    if not result.get("ok"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(result.get("error")))
    return ConnectionTestResponse(message=f"{target.upper()} 连接成功")


@router.post("/kakao/test", response_model=ConnectionTestResponse)
def test_kakao_settings(db: DatabaseSession) -> ConnectionTestResponse:
    settings = SettingsService(db).kakao_internal()
    card = db.scalar(
        select(KakaoCard).where(KakaoCard.active.is_(True)).order_by(KakaoCard.created_at)
    )
    if not settings.base_url:
        raise HTTPException(status.HTTP_409_CONFLICT, "请先配置 Kakao Base URL")
    if card is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "请先导入并启用至少一个卡密")
    try:
        KakaoClient(settings.base_url, settings.timeout).list_tasks(
            card.code,
            page=1,
            page_size=1,
        )
    except (KakaoApiError, ValueError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return ConnectionTestResponse(message="Kakao 连接成功，卡密可用于查询任务")
