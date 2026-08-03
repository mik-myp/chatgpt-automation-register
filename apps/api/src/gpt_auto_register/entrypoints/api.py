import uvicorn

from gpt_auto_register.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "gpt_auto_register.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
