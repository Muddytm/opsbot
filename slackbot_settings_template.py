"""Settings specific to the slackbot.

This is a template - fill out the API_TOKEN bit and save as
slackbot_settings.py.
"""

import opsbot.config as config

DEFAULT_REPLY = "Sorry but I didn't understand you"
ERRORS_TO = config.SLACK_ERROR_TARGET
API_TOKEN = "a token"

PLUGINS = ['opsbot.commands']
