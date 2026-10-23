"""Announcements and the upstream Alexa Actions script adapter."""

from .notifications import can_speak


class Alexa:
    def __init__(self, hass, settings):
        self.hass, self.settings = hass, settings

    def allowed(self):
        from homeassistant.util import dt as dt_util

        person = self.hass.states.get(self.settings["person"])
        return can_speak(
            person.state if person else "unknown",
            dt_util.now().strftime("%H:%M"),
            self.settings.get("quiet_start", "22:00"),
            self.settings.get("quiet_end", "07:00"),
        )

    async def announce(self, text):
        if not self.settings.get("alexa_enabled") or not self.allowed():
            return False
        entity = self.settings.get("alexa_notify")
        if entity:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"message": text},
                target={"entity_id": entity},
                blocking=True,
            )
        elif speaker := self.settings.get("alexa_speaker"):
            await self.hass.services.async_call(
                "notify",
                "alexa_media",
                {"message": text, "target": [speaker], "data": {"type": "announce"}},
                blocking=True,
            )
        else:
            return False
        return True

    async def ask(self, question):
        if not self.settings.get("alexa_enabled") or not self.allowed():
            return False
        script = self.settings.get("alexa_question_script")
        speaker = self.settings.get("alexa_speaker")
        if not script or not speaker:
            return False
        # The upstream script owns the helper serialization and skill launcher.
        await self.hass.services.async_call(
            "script",
            script.split(".", 1)[1],
            {
                "text": f"Do you need your car after work on {question['date']}?",
                "event_id": f"JR_{question['token']}",
                "alexa_device": speaker,
            },
            blocking=True,
        )
        return True
