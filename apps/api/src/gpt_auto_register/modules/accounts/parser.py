import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from gpt_auto_register.db.models.accounts import MailType

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class ParsedAccount:
    email: str
    password: str | None
    client_id: str | None
    refresh_token: str | None
    mail_type: MailType
    mail_url: str | None


@dataclass(frozen=True, slots=True)
class ParseResult:
    accounts: list[ParsedAccount]
    invalid_lines: list[int]


def _valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(value))


def _valid_mail_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_account_line(line: str) -> ParsedAccount | None:
    if "----" in line:
        parts = [part.strip() for part in line.split("----")]
    elif "---" in line:
        parts = [part.strip() for part in line.split("---", 1)]
    else:
        return None

    if len(parts) == 4:
        email, password, client_id, refresh_token = parts
        if not all(parts) or not _valid_email(email):
            return None
        return ParsedAccount(
            email=email.lower(),
            password=password,
            client_id=client_id,
            refresh_token=refresh_token,
            mail_type=MailType.OUTLOOK,
            mail_url=None,
        )

    if len(parts) == 2:
        email, mail_url = parts
        if not _valid_email(email) or not _valid_mail_url(mail_url):
            return None
        return ParsedAccount(
            email=email.lower(),
            password=None,
            client_id=None,
            refresh_token=None,
            mail_type=MailType.LINK,
            mail_url=mail_url,
        )

    return None


def parse_accounts(text: str) -> ParseResult:
    accounts_by_email: dict[str, ParsedAccount] = {}
    invalid_lines: list[int] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        account = parse_account_line(line)
        if account is None:
            invalid_lines.append(line_number)
            continue
        accounts_by_email[account.email] = account

    return ParseResult(accounts=list(accounts_by_email.values()), invalid_lines=invalid_lines)
