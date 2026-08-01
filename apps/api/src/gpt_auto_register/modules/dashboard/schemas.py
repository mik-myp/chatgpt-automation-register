from pydantic import BaseModel

from gpt_auto_register.modules.accounts.schemas import AccountStats
from gpt_auto_register.modules.cards.schemas import CardInventoryStats


class DashboardPipelineStats(BaseModel):
    total: int
    active: int
    completed: int
    failed: int


class DashboardJobStats(BaseModel):
    queued: int
    running: int
    failed: int


class DashboardResponse(BaseModel):
    accounts: AccountStats
    cards: CardInventoryStats
    pipelines: DashboardPipelineStats
    jobs: DashboardJobStats
    registration_results: int
