from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.db.models.accounts import Credential
from gpt_auto_register.db.result import affected_rows


class ResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, email: str) -> Credential | None:
        return self.session.get(Credential, email.lower())

    def list_page(
        self,
        *,
        search: str,
        token_filter: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Credential], int]:
        filters: list[ColumnElement[bool]] = []
        if search:
            filters.append(func.lower(Credential.email).like(f"%{search.lower()}%"))
        token_columns = {
            "access": Credential.access_token,
            "session": Credential.session_token,
            "refresh": Credential.refresh_token,
        }
        if token_filter in token_columns:
            column = token_columns[token_filter]
            filters.append(column.is_not(None))
        plus_state = Credential.metadata_json["plus_check"]["state"].as_string()
        if token_filter == "plus":
            filters.append(plus_state == "plus")
        elif token_filter == "not_plus":
            filters.append(plus_state.in_(["free", "not_plus", "other_plan", "deactivated"]))
        elif token_filter == "plus_unknown":
            filters.append(
                or_(
                    plus_state.is_(None),
                    plus_state.notin_(["plus", "free", "not_plus", "other_plan", "deactivated"]),
                )
            )
        total = (
            self.session.scalar(select(func.count()).select_from(Credential).where(*filters)) or 0
        )
        items = list(
            self.session.scalars(
                select(Credential)
                .where(*filters)
                .order_by(Credential.created_at.desc(), Credential.email)
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def export(self, emails: list[str], all_results: bool) -> list[Credential]:
        query = select(Credential).order_by(Credential.created_at.desc())
        if not all_results:
            query = query.where(Credential.email.in_(emails))
        return list(self.session.scalars(query))

    def delete(self, emails: list[str], all_results: bool) -> int:
        statement = delete(Credential)
        if not all_results:
            statement = statement.where(Credential.email.in_(emails))
        result = self.session.execute(statement)
        return affected_rows(result)
