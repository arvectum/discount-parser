"""ASGI entry point for Discount Parser."""

from src.app import create_app

app = create_app()

__all__ = ["app", "create_app"]
