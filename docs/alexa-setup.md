# Alexa setup

Journey Ready configures how it uses Alexa. Amazon account sign-in and custom-skill authorisation remain separate owner steps.

## Connect Alexa

For this installation Alexa Media Player is already downloaded in HACS, but no Amazon account or Echo has been configured.

Open **Settings > Devices & services > Add integration > Alexa Media Player**, then complete Amazon sign-in/MFA under the account that owns the Echos.

[Setup link](https://my.home-assistant.io/redirect/config_flow_start/?domain=alexa_media) · [Upstream configuration](https://github.com/alandtse/alexa_media_player/wiki/Configuration)

Verify a clearly labelled announcement on the intended Echo. Built-in Alexa Devices Speak/Announce notify entities are also supported for announcements, independently of voice answers.

## Set up Yes/No answers

Install the separate Alexa Actions custom skill and current Home Assistant question/launcher scripts. This is a skill project, not a HACS integration.

- [Current skill walkthrough](https://github.com/keatontaylor/alexa-actions/blob/master/docs/alexa-setup.md)
- [Current Home Assistant scripts and helper](https://github.com/keatontaylor/alexa-actions/blob/master/docs/home-assistant.md)

The skill needs a reachable authenticated Home Assistant endpoint, normally external HTTPS. Verify that access and account linking. Keep TLS verification enabled. Do not commit a token, password or external private URL to this repository.

Test the upstream question script first. It must accept text, event_id and alexa_device, and deliver alexa_actionable_notification events with event_id and event_response_type. The current upstream script handles its helper size and skill launcher.

## Select connections in Journey Ready

Open **Configure > Alexa**:

- Enable home-only Alexa messages.
- Select a Speak/Announce notify entity, or an Alexa Media Player speaker for announcements.
- Select the Alexa Media Player speaker and installed Alexa Actions question script for questions.
- Enter the Home Assistant user ID used by the authenticated Alexa Actions backend, after verifying it in a test event's context.user_id. Missing or different identities are rejected. If the backend provides no authenticated user context, keep phone answers.

The question script owns the skill ID and helper configuration. These are not separate fields in Journey Ready.

The backend identity proves which Home Assistant account sent the event. It does not identify the person speaking to the Echo. Configuring this ID explicitly trusts household voice answers for the selected person's pending question. Keep it blank when you need answers verified per person. Announcements still work without voice answers.

Set the person in Connections, then adjust quiet hours and phone fallback delay in Times and preferences.

## Verify the complete path

1. Test the phone question's Yes and No for the intended work date.
2. Confirm a phone answer prevents the delayed Alexa question.
3. Without a phone answer, confirm Alexa asks once when home.
4. Confirm spoken Yes and No arrive with the pending question's event ID.
5. Confirm silence uses the configured default, never a fabricated No.
6. Confirm away/unknown presence prevents speech.
7. Confirm quiet hours defer morning voice without repeating the phone summary.
8. Confirm departure prompts do not duplicate after reload.

Only mark Alexa ready after an audible announcement and both real response paths pass.
