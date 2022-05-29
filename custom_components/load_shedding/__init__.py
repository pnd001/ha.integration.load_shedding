"""The LoadShedding component."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict, List

from load_shedding import ScheduleError, Stage, get_schedule
from load_shedding.providers import ProviderError, Suburb

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ATTR_STAGE, ATTR_SUBURBS, DEFAULT_SCAN_INTERVAL, DOMAIN, PROVIDER

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: Config):
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LoadShedding as config entry."""

    suburb = Suburb(
        id=entry.data.get("suburb_id"),
        name=entry.data.get("suburb"),
        municipality=entry.data.get("municipality"),
        province=entry.data.get("province"),
    )

    coordinator = LoadSheddingDataUpdateCoordinator(hass)
    coordinator.add_suburb(suburb)

    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(update_listener))

    async def _schedule_updates(*_):
        """Activate the data update coordinator."""
        coordinator.update_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        await coordinator.async_refresh()

    if hass.state == CoreState.running:
        await _schedule_updates()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _schedule_updates)

    hass.data[DOMAIN] = coordinator

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Load Shedding Entry from config_entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


class LoadSheddingDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching LoadShedding data API."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.provider = PROVIDER()
        self.suburbs: list[Suburb] = []
        super().__init__(
            self.hass, _LOGGER, name=DOMAIN, update_method=self.async_update
        )

    def add_suburb(self, suburb: Suburb = None) -> None:
        """Add a suburb to update."""
        self.suburbs.append(suburb)

    async def async_update(self):
        """Retrieve latest state."""
        try:
            stage = await self.hass.async_add_executor_job(self.provider.get_stage)
        except (ProviderError, ScheduleError) as e:
            return {**{ATTR_STAGE: str(Stage.UNKNOWN)}}

        suburbs = {}
        if stage in [Stage.UNKNOWN, Stage.NO_LOAD_SHEDDING]:
            return {**{ATTR_STAGE: str(stage), ATTR_SUBURBS: suburbs}}

        for suburb in self.suburbs:
            try:
                schedule = await self.hass.async_add_executor_job(
                    get_schedule,
                    self.provider,
                    suburb.province,
                    suburb,
                    stage,
                )
            except (ProviderError, ScheduleError) as e:
                _LOGGER.error(f"{e}")
                suburbs[suburb.id] = {}
            else:
                suburbs[suburb.id] = schedule

        return {**{ATTR_STAGE: str(stage), ATTR_SUBURBS: suburbs}}