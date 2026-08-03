from fastapi import APIRouter, Depends

from gpt_auto_register.api.auth_dependencies import require_authenticated, require_csrf
from gpt_auto_register.api.routes.health import router as health_router
from gpt_auto_register.modules.accounts.router import router as accounts_router
from gpt_auto_register.modules.auth.router import router as auth_router
from gpt_auto_register.modules.cards.router import router as cards_router
from gpt_auto_register.modules.dashboard.router import router as dashboard_router
from gpt_auto_register.modules.kakao.router import router as kakao_router
from gpt_auto_register.modules.pipelines.router import router as pipelines_router
from gpt_auto_register.modules.results.operation_router import router as result_operations_router
from gpt_auto_register.modules.results.router import router as results_router
from gpt_auto_register.modules.settings.router import router as settings_router
from gpt_auto_register.modules.setup.router import router as setup_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(setup_router)
api_router.include_router(auth_router)

protected_router = APIRouter(dependencies=[Depends(require_authenticated), Depends(require_csrf)])
protected_router.include_router(accounts_router)
protected_router.include_router(cards_router)
protected_router.include_router(dashboard_router)
protected_router.include_router(pipelines_router)
protected_router.include_router(kakao_router)
protected_router.include_router(result_operations_router)
protected_router.include_router(results_router)
protected_router.include_router(settings_router)
api_router.include_router(protected_router)
