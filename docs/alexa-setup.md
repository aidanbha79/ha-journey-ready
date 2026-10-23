# Alexa commissioning for Journey Ready

This guide covers announcements and spoken Yes/No answers. These are separate setup checks.

## 1. Connect Alexa Media Player

Open Home Assistant, then Settings > Devices & services > Add integration > Alexa Media Player. Complete Amazon sign-in and any MFA in the setup screen. Choose the Amazon region matching the account that owns the Echo devices. Keep passwords and authentication codes in that screen.

Setup link: https://my.home-assistant.io/redirect/config_flow_start/?domain=alexa_media

If it is not listed, verify the component is loaded and inspect Home Assistant logs. HACS reports a newer release, but an update and restart should follow a compatibility check rather than be assumed necessary.

Upstream configuration guide: https://github.com/alandtse/alexa_media_player/wiki/Configuration

## 2. Verify an announcement

Select one discovered Echo for commissioning. Send an explicitly labelled test announcement using the integration's actual available notification action. Confirm it plays on the intended device. Then test the planner's presence guard: home permits speech; away or unknown suppresses it. Do not infer success merely from a successful service-call response.

For installations using the built-in Alexa Devices integration instead, select its Speak or Announce notify entity. That supports spoken reminders, but does not by itself supply the question-response session required here.

Native documentation: https://www.home-assistant.io/integrations/alexa_devices/

## 3. Enable voice Yes/No

Use the separate Alexa Actionable Notifications skill with Alexa Media Player. Follow the upstream guide to create/configure a private skill in the Amazon Developer Console under the account owning the Echos, choose the appropriate language model, configure Home Assistant connectivity and authorise access. Account linking is supported by the guide and avoids copying a long-lived token into the skill when configured correctly. Keep TLS certificate verification enabled.

The skill requires an externally reachable HTTPS Home Assistant endpoint. If using Home Assistant Cloud, verify external reachability and account linking. The travel integration will not expose a new unauthenticated endpoint or manage Amazon account credentials.

Prerequisites: https://github.com/keatontaylor/alexa-actions/wiki/Prerequisites

Skill setup: https://github.com/keatontaylor/alexa-actions/wiki/Alexa-Talking-to-Home-Assistant-(The-Skill)

The newer SMAPI-based third-party alternative was researched but has not been selected or validated for this installation. Do not install it merely because it advertises automatic setup.

## 4. Select connections in the travel integration

Configure announcement device/backend, question skill ID and the helper/event contract required by the selected Alexa Actions setup. Choose the appropriate person entity for presence and the intended phone notification target.

The planned defaults ask the evening question at 19:00, wait 15 minutes for a phone answer, and then ask once through Alexa if home. Unknown or away presence prevents speech. These values remain editable.

## 5. Acceptance checks

- Phone Yes and No each update only the intended work date.
- Phone response prevents the delayed Alexa prompt.
- With no phone answer and the person home, Alexa asks once.
- Spoken Yes and No arrive in Home Assistant with the pending question's correlation ID.
- Silence times out without treating it as No.
- Away or unknown presence prevents both questions and route announcements.
- Departure reminders speak only at home and do not duplicate after restart.

Alexa is ready only after the audible announcement and both response paths are confirmed on a real Echo.
