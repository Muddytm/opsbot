"""Some smaller functions that aren't bot commands, but are used by bot
commands.
"""
from datetime import datetime
from datetime import timedelta
import fnmatch
import json
import opsbot.customlogging as logging
import os
import random
import re
from six import iteritems
import time

import opsbot.config as config
import opsbot.sql as sql
from opsbot.strings import Strings

user_path = config.DATA_PATH + 'users.json'
sql_log_base = config.LOG_PATH

maybe = []

# Build our word list:
with open(config.WORDPATH) as w:
    wordlist = w.readlines()
for word in wordlist:
    maybe.append(word.strip())


def query_users(message, users, level):
    """Return users of the approval level."""
    user_list = []
    for user in users:
        if user["approval_level"] == level:
            user_list.append(user["name"])

    if len(user_list) < 100:
        message.reply("{}".format(", ".join(user_list)))
    elif len(user_list) == 0:
        message.reply("None found.")
    else:
        message.reply("Too many to list ({})!".format(len(user_list)))


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


def grant_sql_access(message, db, reason, readonly, ast_left=False, ast_right=False):
    """Grant access for the user to a the specified database."""
    db_list = sql.database_list()
    requested_dbs = []

    # This is using ast_left (if there's an asterisk on the left of the db name)
    # and ast_right (vice versa) to determine which dbs should be added to the
    # list. If both are False, just look for a db of that exact name.
    for db_name in db_list:
        if ast_left:
            if ast_right:
                if db in db_name:
                    requested_dbs.append(db_name)
            else:
                if db_name.endswith(db):
                    requested_dbs.append(db_name)
        elif ast_right:
            if db_name.startswith(db):
                requested_dbs.append(db_name)
        else:
            if db == db_name:
                requested_dbs.append(db_name)

    # Get approval level of requester, to see if they're approved.
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

        # We want the expiration time to look nice.
        friendly_exp = friendly_time(expiration)

        # If a sql login/user was created, we want the user to know.
        if created_flag:
            message.reply(Strings['GRANTED_ACCESS'].format(db, friendly_exp))
            pass_created = Strings['PASSWORD_CREATED'].format(db, password)
            message._client.send_message(chan, pass_created)
        else:
            message.reply(Strings['EXTENDED_ACCESS'].format(db, friendly_exp))
            pass_reused = Strings['PASSWORD_REUSED'].format(db)
            message._client.send_message(chan, pass_reused)

        #if (len(requested_dbs) > 1):
        #    message.reply('{} databases affected.'.format(len(requested_dbs)))

        slack_id_msg = Strings['SLACK_ID'].format(friendly_exp, name)
        message._client.send_message(chan, slack_id_msg)
        return
    if level == -10:
        message.reply('Request denied')
        return

    message.reply(Strings['NOT_APPROVED_YET'])


def grant(message, db, reason, readonly):
    """Master function for the grant commands.

    Supports wildcards of pretty much any variation."""
    if ((db.endswith("*") and len(db[:-1]) < 4) or
       (db.startswith("*") and len(db[1:]) < 4) or
       (db == "*")):
        message.reply(Strings["DANGER"])
    elif ((not db.endswith("*")) and (not db.startswith("*")) and
         ("*" in db)):
        message.reply(Strings["POOP"])
    elif db.startswith("*"):
        if db.endswith("*"):
            grant_sql_access(message, db[1:][:-1], reason, readonly, True, True)
            return
        grant_sql_access(message, db[1:], reason, readonly, True)
    elif db.endswith("*"):
        grant_sql_access(message, db[:-1], reason, readonly, False, True)
    else:
        grant_sql_access(message, db, reason, readonly)


def logs_as_list(filename, target_time, db=None, user=None, perms=None):
    """Return logs in a file as a list, according to filename."""
    log_lines = []
    if os.path.exists('{}{}'.format(sql_log_base, filename)):
        with open('{}{}'.format(sql_log_base, filename), 'r') as f:
            log_lines = f.readlines()

    final_lines = ""
    for line in log_lines:
        tokens = line.split(",")
        timestamp = tokens[0].split()[0]
        timestamp = timestamp[5:] + "-" + timestamp[:4]
        if (datetime.strptime(timestamp, "%m-%d-%Y") == target_time):
            if db:
                if not wildcard_in_text(db, tokens[1]):
                    continue

            if user:
                if not wildcard_in_text(user, tokens[2]):
                    continue

            if perms:
                if not (perms.lower() == "readonly" or perms.lower() == "readwrite"):
                    continue

                if perms.lower() == "readonly" and len(tokens) >= 5 and tokens[4] != "readonly":
                    continue
                elif perms.lower() == "readwrite" and len(tokens) >= 5 and tokens[4] != "readwrite":
                    continue

            final_lines += (line + "\n")

    return final_lines


def wildcard_in_text(target, text):
    """Check for a wildcard token's presence in a string. Used mainly for
    logs_as_list.
    """
    target = target.strip()
    text = text.strip()
    if "*" in target:
        if target.startswith("*"):
            if target.endswith("*"):
                if target[1:][:-1] in text:
                    return True
            else:
                if text.endswith(target[1:]):
                    return True
        elif target.endswith("*"):
            if text.startswith(target[:-1]):
                return True

    else:
        if text == target:
            return True
