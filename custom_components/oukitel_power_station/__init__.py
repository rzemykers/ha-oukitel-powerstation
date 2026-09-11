"""The Oukitel Power Station integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import OukitelCloud, OukitelCloudAuthError, OukitelCloudError
from .const import (
    CONF_EMAIL,
    CONF_ENABLE_CONTROL,
    CONF_MANIFEST,
    CONF_PASSWORD,
    CONF_PK,
    CONF_REGION,
)
from .coordinator import OukitelCoordinator
from .product import ProductManifest, build_manifest, resolve_manifest

_LOGGER = logging.getLogger(__name__)

# SWITCH/SELECT/NUMBER are forwarded unconditionally; each platform checks the
# `enable_control` option itself, keeping forward/unload symmetric across an
# options change.
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

type OukitelConfigEntry = ConfigEntry[OukitelCoordinator]


async def _async_resolve_manifest(hass: HomeAssistant, entry: ConfigEntry) -> ProductManifest:
    """Resolve a product manifest, fetching and persisting an unknown TSL."""
    pk = str(entry.data.get(CONF_PK) or "")
    snapshot = entry.data.get(CONF_MANIFEST)
    manifest = await hass.async_add_executor_job(resolve_manifest, pk, snapshot, None)
    if manifest is not None:
        return manifest

    data = entry.data
    cloud = OukitelCloud(async_get_clientsession(hass), data[CONF_REGION])
    try:
        await cloud.login(data[CONF_EMAIL], data[CONF_PASSWORD])
        tsl = await cloud.get_tsl(pk)
    except OukitelCloudAuthError as err:
        raise ConfigEntryAuthFailed(f"cloud credentials rejected: {err}") from err
    except OukitelCloudError as err:
        raise ConfigEntryNotReady(f"cannot fetch product TSL for {pk}: {err}") from err
    if not tsl:
        raise ConfigEntryNotReady(f"product TSL for {pk} is empty")

    vendor_manifest = build_manifest(tsl)
    if not vendor_manifest.tags:
        raise ConfigEntryNotReady(f"product TSL for {pk} has no properties")
    snapshot = vendor_manifest.to_dict()
    hass.config_entries.async_update_entry(entry, data={**data, CONF_MANIFEST: snapshot})
    manifest = resolve_manifest(pk, snapshot)
    if manifest is None:  # pragma: no cover - build_manifest produced the snapshot
        raise ConfigEntryNotReady(f"cannot build product manifest for {pk}")
    return manifest


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve control entities for entries created before the opt-in option."""
    if entry.version < 2:
        options = dict(entry.options)
        options.setdefault(CONF_ENABLE_CONTROL, True)
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OukitelConfigEntry) -> bool:
    """Set up Oukitel Power Station from a config entry."""
    manifest = await _async_resolve_manifest(hass, entry)
    coordinator = OukitelCoordinator(hass, entry, manifest)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OukitelConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_reload_on_update(hass: HomeAssistant, entry: OukitelConfigEntry) -> None:
    """Reload when options change.

    Data-only updates (authKey, host) are consumed in-place: the coordinator
    reads ``entry.data`` on every connect, so tearing the session down would
    only reset the one-refresh-per-outage guard and loop the key rewrite.
    """
    coordinator = entry.runtime_data
    if dict(entry.options) == coordinator.options:
        return
    await hass.config_entries.async_reload(entry.entry_id)
