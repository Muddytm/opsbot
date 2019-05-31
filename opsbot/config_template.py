"""Config variables for the system.

To access any of these do something like:
>>> import config
>>> print config.LOGGING_LEVEL


For the most part, nothing in this file should need to be changed unless you
want to change some of the core defaults. Variables that are custom to each
installation should be set in environment variables. Setting them there
prevent accidentally pushing those settings to source control and can be easily
changed in a per-installation basis without changing any files.

"""

import os

# Slack user id to send any errors to. Exception details will be rerouted
# to this user so you can know right away if there was a problem processing
# anything.
SLACK_ERROR_TARGET = os.getenv('SLACK_ERROR_TARGET', '')

# Azure access info. Pulled from ENV since it's more secure there than in
# a text file.
AZURE_DB =
AZURE_USER =
AZURE_PASSWORD =
TENANT_ID =
SUB_ID =
CLIENT_ID =
CLIENT_SECRET =
RESOURCE_GROUPS = []

SQL_USER =
SQL_PASSWORD =
SQL_SERVER_1 =
SQL_SERVER_2 =

TEMP_USER =
TEMP_PASSWORD =

SUMOLOGIC_ENDPOINT =
NEWRELIC_APP_ID =
NEWRELIC_USER =
NEWRELIC_PASS =


# Slack channel to listen to and do group replies in:
AUTH_CHANNEL = "prod_auth" #os.getenv('AUTH_SLACK_CHANNEL')
AUTH_CHANNEL_ERRORS = "prod_auth_errors"

# The part that goes after the server name
SERVER_SUFFIX = ".database.windows.net"

# URL of a help document:
HELP_URL = "https://isitchristmas.com/" #os.getenv('SLACK_HELP_URL', 'HELP_URL env variable not set.')

# Logging level. (10 = DEBUG, 20 = INFO, 30 = WARNING)
LOGGING_LEVEL = int(os.getenv('AUTH_LOGGING_LEVEL', 30))

# Everything below here is intended to be a sensible default and typically
# shouldn't need to be changed. If you expect to change one of these values
# consider moving it to the section above and read it from an env variable.


# Path to the opsbot directory base:
BASE_PATH = os.path.dirname(os.path.realpath(__file__)) + "/../"

# Data path to put various data files:
DATA_PATH = BASE_PATH + 'data/'

# Path for general logging:
LOG_PATH = BASE_PATH + 'log/'

# Path to the word list for passwords:
WORDPATH = DATA_PATH + 'wordlist.txt'

# How many hours is a generated account good for?
HOURS_TO_GRANT_ACCESS = 4

# Hour threshold for notification
NOTIFICATION_THRESHOLD_HOUR = 60

# Ten minute threshold for notification
NOTIFICATION_THRESHOLD_TENMINS = 10

# When sent to the slack channel, this is the printed format:
# '%b-%d %I:%M%p' looks like 'Feb-08 02:41PM'
TIME_PRINT_FORMAT = '%I:%M%p, %B %d'

# Password format.
# This is a simple replacement:
#     # ==> a number from 0-99
#     * ==> a word from the wordlist
#     ! ==> a symbol from password_symbols
PASSWORD_FORMAT = "*#*!*"

# Valid symbols to put in a password. Be sure to exclude anything in the
# password_format unless you want the possiblity of loops.
PASSWORD_SYMBOLS = "@$%^&(){}<>-+="

# How often (in seconds) to get a new list of databases:
CHECK_DATABASE_INTERVAL = 1800

# How often (in seconds) to check for expired users
DELETE_USER_INTERVAL = 60

# How often (in seconds) to get a new list of servers:
CHECK_SERVER_INTERVAL = 3600

# How often a given thread should check for work and/or stop signals, in sec.
# Smaller numbers = more checks, but faster timing to things like quit signals.
THREAD_SLEEP = 2

# Default time a thread should to its primary work, in seconds.
THREAD_WORK_TIMER = 60

# For CVW
BOSS = "caleb.hawkins"
