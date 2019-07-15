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
import sys
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


def help(message):
    """The main function for help stuff. Return help text."""
    users = get_users()
    hint = "You shouldn't see this message...if you do, bug my creator."
    for user in users:
        if user["id"] == message._get_user_id():
            if user["approval_level"] == "unapproved":
                hint = ("Looks like you're not approved yet for database access! "
                        "Message me `approve me` to request approval from the "
                        "admins.")
            elif user["approval_level"] == "denied":
                hint = ("Database access: denied")
            elif user["approval_level"] == "admin":
                hint = ("Database access: approved (also, you're an Authbot admin! Go you.)")
            else:
                hint = ("Hmm...this message shouldn't appear.")
            break

    help_text = ("For help on Authbot's functions, type \"help [topic]\", where "
                 "[topic] is one of (or part of) the following phrases: ")

    items = []
    help_strings = get_help_strings()
    for item in help_strings:
        items.append(item)

    return ("{}\n\n{}\n\n{}".format(hint, help_text, ", ".join(items)))


def help_item(query):
    """Return information for the query (help item)."""
    help_strings = get_help_strings()
    for item in help_strings:
        if query in item.lower():
            return ("```{}:\n\n{}```".format(item.upper(), help_strings[item]))

    return "Nothing like that was found in my help document."


def get_help_strings():
    """Return dict of help strings from helpdoc.md."""
    info = {}
    header = ""
    with open("opsbot/helpdoc.md") as f:
        content = f.readlines()

    for line in content:
        line = line.strip()
        if line.startswith("#"):
            header = line.replace("#", "").strip().lower()
        elif not line.startswith("#") and line:
            info[header] = line
            header = ""

    return info


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
        if user["approval_level"] == "admin":
            admins.append(user)

    return admins


def save_users(user_list):
    """Save dict of users to users.json."""
    with open(user_path, "w") as outfile:
        json.dump(user_list, outfile)


def pass_good_until(hours_good=config.HOURS_TO_GRANT_ACCESS, offset=0):
    """Find time that a password is good until."""
    pass_time = datetime.now() + timedelta(hours=hours_good)
    if offset > 0:
        pass_time = pass_time - timedelta(hours=offset)
    return pass_time


def friendly_time(time=None):
    """Rerurn the time in a print-friendly format."""
    if time is None:
        time = pass_good_until(config.HOURS_TO_GRANT_ACCESS, 7)
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
        if "user" in channels[x] and channels[x]["user"] == user:
            return channels[x]["id"]

    return ""


def have_channel_open(channels, user):
    """Return True if the user has a DM channel open with the bot."""
    for x in channels:
        chan = channels[x]
        if 'is_member' in chan:
            continue
        if "user" in chan and chan['user'] == user:
                return True
    return False


def grant_sql_access(message, db, reason, perms, ast_left=False, ast_right=False):
    """Grant access for the user to a the specified database."""
    # Get approval level of requester, to see if they're approved.
    users = get_users()
    requester = message._get_user_id()
    for user in users:
        if user["id"] == requester:
            name = user["name"]
            level = user["approval_level"]

    # Do this if we're giving SQL jobs access.
    if perms == "sqljobs":
        server_list = []
        with open ("data/databases.json") as f:
            data = json.load(f)

        for server in f:
            server_list.append(server.lower())

        if db.lower() in server_list:
            result = sql.create_sql_jobs_access(name, db, reason)

            if result == "noaccess":
                message.reply(Strings["SQLJOBS_NOACCESS"])
            elif result == "success":
                message.reply(Strings["SQLJOBS_SUCCESS"].format(db.upper()))

        return

    # Get db list
    db_list = sql.database_list()
    requested_dbs = []

    # This is using ast_left (if there's an asterisk on the left of the db name)
    # and ast_right (vice versa) to determine which dbs should be added to the
    # list. If both are False, just look for a db of that exact name.
    # TODO: implement this * business with glob instead.
    for server in db_list:
        for db_name in db_list[server]:
            if ast_left:
                if ast_right:
                    if db in db_name:
                        requested_dbs.append({"db": db_name, "server": server})
                else:
                    if db_name.endswith(db):
                        requested_dbs.append({"db": db_name, "server": server})
            elif ast_right:
                if db_name.startswith(db):
                    requested_dbs.append({"db": db_name, "server": server})
            else:
                if db == db_name:
                    requested_dbs.append({"db": db_name, "server": server})

    limit = 10
    if len(requested_dbs) >= limit:
        message.reply(Strings["TOO_MANY_DBS"].format(str(len(requested_dbs)), str(limit)))
        return

    if (level == "approved") or (level == "admin"):
        # Tell the user if there are no databases by that name
        if (len(requested_dbs)) == 0:
            message.reply(Strings['DATABASE_UNKNOWN'].format(db))
            return

        password = generate_password()
        chan = find_channel(message._client.channels, message._get_user_id())
        expiration = pass_good_until() # + timedelta(seconds=offset)
        login_created = False
        granted_msg = ""
        extended_msg = ""
        for db in requested_dbs:
            user_created, login_flag, valid = sql.create_sql_login(name,
                                                                   password,
                                                                   db["db"],
                                                                   db["server"],
                                                                   expiration,
                                                                   perms,
                                                                   reason)

            # We want the expiration time to look nice.
            friendly_exp = friendly_time()

            if not valid:
                message.reply(Strings["GRANT_EXAMPLE"].format(db["db"], db["db"]))
                continue

            # We just want to know if a login was created once:
            if login_flag:
                login_created = True

            # If database access was granted...
            if user_created:
                granted_msg += "Database \"{}\" on server \"{}\"\n".format(db["db"], db["server"] + config.SERVER_SUFFIX)
            # If database access was extended...
            else:
                extended_msg += "Database \"{}\" on server \"{}\"\n".format(db["db"], db["server"] + config.SERVER_SUFFIX)

        # Post message about access granted
        if granted_msg != "":
            if "readwrite" in perms:
                message.reply(Strings["GRANTED_ACCESS"].format(friendly_exp, granted_msg, "\n" + Strings['READWRITE'].format(config.BOSS)))
            else:
                message.reply(Strings["GRANTED_ACCESS"].format(friendly_exp, granted_msg, ""))

        # Post message about access extended
        if extended_msg != "":
            if "readwrite" in perms:
                message.reply(Strings["EXTENDED_ACCESS"].format(friendly_exp, extended_msg, "\n" + Strings['READWRITE'].format(config.BOSS)))
            else:
                message.reply(Strings["EXTENDED_ACCESS"].format(friendly_exp, extended_msg, ""))

        # Give password or tell user to use the one they've received already
        all_dbs = []
        for set in requested_dbs:
            all_dbs.append(set["db"])

        if login_created:
            message._client.send_message(chan, Strings["PASSWORD_CREATED"].format(password, ", ".join(all_dbs)))
        elif (granted_msg != "" or extended_msg != ""):
            message._client.send_message(chan, Strings["PASSWORD_REUSED"].format(", ".join(all_dbs)))

        if (granted_msg != "" or extended_msg != ""):
            slack_id_msg = Strings['SLACK_ID'].format(friendly_exp, name)
            message._client.send_message(chan, slack_id_msg)

        return
    if level == "denied":
        message.reply('Request denied')
        return

    message.reply(Strings['NOT_APPROVED_YET'])


def grant(message, db, reason, perms):
    """Master function for the grant commands.

    Supports wildcards of pretty much any variation."""

    # Handling SQL jobs case (db = server name)
    if perms == "sqljobs":
        grant_sql_access(message, db, reason, perms)
        return

    # Handling readonly/readwrite cases
    if ((db.endswith("*") and len(db[:-1]) < 3) or
       (db.startswith("*") and len(db[1:]) < 3) or
       (db == "*")):
        message.reply(Strings["DANGER"])
    elif ((not db.endswith("*")) and (not db.startswith("*")) and
         ("*" in db)):
        message.reply(Strings["POOP"])
    elif db.startswith("*"):
        if db.endswith("*"):
            grant_sql_access(message, db[1:][:-1], reason, perms, True, True)
            return
        grant_sql_access(message, db[1:], reason, perms, True)
    elif db.endswith("*"):
        grant_sql_access(message, db[:-1], reason, perms, False, True)
    else:
        grant_sql_access(message, db, reason, perms)


def expire_user(name):
    """Expire user."""

    name = name.replace(".", "_")

    try:
        with open("/opt/opsbot35/userdata/{}_active.json".format(name)) as f:
            data = json.load(f)

        for set in data["access"]:
            cur_time = datetime.strptime(set["expiration"], "%Y-%m-%dT%H:%M:%S.%f")
            ff_time = cur_time - timedelta(hours=config.HOURS_TO_GRANT_ACCESS, minutes=0)
            set["expiration"] = ff_time.strftime("%Y-%m-%dT%H:%M:%S.%f")

        with open("/opt/opsbot35/userdata/{}_active.json".format(name), "w") as f:
            json.dump(data, f)
    except IOError as e:
        pass
