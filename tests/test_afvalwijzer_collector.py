"""Tests for the Afvalwijzer collector: streams the API files under another stream's type."""
from datetime import date, timedelta

from custom_components.afvalbeheer.API import get_wastedata_from_config
from custom_components.afvalbeheer.collectors.individual import afvalwijzer as afvalwijzer_module
from custom_components.afvalbeheer.const import (
    CONF_CUSTOM_MAPPING,
    CONF_CUSTOMER_ID,
    CONF_POSTCODE,
    CONF_PRINT_AVAILABLE_WASTE_TYPES,
    CONF_PRINT_AVAILABLE_WASTE_TYPE_SLUGS,
    CONF_RESOURCES,
    CONF_STREET_NUMBER,
    CONF_UPDATE_INTERVAL,
    CONF_WASTE_COLLECTOR,
    WASTE_TYPE_GREEN,
    WASTE_TYPE_PAPER,
)


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


class _Response:
    def __init__(self, items):
        self._items = items

    def json(self):
        return {'ophaaldagen': {'data': self._items}}


def _meppel_items():
    """What the API returns for an address in Meppel: VET-goed is sent as type keukenafval."""
    return [
        {'nameType': 'vet-goed', 'type': 'keukenafval', 'date': _day(1)},
        {'nameType': 'gft-e', 'type': 'gft', 'date': _day(7)},
        {'nameType': 'papier', 'type': 'papier', 'date': _day(16)},
    ]


def _config(custom_mapping=None):
    return {
        CONF_WASTE_COLLECTOR: 'mijnafvalwijzer',
        CONF_POSTCODE: '7948AW',
        CONF_STREET_NUMBER: '2',
        CONF_RESOURCES: ['gft', 'papier', 'vet-goed'],
        CONF_CUSTOM_MAPPING: custom_mapping or {},
        CONF_PRINT_AVAILABLE_WASTE_TYPES: False,
        CONF_PRINT_AVAILABLE_WASTE_TYPE_SLUGS: False,
        CONF_UPDATE_INTERVAL: 0,
        CONF_CUSTOMER_ID: '',
    }


async def _update(hass, monkeypatch, items, custom_mapping=None):
    monkeypatch.setattr(afvalwijzer_module.requests, 'get', lambda url, **kwargs: _Response(items))
    collector = get_wastedata_from_config(hass, _config(custom_mapping)).collector
    await collector.update()
    return collector


def _by_type(collector):
    found = {}
    for collection in collector.collections:
        found.setdefault(collection.waste_type, []).append((collection.date.date().isoformat(), collection.waste_type_slug))
    return {waste_type: sorted(dates) for waste_type, dates in found.items()}


async def test_vet_goed_is_not_shown_as_gft(hass, monkeypatch):
    collector = await _update(hass, monkeypatch, _meppel_items())

    assert _by_type(collector) == {
        'vet-goed': [(_day(1), 'vet-goed')],
        WASTE_TYPE_GREEN: [(_day(7), 'gft')],
        WASTE_TYPE_PAPER: [(_day(16), 'papier')],
    }


async def test_keukenafval_without_another_name_stays_gft(hass, monkeypatch):
    items = [
        {'nameType': 'keukenafval', 'type': 'keukenafval', 'date': _day(2)},
        {'type': 'keukenafval', 'date': _day(9)},
        {'nameType': None, 'type': 'keukenafval', 'date': _day(16)},
    ]
    collector = await _update(hass, monkeypatch, items)

    assert _by_type(collector) == {
        WASTE_TYPE_GREEN: [(_day(2), 'keukenafval'), (_day(9), 'keukenafval'), (_day(16), 'keukenafval')],
    }


async def test_name_type_match_ignores_case_and_spaces(hass, monkeypatch):
    collector = await _update(hass, monkeypatch, [{'nameType': ' VET-goed ', 'type': 'keukenafval', 'date': _day(1)}])

    assert _by_type(collector) == {'vet-goed': [(_day(1), 'vet-goed')]}


async def test_custom_mapping_can_rename_vet_goed(hass, monkeypatch):
    collector = await _update(hass, monkeypatch, _meppel_items(), custom_mapping={'vet-goed': 'Vet'})

    assert _by_type(collector)['Vet'] == [(_day(1), 'vet-goed')]
    assert WASTE_TYPE_GREEN in _by_type(collector)
