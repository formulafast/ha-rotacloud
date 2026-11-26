"""Real HA resource collections: persistence, idempotence and ownership."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceYAMLCollection
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component

from custom_components.rotacloud_attendance.const import DOMAIN, VERSION
from custom_components.rotacloud_attendance.resources import RESOURCE_PATHS, async_register_resources


async def test_persisted_resources_are_loaded_and_only_own_paths_are_updated(hass):
    assert await async_setup_component(hass, 'lovelace', {})
    collection = hass.data[LOVELACE_DATA].resources
    assert not collection.loaded
    saved = [
        {'id':'other','url':'/local/another-card.js?v=1','type':'module'},
        {'id':'remote','url':'https://example.org'+RESOURCE_PATHS[0],'type':'module'},
        {'id':'live','url':RESOURCE_PATHS[0]+'?v=0.6.0','type':'js'},
        {'id':'duplicate','url':RESOURCE_PATHS[0]+'?v=old','type':'module'},
    ]
    await Store(hass, 1, 'lovelace_resources').async_save({'items':saved})
    await async_register_resources(hass)
    items = collection.async_items()
    assert len(items) == 4
    assert saved[0] in items and saved[1] in items
    assert next(x for x in items if x['id']=='live') == {'id':'live','url':RESOURCE_PATHS[0]+'?v='+VERSION,'type':'module'}
    assert not any(x['id']=='duplicate' for x in items)
    with patch.object(collection, 'async_create_item', wraps=collection.async_create_item) as create, patch.object(collection,'async_update_item', wraps=collection.async_update_item) as update, patch.object(collection,'async_delete_item',wraps=collection.async_delete_item) as delete:
        await async_register_resources(hass)
        create.assert_not_called(); update.assert_not_called(); delete.assert_not_called()


async def test_concurrent_setup_adds_one_resource_per_file(hass):
    assert await async_setup_component(hass, 'lovelace', {})
    await asyncio.gather(async_register_resources(hass), async_register_resources(hass))
    items=hass.data[LOVELACE_DATA].resources.async_items()
    assert sorted(x['url'] for x in items) == sorted(path+'?v='+VERSION for path in RESOURCE_PATHS)


async def test_yaml_resources_are_never_written_and_repair_clears_when_correct(hass):
    original=[{'url':'/local/other.js','type':'module'}]
    collection=ResourceYAMLCollection(original.copy())
    hass.data[LOVELACE_DATA]=SimpleNamespace(resource_mode='yaml',resources=collection)
    await async_register_resources(hass)
    assert collection.async_items()==original
    registry=ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN,'frontend_resources').translation_key=='yaml_resources'
    collection.data += [{'url':path+'?v='+VERSION,'type':'module'} for path in RESOURCE_PATHS]
    await async_register_resources(hass)
    assert registry.async_get_issue(DOMAIN,'frontend_resources') is None


async def test_registration_failure_creates_repair_and_retry_recovers(hass):
    assert await async_setup_component(hass, 'lovelace', {})
    collection=hass.data[LOVELACE_DATA].resources
    with patch.object(collection,'async_create_item',new=AsyncMock(side_effect=HomeAssistantError)):
        await async_register_resources(hass)
    registry=ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN,'frontend_resources') is not None
    await async_register_resources(hass)
    assert len(collection.async_items())==2
    assert registry.async_get_issue(DOMAIN,'frontend_resources') is None
