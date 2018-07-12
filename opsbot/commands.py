"""Commands available by the slackbot and some related helper functions."""
from datetime import datetime
from datetime import timedelta
import fnmatch
import json
import opsbot.customlogging as logging
import os
import random
import re
from six import iteritems
from slackbot.bot import listen_to
from slackbot.bot import respond_to
import time

import opsbot.config as config
import opsbot.sql as sql
from opsbot.strings import Strings
import opsbot.helper_functions as hf

user_path = config.DATA_PATH + 'users.json'
sql_log_base = config.LOG_PATH


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
    #logging.info("Loaded users into users.json.\n")


@respond_to("start")
def notify(message):
    """Start a minute-by-minute check of user expiration times and notify
       users when their time is almost up."""
    # TODO: clean up this ugly mess
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
                users = hf.get_users()
                for user in users:
                    if user["name"] == person:
                        chan = hf.find_channel(message._client.channels, user["id"])
                        if flag is "hour":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_HOUR'].format(", ".join(info[person])) + "\n"
                                                         "" + Strings["NOTIFY_EXPIRE_INFO"])
                            for db in info[person]:
                                logging.info("{}, [NOTIFIED OF DATABASE ACCESS EXPIRING IN AN HOUR]\n".format(user["name"]), db)
                        elif flag is "tenmins":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_TENMINS'].format(", ".join(info[person])) + "\n"
                                                         "" + Strings["NOTIFY_EXPIRE_INFO"])
                            for db in info[person]:
                                logging.info("{}, [NOTIFIED OF DATABASE ACCESS EXPIRING IN TEN MINUTES]\n".format(user["name"]), db)
        elif flag is "deleted":
            with open("data/deleted.json") as deleted:
                deleted_users = json.load(deleted)

            for person, dbs in deleted_users.items():
                if not dbs: # If db list is empty
                    continue
                users = hf.get_users()
                for user in users:
                    if person == user["name"]:
                        chan = hf.find_channel(message._client.channels, user["id"])
                        message._client.send_message(chan,
                                                     Strings['EXPIRE'].format(", ".join(dbs)))
                        for db in dbs:
                            logging.info("{}, [NOTIFIED OF DATABASE ACCESS EXPIRING]\n".format(user["name"]), db)
                        deleted_users[person] = []
                        with open("data/deleted.json", 'w') as outfile:
                            json.dump(deleted_users, outfile)

        time.sleep(5)


@respond_to('^upgrade (.*) (.*)')
def upgrade(message, target, num):
    """Upgrade a user to the specified approval level."""
    users = hf.get_users()

    for user in users:
        if user["name"] != target:
            continue
        try:
            user["approval_level"] = int(num)
        except Exception:
            message.reply(":x: That's not a number, ya dingus. :)")
            return

    hf.save_users(users)

    message.reply("Successfully upgraded user {} to approval level "
                  "{}.".format(target, num))


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
        message.reply("```" + hf.generate_password() + "```")


@respond_to('help', re.IGNORECASE)
@listen_to('help', re.IGNORECASE)
def channel_help(message):
    """Reply with the link to the help doc url."""
    message.reply(Strings['HELP'].format(config.HELP_URL))


@respond_to('^approve me$', re.IGNORECASE)
def approve_me(message):
    """Send request to be approved to the approvers/admins."""
    users = hf.get_users()
    for user in users:
        if user["id"] == message._get_user_id():
            if user["approval_level"] == 0: # Unknown
                message.reply(Strings['APPROVER_REQUEST'])
                admins = hf.get_admins()
                names = []
                for admin in admins:
                    names.append(admin["name"])

                approval_message = Strings[
                    'APPROVER_REQUEST_DETAIL'].format(">, <@".join(names), user["name"])

                #message._client.send_message(config.AUTH_CHANNEL, approval_message)
                message._client.send_message("mcg_prod_auth", approval_message)
            else:
                message.reply(":x: Your approval level is already: " + str(user["approval_level"]))


@listen_to('^approve me$', re.IGNORECASE)
def approve_me_group(message):
    """Reply to 'approve me' in the group channel (redirect to a DM)."""
    users = hf.get_users()
    sender_id = message._get_user_id()

    for user in users:
        if user["id"] == sender_id:
            if (user["approval_level"] == 0):
                message.reply(Strings['APPROVE_ME_REQUEST'])
            else:
                self_name = hf.level_name(user["approval_level"])
                message.reply(":x: Your status is already: {}".format(self_name))


@listen_to('^approve (\S*)$')
def approve_person(message, target):
    """Approve a user, if the author of the msg is an admin.

    TODO: get this working
    """
    users = hf.get_users()
    if target == 'me':
        return
    for user in users:
        if user["name"] == target:
            approver = message._get_user_id()
            admins = hf.get_admins()
            for admin in admins:
                if admin["id"] == approver:
                    if user is not None:
                        if user["approval_level"] == 0:
                            message.reply("Approving user: <@{}>".format(target))
                            user["approval_level"] = 10
                            hf.save_users(users)
                        elif user["approval_level"] == -10:
                            message.reply(Strings['MARKED_DENIED'])
                        else:
                            message.reply(":x: {} is already: {}.".format(target,
                                                                      hf.level_name(user["approval_level"])))
                    else:
                        message.reply(Strings['USER_NOT_FOUND'].format(target))
                else:
                    message.reply(Strings['CANT_APPROVE'])


@respond_to('^admins$')
def admin_list(message):
    """Display a list of all admins."""
    admins = hf.get_admins()
    names = []
    for admin in admins:
        names.append(admin["name"])

    message.reply('My admins are: {}'.format(", ".join(names)))


@respond_to('^approved$')
def approved_list(message):
    """Display a list of all approved users."""
    users = hf.get_users()
    names = []
    for user in users:
        if user["approval_level"] == 10: # "Approved" level
            names.append(user["name"])

    message.reply('Approved users are: {}'.format(", ".join(names)))


@respond_to('^denied$')
def denied_list(message):
    """Display a list of denied users."""
    users = hf.get_users()
    names = []
    for user in users:
        if user["approval_level"] == -10: # "Denied" level
            names.append(user["name"])

    message.reply('Denied users are: {}'.format(", ".join(names)))


@respond_to('^unknown$')
def unknown_list(message):
    """Display a list of users without a known status."""
    users = hf.get_users()
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
    message.reply(Strings['USERS_FOUND'].format(len(hf.get_users())))


@respond_to('^search (.*)')
def search_user(message, search):
    """Return users found from a search."""
    found = []
    search = search.lower()
    users = hf.get_users()
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
            message.reply(hf.pretty_json(user, True))
            if (hf.have_channel_open(message._client.channels, userid)):
                message.reply('User has a channel open.')
            else:
                message.reply("User doesn't have a channel open.")
            return
    message.reply('No user found by that name: {}.'.format(username))


#@respond_to('^server (\S*)$')
#@listen_to('^server (\S*)$')
# def find_server(message, db):
#     """Display the server a given database is on."""
#     db_list = sql.database_list()
#     if db in db_list:
#         server = db_list[db]
#         message.reply(Strings['DATABASE_SERVER'].format(db, server))
#     else:
#         message.reply(Strings['DATABASE_UNKNOWN'].format(db))


@listen_to('^grant (\S*)$')
def no_reason(message, db):
    """Display error when no reason given trying to 'grant' access."""
    message.reply(Strings['GRANT_EXAMPLE'].format(db))


@listen_to('^grant (\S*) (.*)')
def grant_access(message, db, reason):
    """Request read only access to a database."""
    if ((db.endswith("*") and len(db[:-1]) < 4) or
       (db.startswith("*") and len(db[1:]) < 4) or
       (db == "*")):
        message.reply(Strings["DANGER"])
    elif ((not db.endswith("*")) and (not db.startswith("*")) and
         ("*" in db)):
        message.reply(Strings["POOP"])
    elif db.startswith("*"):
        if db.endswith("*"):
            hf.grant_sql_access(message, db[1:][:-1], reason, True, True, True)
            return
        hf.grant_sql_access(message, db[1:], reason, True, True)
    elif db.endswith("*"):
        hf.grant_sql_access(message, db[:-1], reason, True, False, True)
    else:
        hf.grant_sql_access(message, db, reason, True)

@listen_to('^grantrw (\S*) (.*)')
def grant_access_rw(message, db, reason):
    """Request read/write access to a database."""
    if ((db.endswith("*") and len(db[:-1]) < 4) or
       (db.startswith("*") and len(db[1:]) < 4) or
       (db == "*")):
        message.reply(Strings["DANGER"])
    elif ((not db.endswith("*")) and (not db.startswith("*")) and
         ("*" in db)):
        message.reply(Strings["POOP"])
    elif db.startswith("*"):
        if db.endswith("*"):
            hf.grant_sql_access(message, db[1:][:-1], reason, False, True, True)
            return
        hf.grant_sql_access(message, db[1:], reason, False, True)
    elif db.endswith("*"):
        hf.grant_sql_access(message, db[:-1], reason, False, False, True)
    else:
        hf.grant_sql_access(message, db, reason, False)


@respond_to("^logs$")
def logs_help(message):
    """Return brief information on logs."""
    message.reply("{}\n{}\n{}".format(Strings["LOGS_HELP_1"],
                                      Strings["LOGS_HELP_2"],
                                      Strings["LOGS_HELP_3"]))


@respond_to("^logs (.*)")
def list_logs(message, target):
    """Do one of the following:
    - Post logs for a specified day
    - Post logs for a specified day for a specified database
    - Post logs for a specified range of days
    - post logs for a specified range of days for a specific database
    """

    tokens = target.split()
    chan = hf.find_channel(message._client.channels, message._get_user_id())

    if len(tokens) == 1:
        try:
            target_time = datetime.strptime(tokens[0], "%m-%d-%Y")
            filename = "{}-{}.csv".format(target_time.strftime("%m"),
                                          target_time.strftime("%Y"))
        except:
            message.reply(Strings["LOGS_WRONG_FORMAT"])
            return

        final_lines = hf.logs_as_list(filename, target_time)

        if final_lines != "":
            filename = "{}.csv".format(tokens[0])
            with open ("user_logs/{}".format(filename), "w") as f:
                    f.write(final_lines)

            message.channel.upload_file(filename, "user_logs/{}".format(filename),
                                        initial_comment=Strings["YOUR_LOGS"])
            return
    elif len(tokens) == 2:
        try:
            target_time = datetime.strptime(tokens[0], "%m-%d-%Y")
            try:
                target_time_end = datetime.strptime(tokens[1], "%m-%d-%Y")
                final_lines = ""
                while target_time <= target_time_end:
                    filename = "{}-{}.csv".format(target_time.strftime("%m"),
                                                  target_time.strftime("%Y"))
                    final_lines += hf.logs_as_list(filename, target_time)
                    target_time = target_time + timedelta(days=1)

                if final_lines != "":
                    filename = "{}_to_{}.csv".format(tokens[0], tokens[1])
                    with open ("user_logs/{}".format(filename), "w") as f:
                        f.write(final_lines)

                    message.channel.upload_file(filename, "user_logs/{}".format(filename),
                                                initial_comment=Strings["YOUR_LOGS"])
                    return
            except:
                filename = "{}-{}.csv".format(target_time.strftime("%m"),
                                              target_time.strftime("%Y"))

                final_lines = hf.logs_as_list(filename, target_time, tokens[1])

                if final_lines != "":
                    filename = "{}_for_{}.csv".format(tokens[0], tokens[1])
                    with open ("user_logs/{}".format(filename), "w") as f:
                        f.write(final_lines)

                    message.channel.upload_file(filename, "user_logs/{}".format(filename),
                                                initial_comment=Strings["YOUR_LOGS"])
                    return
        except:
            message.reply(Strings["LOGS_WRONG_FORMAT"])
            return
    elif len(tokens) == 3:
        try:
            target_time = datetime.strptime(tokens[0], "%m-%d-%Y")
            target_time_end = datetime.strptime(tokens[1], "%m-%d-%Y")
            final_lines = ""
            while target_time <= target_time_end:
                filename = "{}-{}.csv".format(target_time.strftime("%m"),
                                              target_time.strftime("%Y"))
                final_lines += hf.logs_as_list(filename, target_time, tokens[2])
                target_time = target_time + timedelta(days=1)

            if final_lines != "":
                filename = "{}_to_{}_for_{}.csv".format(tokens[0], tokens[1], tokens[2])
                with open ("user_logs/{}".format(filename), "w") as f:
                    f.write(final_lines)

                message.channel.upload_file(filename, "user_logs/{}".format(filename),
                                            initial_comment=Strings["YOUR_LOGS"])
                return
        except:
            message.reply(Strings["LOGS_WRONG_FORMAT"])
            return

    message.reply(Strings["NO_LOGS_AVAILABLE"])


@respond_to("^approved$")
def approved(message):
    """Returns list of approved users."""
    hf.query_users(message, hf.get_users(), 10)


@respond_to("^unapproved$")
def unapproved(message):
    """Returns list of unapproved users."""
    hf.query_users(message, hf.get_users(), 0)


@respond_to("^admins$")
def admins(message):
    """Returns list of admins."""
    hf.query_users(message, hf.get_users(), 50)


@respond_to("^denied$")
def denied(message):
    """Returns list of denied users."""
    hf.query_users(message, hf.get_users(), -10)
