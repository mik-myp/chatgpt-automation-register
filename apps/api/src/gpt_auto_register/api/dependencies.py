from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.session import SessionLocal, get_db

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return getattr(request.app.state, "session_factory", SessionLocal)


DatabaseSessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
