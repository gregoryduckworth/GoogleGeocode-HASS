"""Stub for homeassistant.helpers.location."""


def has_location(entity):
    """Return True if entity has latitude and longitude attributes."""
    attr = entity.attributes
    return 'latitude' in attr and 'longitude' in attr
