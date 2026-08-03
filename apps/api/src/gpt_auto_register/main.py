from gpt_auto_register.bootstrap.application import create_app

app = create_app()

__all__ = ["app", "create_app"]
