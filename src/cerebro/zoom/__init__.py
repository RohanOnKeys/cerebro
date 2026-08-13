"""Zoom auth and REST v2 client (Server-to-Server OAuth, one shared account)."""

from cerebro.zoom.api import ZoomAPI, ZoomAPIError
from cerebro.zoom.auth import ZoomAuth, ZoomAuthError

__all__ = ["ZoomAPI", "ZoomAPIError", "ZoomAuth", "ZoomAuthError"]
