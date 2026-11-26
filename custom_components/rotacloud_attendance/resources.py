"""Register only this integration's two dashboard modules on setup/reload."""
import asyncio
import logging
from urllib.parse import urlsplit

from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)
RESOURCE_PATHS = (
    "/rotacloud_attendance/static/staff-live.js",
    "/rotacloud_attendance/static/staff-terminal.js",
)


def _owned_path(url):
    """Never adopt another host's resource, even with the same path."""
    try:
        parsed = urlsplit(url)
    except (ValueError, TypeError):
        return None
    return parsed.path if not parsed.scheme and not parsed.netloc and parsed.path in RESOURCE_PATHS else None


def _issue(hass, key):
    ir.async_create_issue(hass, DOMAIN, "frontend_resources", is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=key,
                          translation_placeholders={"version": VERSION})


async def async_register_resources(hass):
    lock = hass.data.setdefault(DOMAIN + "_resource_lock", asyncio.Lock())
    async with lock:
        try:
            lovelace = hass.data[LOVELACE_DATA]
            collection = lovelace.resources
            # Load persisted resources BEFORE inspecting or mutating the collection.
            await collection.async_get_info()
            items = list(collection.async_items())
            if lovelace.resource_mode == "yaml":
                correct = all(any(item.get("url") == path + "?v=" + VERSION
                                  and item.get("type") == "module" for item in items)
                              for path in RESOURCE_PATHS)
                if correct:
                    ir.async_delete_issue(hass, DOMAIN, "frontend_resources")
                else:
                    _issue(hass, "yaml_resources")
                return
            for path in RESOURCE_PATHS:
                owned = [item for item in items if _owned_path(item.get("url")) == path]
                url = path + "?v=" + VERSION
                if owned:
                    first = owned[0]
                    if first.get("url") != url or first.get("type") != "module":
                        await collection.async_update_item(first["id"], {"url": url, "res_type": "module"})
                    # Remove duplicates of OUR exact resource path only.
                    for duplicate in owned[1:]:
                        await collection.async_delete_item(duplicate["id"])
                else:
                    await collection.async_create_item({"url": url, "res_type": "module"})
            ir.async_delete_issue(hass, DOMAIN, "frontend_resources")
        except (HomeAssistantError, OSError, KeyError, ValueError):
            _LOGGER.warning("Dashboard resources could not be registered; see Repairs for manual setup")
            _issue(hass, "frontend_resources")
