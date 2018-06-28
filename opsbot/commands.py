"""Commands available by the slackbot and some related helper functions."""
from datetime import datetime
from datetime import timedelta
import fnmatch
import json
import os
import random
import re
from six import iteritems
from slackbot.bot import listen_to
from slackbot.bot import respond_to
import time

import opsbot.config as config
#from opsbot.people import Level
#from opsbot.people import People
import opsbot.sql as sql
from opsbot.strings import Strings

user_path = config.DATA_PATH + 'users.json'
sql_log_base = config.LOG_PATH

#user_list = People()
maybe = []

# Build our word list:
with open(config.WORDPATH) as w:
    wordlist = w.readlines()
for word in wordlist:
    maybe.append(word.strip())


@respond_to("load")
def load_slack_users(message):
    """Put Slack users into JSON and dump into users.json."""
    user_list = []
    for userid, user in iteritems(message._client.users):
        user_info = {}
        user_info["name"] = user["name"]
        user_info["id"] = user["id"]
        user_info["approval_level"] = 0 # By default, not approved or denied
        user_info["metadata"] = "" # Metadata to be edited later on

        user_list.append(user_info)

    with open(user_path, 'w') as outfile:
        json.dump(user_list, outfile)

    message.reply("Successfully loaded users into json file.")


@respond_to("start")
def notify(message):
    """Start a minute-by-minute check of user expiration times and notify
       users when their time is almost up."""
    message.reply(":gear: Started expiration checking process; users will now "
                  "be notified if their access is about to expire.")
    flag = "tenmins"
    while True:
        if flag is "tenmins":
            info = sql.notify_users("hour")
            flag = "hour"
        elif flag is "hour":
            info = sql.notify_users("tenmins")
            flag = "deleted"
        elif flag is "deleted":
            flag = "tenmins"

        if (flag is "hour") or (flag is "tenmins"):
            for person in info:
                if len(info[person]) == 0:
                    continue
                users = get_users()
                for user in users:
                    if user["name"] == person:
                        chan = find_channel(message._client.channels, user["id"])
                        if flag is "hour":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_HOUR'].format(", ".join(info[person])))
                        elif flag is "tenmins":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_TENMINS'].format(", ".join(info[person])))
        elif flag is "deleted":
            with open("data/deleted.json") as deleted:
                deleted_users = json.load(deleted)

            for person, dbs in deleted_users.items():
                if not dbs: # If db list is empty
                    break
                users = get_users()
                for user in users:
                    if person == user["name"]:
                        chan = find_channel(message._client.channels, user["id"])
                        message._client.send_message(chan,
                                                     Strings['EXPIRE'].format(", ".join(dbs)))
                        deleted_users[person] = []
                        with open("data/deleted.json", 'w') as outfile:
                            json.dump(deleted_users, outfile)

        time.sleep(10)


def get_users():
    """Return dict of users stored in users.json."""
    with open(user_path, "r") as infile:
        return json.load(infile)


def get_admins():
    """Return list of users who are admins (approval level 50)."""
    users = get_users()
    admins = []
    for user in users:
        if user["approval_level"] == 50:
            admins.append(user)

    return admins


def save_users(user_list):
    """Save dict of users to users.json."""
    with open(user_path, "w") as outfile:
        json.dump(user_list, outfile)


def level_name(num):
    """Return appropriate approval level name for the number parameter.

    Ex: 50 = "admin".
    """
    level_names = {"50": "admin", "10": "approved", "5": "expired",
                   "0": "unknown", "-10": "denied"}

    return level_names[str(num)]


@respond_to('^upgrade (.*) (.*)')
def upgrade(message, target, num):
    """Upgrade a user to the specified approval level."""
    users = get_users()

    for user in users:
        if user["name"] != target:
            continue
        try:
            user["approval_level"] = int(num)
        except Exception:
            message.reply(":x: That's not a number, ya dingus. :)")
            return

    save_users(users)

    message.reply("Successfully upgraded user {} to approval level "
                  "{}.".format(target, num))


def pass_good_until(hours_good=config.HOURS_TO_GRANT_ACCESS):
    """Find time that a password is good until."""
    return datetime.now() + timedelta(hours=hours_good)


def friendly_time(time=None):
    """Rerurn the time in a print-friendly format."""
    if time is None:
        time = pass_good_until()
    return time.strftime(config.TIME_PRINT_FORMAT)


def generate_password(pass_fmt=config.PASSWORD_FORMAT):
    """Return a new password, using pass_fmt as a template.

    This is a simple replacement:
        # ==> a number from 0-99
        * ==> a word from the wordlist
        ! ==> a symbol
    """
    random.shuffle(maybe)

    new_pass = pass_fmt
    loc = 0
    while '*' in new_pass:
        new_pass = new_pass.replace("*", maybe[loc], 1)
        loc = loc + 1
        if loc == len(maybe):
            random.shuffle(maybe)
            loc = 0
    while '#' in new_pass:
        new_pass = new_pass.replace("#", str(random.randint(0, 99)), 1)
    while '!' in new_pass:
        new_pass = new_pass.replace(
            "!", random.choice(config.PASSWORD_SYMBOLS))
    return new_pass


def pretty_json(data, with_ticks=False):
    """Return the JSON data in a prettier format.

    If with_ticks is True, include ticks (```) around it to have it in
    monospace format for better display in slack.
    """
    pretty = json.dumps(data, sort_keys=True, indent=4)
    if with_ticks:
        pretty = '```' + pretty + '```'
    return pretty


def find_channel(channels, user):
    """Return the direct message channel of a user, if it exists."""
    for x in channels:
        if 'is_member' in channels[x]:
            continue
        if channels[x]["user"] == user:
            return channels[x]["id"]
    return ""


def have_channel_open(channels, user):
    """Return True if the user has a DM channel open with the bot."""
    for x in channels:
        chan = channels[x]
        if 'is_member' in chan:
            continue
        if chan['user'] == user:
                return True
    return False


@respond_to('channels')
def channels(message):
    """Display summary of channels in Slack.

    TODO: fix this :)
    """
    for channel in message._client.channels:
        if 'is_member' in channel:
            message.reply("{} ({})".format(chan['name'], chan['id']))
        elif 'is_im' in channel:
            print(chan)
            friendlyname = chan['user']
            try:
                friendlyname = chan['user']["name"]
            except (KeyError, AttributeError):
                pass
            message.reply("User channel: {} ({})".format(friendlyname,
                                                         chan['id']))


@respond_to('password$')
@respond_to('password (\d*)')
def pass_multi_request(message, num_words=1):
    """Display a generated password for the user."""
    try:
        tries = int(num_words)
    except ValueError:
        message.reply(Strings['NONSENSE'])
        return
    if (tries > 10):
        message.reply(Strings['TOO_MANY_PASSWORDS'])
        return
    if (tries < 1):
        message.reply(Strings['NONSENSE'])
        return
    for x in range(tries):
        message.reply("```" + generate_password() + "```")


@respond_to('help', re.IGNORECASE)
@listen_to('help', re.IGNORECASE)
def channel_help(message):
    """Reply with the link to the help doc url."""
    message.reply(Strings['HELP'].format(config.HELP_URL))


@respond_to('^approve me$', re.IGNORECASE)
def approve_me(message):
    """Send request to be approved to the approvers/admins."""
    users = get_users()
    for user in users:
        if user["id"] == message._get_user_id():
            if user["approval_level"] == 0: # Unknown
                message.reply(Strings['APPROVER_REQUEST'])
                admins = get_admins()
                names = []
                for admin in admins:
                    names.append(admin["name"])

                approval_message = Strings[
                    'APPROVER_REQUEST_DETAIL'].format(">, <@".join(names), user["name"])

                #message._client.send_message(config.AUTH_CHANNEL, approval_message)
                message._client.send_message("mcg_prod_auth", approval_message)
            else:
                message.reply(":x: Your approval level is already: " + int(user["approval_level"]))


@listen_to('^approve me$', re.IGNORECASE)
def approve_me_group(message):
    """Reply to 'approve me' in the group channel (redirect to a DM)."""
    users = get_users()
    sender_id = message._get_user_id()

    for user in users:
        if user["id"] == sender_id:
            if (user["approval_level"] == 0):
                message.reply(Strings['APPROVE_ME_REQUEST'])
            else:
                self_name = level_name(user["approval_level"])
                message.reply(":x: Your status is already: {}".format(self_name))


@listen_to('^approve (\S*)$')
def approve_person(message, target):
    """Approve a user, if the author of the msg is an admin.

    TODO: get this working
    """
    users = get_users()
    if target == 'me':
        return
    for user in users:
        if user["name"] == target:
            approver = message._get_user_id()
            admins = get_admins()
            for admin in admins:
                if admin["id"] == approver:
                    if user is not None:
                        if user["approval_level"] == 0:
                            message.reply("Approving user: '{}'".format(target))
                            user["approval_level"] = 10
                            save_users(users)
                        elif user["approval_level"] == -10:
                            message.reply(Strings['MARKED_DENIED'])
                        else:
                            message.reply(":x: {} is already: {}.".format(target,
                                                                      level_name(user["approval_level"])))
                    else:
                        message.reply(Strings['USER_NOT_FOUND'].format(target))
                else:
                    message.reply(Strings['CANT_APPROVE'])


@respond_to('^admins$')
def admin_list(message):
    """Display a list of all admins."""
    admins = get_admins()
    names = []
    for admin in admins:
        names.append(admin["name"])

    message.reply('My admins are: {}'.format(", ".join(names)))


@respond_to('^approved$')
def approved_list(message):
    """Display a list of all approved users."""
    users = get_users()
    names = []
    for user in users:
        if user["approval_level"] == 10: # "Approved" level
            names.append(user["name"])

    message.reply('Approved users are: {}'.format(", ".join(names)))


@respond_to('^denied$')
def denied_list(message):
    """Display a list of denied users."""
    users = get_users()
    names = []
    for user in users:
        if user["approval_level"] == -10: # "Denied" level
            names.append(user["name"])

    message.reply('Denied users are: {}'.format(", ".join(names)))


@respond_to('^unknown$')
def unknown_list(message):
    """Display a list of users without a known status."""
    users = get_users()
    names = []
    for user in users:
        if user["approval_level"] == 0: # "Unknown" level
            names.append(user["name"])

    if (len(names) > 100):
        message.reply(Strings['TOO_MANY_USERS'].format(len(names)))
        return

    message.reply('Unknown users are: {}'.format(", ".join(names)))


@respond_to('^me$')
def status(message):
    """Display the JSON data of the messaging user."""
    message.reply('User_id: ' +
                  str(message._client.users[message._get_user_id()]))


@respond_to('^body$')
def body(message):
    """Display the JSON data of this message.

    Mainly (only?) useful for understanding the JSON options available
    a message.
    """
    message.reply(str(message._body))


@respond_to('^users$')
def users(message):
    """Display number of total Slack users."""
    message.reply(Strings['USERS_FOUND'].format(len(get_users())))


@respond_to('^search (.*)')
def search_user(message, search):
    """Return users found from a search."""
    found = []
    search = search.lower()
    users = get_users()
    for user in users:
        if search in user['name'].lower():
            found.append('{} ({})'.format(user['name'], user["id"]))
    if len(found) == 0:
        message.reply('No user found by that key: {}.'.format(search))
        return
    message.reply('Users found: {}'.format(', '.join(found)))


@respond_to('^details (.*)')
def find_user_by_name(message, username):
    """Return the JSON of a given user."""
    for userid, user in iteritems(message._client.users):
        if user['name'] == username:
            message.reply(pretty_json(user, True))
            if (have_channel_open(message._client.channels, userid)):
                message.reply('User has a channel open.')
            else:
                message.reply("User doesn't have a channel open.")
            return
    message.reply('No user found by that name: {}.'.format(username))


#@respond_to('^server (\S*)$')
#@listen_to('^server (\S*)$')
def find_server(message, db):
    """Display the server a given database is on."""
    db_list = sql.database_list()
    if db in db_list:
        server = db_list[db]
        message.reply(Strings['DATABASE_SERVER'].format(db, server))
    else:
        message.reply(Strings['DATABASE_UNKNOWN'].format(db))


@listen_to('^grant (\S*)$')
def no_reason(message, db):
    """Display error when no reason given trying to 'grant' access."""
    message.reply(Strings['GRANT_EXAMPLE'].format(db))


def grant_sql_access(message, db, reason, readonly):
    """Grant access for the user to a the specified database."""
    db_list = sql.database_list()
    requested_dbs = []
    for db_name in db_list:
        if db in db_name:
            requested_dbs.append(db_name)

    users = get_users()
    requester = message._get_user_id()
    for user in users:
        if user["id"] == requester:
            name = user["name"]
            level = user["approval_level"]

    if (level == 10) or (level == 50):
        if (len(requested_dbs)) == 0:
            message.reply(Strings['DATABASE_UNKNOWN'].format(db))
            return

        password = generate_password()
        chan = find_channel(message._client.channels, message._get_user_id())
        #offset = int(user_list[requester].details['tz_offset']) # To be revisited later - timezone shenanigans
        expiration = pass_good_until() # + timedelta(seconds=offset)
        created_flag = False
        for db in requested_dbs:
            created = sql.create_sql_login(name,
                                           password,
                                           db,
                                           expiration,
                                           readonly,
                                           reason)
            # We want to remember if the password was ever created so we
            # can have a message about it.
            if created:
                created_flag = True
        friendly_exp = friendly_time(expiration)
        message.reply(Strings['GRANTED_ACCESS'].format(db, friendly_exp))
        if (len(requested_dbs) > 1):
            message.reply('{} databases affected.'.format(len(requested_dbs)))
        if created_flag:
            pass_created = Strings['PASSWORD_CREATED'].format(db, password)
            message._client.send_message(chan, pass_created)
        else:
            pass_reused = Strings['PASSWORD_REUSED'].format(db)
            message._client.send_message(chan, pass_reused)
        slack_id_msg = Strings['SLACK_ID'].format(name)
        message._client.send_message(chan, slack_id_msg)
        return
    if level == -10:
        message.reply('Request denied')
        return
    message.reply(Strings['NOT_APPROVED_YET'])


@listen_to('^grant (\S*) (.*)')
def grant_access(message, db, reason):
    """Request read only access to a database."""
    grant_sql_access(message, db, reason, True)


@listen_to('^grantrw (\S*) (.*)')
def grant_access_rw(message, db, reason):
    """Request read/write access to a database."""
    grant_sql_access(message, db, reason, False)


@respond_to("logs")
def logs_help(message):
    """Return brief information on logs."""
    message.reply(Strings["LOGS_HELP"])


@respond_to("logs (.*)")
def list_logs(message, target):
    """Return logs from a specified day."""
    try:
        target_time = time.strptime(target, "%m-%d-%Y")
        filename = "{}-{}.csv".format(target[:2], target[6:])
        #print (filename)
    except:
        message.reply(Strings["LOGS_WRONG_FORMAT"])
        return

    log_lines = []
    if os.path.exists('{}{}'.format(sql_log_base, filename)):
        with open('{}{}'.format(sql_log_base, filename), 'r') as f:
            log_lines = f.readlines()

    if len(log_lines) == 0:
        message.reply(Strings["NO_LOGS"])
        return

    final_lines = ""
    for line in log_lines:
        timestamp = line.split(" ")[0]
        timestamp = timestamp[5:] + "-" + timestamp[:4]
        if (time.strptime(timestamp, "%m-%d-%Y") == target_time):
            final_lines += (line + "\n")
        #print (timestamp)

    if final_lines != "":
        message.reply("```" + final_lines + "```")
        return
