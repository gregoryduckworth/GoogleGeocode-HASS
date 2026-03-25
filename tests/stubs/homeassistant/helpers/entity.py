"""Stubs for homeassistant.helpers.entity and config_validation."""
import voluptuous as vol


class Entity:
    """Minimal stub Entity base class."""

    hass = None

    @property
    def name(self):
        return None

    @property
    def state(self):
        return None

    @property
    def extra_state_attributes(self):
        return {}

    @property
    def entity_picture(self):
        return None

    def update(self):
        pass
