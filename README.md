(I'll put this here as documentation, but I'll need to put this in a much
friendlier format later.)

Authbot (yes, I know it says Opsbot at the top) is a tool used for instant
database access, without needing to go through the bother of requesting access
from humans.

# BOT SETUP

To actually get the bot going, you're going to need to give it some API keys,
IDs, and other things to get it moving.

First off, you'll want to give it your **Slack API token**. Copy
slackbot_settings_template.py to slackbot_settings.py, and put your Slack API
token into the API_TOKEN field. This will allow Authbot to connect to the
appropriate Slack application. Example:

``API_TOKEN = "blah-012345678910-XKyRDRRv71OktkBcGxoG0eyZ"``

Alongside this, you'll want to give the bot a channel to call home and listen in
on for requests. Create a dedicated Authbot channel (if you haven't already) in
Slack, and then put the name in opsbot/config.py under AUTH_CHANNEL. Example:

``AUTH_CHANNEL = "aperturescience_authbot_channel"``

Next, you've got all of this to fill out, in config.py:

``AZURE_USER = ""
AZURE_PASSWORD = ""
AZURE_DSN = ""
TENANT_ID = ""
SUB_ID = ""
CLIENT_ID = ""
CLIENT_SECRET = ""
RESOURCE_GROUP = ""
SUMOLOGIC_ENDPOINT = ""``

- **AZURE_USER** is your username for Azure that will be used to access servers
and databases.
- **AZURE_PASSWORD** is your password for that user.
- **AZURE_DSN** is currently unused, actually. Don't worry about this.
- **TENANT_ID** is your tenant ID, available on the Azure portal.
- **SUB_ID** is your subscription ID.
- **CLIENT_ID** can be retrieved by making an Azure app - this will be
needed to retrieve information for currently existing Azure servers and
databases.
- **CLIENT_SECRET** is the API "secret" key for that same app.
- **RESOURCE_GROUP** can be found on the page for your servers. To be changed,
so that this is more dynamic and does not need to be stated.
- **SUMOLOGIC_ENDPOINT** is for sending logs to Sumologic. Can be left blank if
you would rather have the logs be sent to named CSVs in /log.

Finally, you'll want to set up data sources for the servers that your specified
Azure user will be accessing. **Be sure** to make the data source names the same
as the server names for which they are created
(i.e., "CoolServer.windows.databases.net" would have a DSN of "CoolServer").

# ADMIN SETUP

At the moment, usage of the bot is quite simple, but first things first - **for
admins**, you will want to start the bot and message the bot with the word
"load". This will load all Slack users into a file named users.json, with
default settings. Yes, this is a bit iffy, so it will be changed later on to be
less crap.

Next, you will want to find the users in users.json that are to be the admins,
and set their "approval_level" value to "admin".

# USER SETUP

For general users, you will first want to become approved. Start by sending
this message to the Authbot app directly:

``approve me``

This will post a message in the Authbot-designated channel, calling for admins
to either approve or deny. If you are approved, then you will have access to any
database that the Authbot does, as long as you ask for access to be granted to
you.

To have access granted to you, send a message in the designated Authbot channel
with the format "grant [database] [reason]". Wildcards are supported. Some
examples are as follows:

``grant cooldb just because
grant azure* I'm really feeling it
grant *test* I want everything with "test" in the middle
grant *database gimme all databases with database at the end :)``

The first grant will give access to "cooldb", the second will give access to all
databases with "azure" at the beginning, the third will give access to all
databases with "test" in the middle, and the fourth will give access to all
databases with "database" at the end.

**Note**: Authbot does not allow wildcards with less than 4 characters, so "db*"
will fail. Additionally, the grant request will fail if access would be granted
for 10 databases or more.
