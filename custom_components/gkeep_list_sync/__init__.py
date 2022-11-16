"""The Google Keep List Sync integration."""
from __future__ import annotations

import logging

from gkeepapi import Keep
from gkeepapi.exception import LoginException, APIException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, InvalidStateError
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_USERNAME

from .const import (
    DOMAIN,
    CONF_LIST_ID,
    SHOPPING_LIST_DOMAIN,
    MISSING_LIST,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up of Google Keep List component."""

    # Check for dependencies
    if not hass.data.get(SHOPPING_LIST_DOMAIN):
        _LOGGER.error(
            "Shopping list integration is missing, please add it to Home Assistant and reload",
        )
        return False

    # Get instance of Google Keep and list
    try:
        keep = Keep()
        await hass.async_add_executor_job(
            keep.resume,
            config_entry.data.get(CONF_USERNAME),
            config_entry.data.get(CONF_ACCESS_TOKEN),
        )
    except LoginException as ex:
        raise ConfigEntryAuthFailed from ex
    except APIException as ex:
        _LOGGER.error(
            "Unable to communicate with Google Keep API (error code %s): %s",
            ex.code,
            ex,
        )
        return False

    if not keep.get(config_entry.data.get(CONF_LIST_ID)):
        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, MISSING_LIST: True},
        )
        raise ConfigEntryAuthFailed("List couldn't be found, please reauthenticate")

    async def handle_sync_list(call) -> None:  # pylint: disable=unused-argument
        """Handle synchronizing the Google Keep list with Shopping list"""

        # Sync to get any new items
        await hass.async_add_executor_job(keep.sync)

        if not (glist := keep.get(config_entry.data.get(CONF_LIST_ID))):
            raise InvalidStateError("List couldn't be found, please reauthenticate")

        _LOGGER.debug("service: %s", glist)

        # Add items to HA and delete from Google Keep
        for item in glist.unchecked:
            _LOGGER.debug("syncing item: %s", item.text)
            await hass.services.async_call(
                "shopping_list",
                "add_item",
                {"name": item.text},
                True,
            )
            await hass.async_add_executor_job(item.delete)

        # Sync again to delete already added items
        await hass.async_add_executor_job(keep.sync)

    hass.services.async_register(DOMAIN, "sync_list", handle_sync_list)

    return True