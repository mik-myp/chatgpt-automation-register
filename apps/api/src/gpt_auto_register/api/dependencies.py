from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from gpt_auto_register.db.session import get_db

DatabaseSession = Annotated[Session, Depends(get_db)]
