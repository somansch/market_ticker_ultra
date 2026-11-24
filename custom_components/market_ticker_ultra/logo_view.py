"""The logos users upload for their instruments, served to who is signed in.

Not a static path: those skip authentication, and an uploaded file is not
for everybody who can reach the instance. A request needs a token - or the
signature Home Assistant puts on the address the card is given.
"""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .logos import OWN_LOGO_TYPES, OWN_LOGO_URL_BASE, own_logo_dir

# An uploaded image is somebody's file: shown as a picture, never run. An
# SVG opened by its address would otherwise be a document of this origin.
_HEADERS = {
    "Cache-Control": "private, max-age=86400",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


class OwnLogoView(HomeAssistantView):
    """One uploaded logo, by its file name."""

    url = OWN_LOGO_URL_BASE + "/{file_name}"
    name = "api:market_ticker_ultra:logo"
    requires_auth = True

    async def get(self, request: web.Request, file_name: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        # A name and nothing else: no folder, no way out of the logos' own.
        name = Path(file_name).name
        if name != file_name or Path(name).suffix.lower() not in OWN_LOGO_TYPES:
            raise web.HTTPNotFound
        path = own_logo_dir(hass.config.config_dir) / name
        if not await hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path, headers=_HEADERS)
