"""Commands available by the slackbot and some related helper functions."""
from datetime import datetime
from datetime import timedelta
import fnmatch
import json
import opsbot.customlogging as logging
import os
import random
import re
import requests
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
public_channel = config.AUTH_CHANNEL
errors_channel = config.AUTH_CHANNEL_ERRORS

notify_flag = False


@respond_to("load")
def load_slack_users(message):
    """Put Slack users into JSON and dump into users.json.

    NOTE: USING THIS WILL RESET user.json. Uncomment the @respond_to bit
    if you really want to use this."""

    users = hf.get_users()

    for user in users:
        if user["id"] == message._get_user_id():
            if user["approval_level"] != "admin":
                message.reply("Insufficient privileges.")
                return

    with open(user_path) as outfile:
        users = json.load(outfile)

    existing_users = []

    for user in users:
        if (user["metadata"] != "" or user["approval_level"] != "unapproved"):
            existing_users.append(user)

    #print (existing_users)

    user_list = []
    for userid, user in iteritems(message._client.users):
        user_info = {}
        user_info["name"] = user["name"]
        user_info["id"] = user["id"]
        user_info["approval_level"] = "unapproved" # By default, not approved or denied
        user_info["metadata"] = "" # Metadata to be edited later on

        user_list.append(user_info)

    if existing_users:
        for user in existing_users:
            for listed_user in user_list:
                if user["id"] == listed_user["id"]:
                    user_list[user_list.index(listed_user)] = user

    with open(user_path, 'w') as outfile:
        json.dump(user_list, outfile)

    message.reply("Successfully loaded users into json file.")


@respond_to("expireme", re.IGNORECASE)
def expireme(message):
    """Expire the user's access right away."""
    users = hf.get_users()
    requester = message._get_user_id()
    for user in users:
        if user["id"] == requester:
            name = user["name"]
            break

    hf.expire_user(name)


@respond_to("logtest")
def logtest(message):
    """something"""
    logging.info("stuff", "server", "database")


@respond_to("start")
def notify(message):
    """Start a minute-by-minute check of user expiration times and notify
       users when their time is almost up.

    Basic flow: iterate through each process every 5 seconds. Processes are:

    Hour = notify the user one hour before their access is to expire
    Tenmins = notify the user ten minutes before their access is to expire
    Deleted = notify the user when their access has expired

    Each one works by looking at notified.json or deleted.json - if the database
    is not listed for the user in question"""
    # TODO: clean up this ugly mess

    global notify_flag

    if not notify_flag:
        notify_flag = True
        message.reply(":gear: Started expiration checking process; users will now "
                      "be notified if their access is about to expire.")
    else:
        message.reply("Cannot have more than one running instance of the notify "
                      "function.")
        return

    flag = "tenmins"
    while True:
        if flag is "deleted":
            info = sql.notify_users("hour")
            flag = "hour"
        elif flag is "hour":
            info = sql.notify_users("tenmins")
            flag = "tenmins"
        elif flag is "tenmins":
            info = sql.notify_users("deleted")
            flag = "deleted"

        for person in info:
            if len(info[person]) == 0:
                continue
            try:
                users = hf.get_users()
                for user in users:
                    if user["name"] == person:
                        dbs = []
                        servers = []
                        for grant in info[person]:
                            dbs.append(grant["db"])
                            servers.append(grant["server"])
                        chan = hf.find_channel(message._client.channels, user["id"])

                        if flag is "hour":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_HOUR'].format(", ".join(dbs)) + "\n"
                                                         "" + Strings["NOTIFY_EXPIRE_INFO"])
                            for db, server in zip(dbs, servers):
                                logging.info("{} reason=[NOTIFIED OF DATABASE ACCESS EXPIRING IN AN HOUR]\n".format(user["name"]), server, db, "notifyhour")
                        elif flag is "tenmins":
                            message._client.send_message(chan,
                                                         Strings['NOTIFY_EXPIRE_TENMINS'].format(", ".join(dbs)) + "\n"
                                                         "" + Strings["NOTIFY_EXPIRE_INFO"])
                            for db, server in zip(dbs, servers):
                                logging.info("{} reason=[NOTIFIED OF DATABASE ACCESS EXPIRING IN TEN MINUTES]\n".format(user["name"]), server, db, "notifyten")
                        elif flag is "deleted":
                            message._client.send_message(chan,
                                                         Strings['EXPIRE'].format(", ".join(dbs)))
                            message._client.send_message(public_channel,
                                                         Strings["EXPIRE_PING"].format(user["name"],
                                                                                       ", ".join(dbs)))
                            for db, server in zip(dbs, servers):
                                logging.info("{} reason=[NOTIFIED OF DATABASE ACCESS EXPIRING]\n".format(user["name"]), server, db, "notifyexpire")

                # Set up reminder to log out of SQL.
                userdata = None
                for filename in os.listdir("userdata/"):
                    if person.replace(".", "_") in filename:
                        with open("userdata/{}".format(filename)) as data_file:
                            userdata = json.load(data_file)

                        # Send "log out of SQL server" message
                        if "expired" in userdata and "new" in userdata["expired"]:
                            message._client.send_message(chan,
                                                         Strings["REMOVE_LOGIN"])
                            userdata["expired"] = "old"

                            with open("userdata/{}".format(filename), 'w') as outfile:
                                json.dump(userdata, outfile)

            except Exception as e:
                message._client.send_message(errors_channel, "```{}```".format(e))

        # For use with Datadog
        with open("/opt/opsbot35/data/status.txt", "w") as f:
            f.write(str(datetime.now()))

        time.sleep(5)


#@respond_to('^upgrade (.*) (.*)')
def upgrade(message, target, num):
    """Upgrade a user to the specified approval level.

    Commented out for now since this can be abused, usage should be limited."""
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


#@respond_to('^channels$')
def channels(message):
    """Display summary of channels in Slack.

    TODO: I have no idea why this doesn't work, so fix this :)
    """
    for channel in message._client.channels:
        if 'is_member' in channel:
            message.reply("{} ({})".format(channel['name'], channel['id']))
        elif 'is_im' in channel:
            #print(channel)
            friendlyname = channel['user']
            try:
                friendlyname = channel['user']["name"]
            except (KeyError, AttributeError):
                pass
            message.reply("User channel: {} ({})".format(friendlyname,
                                                         channel['id']))


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


@listen_to("^help$", re.IGNORECASE)
@respond_to("^help$", re.IGNORECASE)
def channel_help_respond(message):
    """Reply with help."""
    help_string = "```{}```".format(hf.help(message))
    message.reply(help_string)


#@listen_to("^help$", re.IGNORECASE)
#def channel_help_listen(message):
#    """Reply with help."""
#    help_string = "```{}```".format(hf.help(message))
#    chan = hf.find_channel(message._client.channels, message._get_user_id())
#    message._client.send_message(chan, help_string)


@listen_to("^help (.*)", re.IGNORECASE)
@respond_to("^help (.*)", re.IGNORECASE)
def channel_help_item(message, query):
    """Reply with help for the specific item."""
    query = query.lower()
    help_string = hf.help_item(query)
    message.reply(help_string)


@respond_to('^approve me$', re.IGNORECASE)
def approve_me(message):
    """Send request to be approved to the approvers/admins."""
    users = hf.get_users()
    for user in users:
        if user["id"] == message._get_user_id():
            if user["approval_level"] == "unapproved": # Unknown
                message.reply(Strings['APPROVER_REQUEST'])
                admins = hf.get_admins()
                names = []
                for admin in admins:
                    names.append(admin["name"])

                approval_message = Strings[
                    'APPROVER_REQUEST_DETAIL'].format(">, <@".join(names), user["name"])

                #message._client.send_message(config.AUTH_CHANNEL, approval_message)
                message._client.send_message(public_channel, approval_message)
            else:
                message.reply(":x: Your approval level is already: " + str(user["approval_level"]))


@listen_to('^approve me$', re.IGNORECASE)
def approve_me_group(message):
    """Reply to 'approve me' in the group channel (redirect to a DM)."""
    users = hf.get_users()
    sender_id = message._get_user_id()

    for user in users:
        if user["id"] == sender_id:
            if (user["approval_level"] == "unapproved"):
                message.reply(Strings['APPROVE_ME_REQUEST'])
            else:
                self_name = user["approval_level"]
                message.reply(":x: Your status is already: {}".format(self_name))


@listen_to('^approve (\S*)$', re.IGNORECASE)
def approve_person(message, target):
    """Approve a user, if the author of the msg is an admin."""
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
                        if user["approval_level"] == "unapproved":
                            message.reply("Approved user: <@{}>".format(target))
                            user["approval_level"] = "approved"
                            hf.save_users(users)
                            return
                        elif user["approval_level"] == "denied":
                            message.reply(Strings['MARKED_DENIED'])
                            return
                        else:
                            message.reply(":x: {} is already: {}.".format(target,
                                                                          user["approval_level"]))
                            return
                    else:
                        message.reply(Strings['USER_NOT_FOUND'].format(target))
                        return

    message.reply(Strings['CANT_APPROVE'])


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


@respond_to('^dbdetails (.*)')
@listen_to('^dbdetails (.*)')
def find_db_by_name(message, db):
    """Return information regarding this db, notably what server it's on
    and what users currently have access to it."""
    user_list = []
    for filename in os.listdir("userdata/"):

        with open("userdata/{}".format(filename)) as data_file:
            userdata = json.load(data_file)

        for i in range(len(userdata["access"])):
            if userdata["access"][i]["db"] == db:
                user_list.append(userdata["name"])
                break

    with open("data/databases.json") as data_file:
        data = json.load(data_file)

    correct_server = ""
    for server in data:
        if db in data[server]:
            correct_server = server

    if correct_server == "":
        message.reply("No database found!")
        return

    user_access = ""
    if user_list:
        user_access = "The following users currently have access: {}".format(", ".join(user_list))

    message.reply("The database \"{}\" is located on server \"{}\". {}".format(db,
                                                                               correct_server + config.SERVER_SUFFIX,
                                                                               user_access))


@listen_to('^grant (\S*)$', re.IGNORECASE)
def no_reason(message, db):
    """Display error when no reason given trying to 'grant' access, unless
    extending time."""
    #message.reply(Strings['GRANT_EXAMPLE'].format(db))
    try:
        hf.grant(message, db.lower(), "[EXTENDING ACCESS TIME]", True)
    except Exception as e:
        message._client.send_message(errors_channel, "```{}```".format(e))


@listen_to('^grantrw (\S*)$', re.IGNORECASE)
def no_reason(message, db):
    """Display error when no reason given trying to 'grantrw' access, unless
    extending time."""
    #message.reply(Strings['GRANT_EXAMPLE'].format(db))
    try:
        hf.grant(message, db.lower(), "[EXTENDING ACCESS TIME]", False)
    except Exception as e:
        message._client.send_message(errors_channel, "```{}```".format(e))


@listen_to('^grant (\S*) (.*)', re.IGNORECASE)
def grant_access(message, db, reason):
    """Request read only access to a database."""
    hf.grant(message, db.lower(), reason, True)

@listen_to('^grantrw (\S*) (.*)', re.IGNORECASE)
def grant_access_rw(message, db, reason):
    """Request read/write access to a database."""
    hf.grant(message, db.lower(), reason, False)


@respond_to("^approved$")
def approved(message):
    """Returns list of approved users."""
    hf.query_users(message, hf.get_users(), "approved")


@respond_to("^unapproved$")
def unapproved(message):
    """Returns list of unapproved users."""
    hf.query_users(message, hf.get_users(), "unapproved")


@respond_to("^admins$")
def admins(message):
    """Returns list of admins."""
    hf.query_users(message, hf.get_users(), "admin")


@respond_to("^denied$")
def denied(message):
    """Returns list of denied users."""
    hf.query_users(message, hf.get_users(), "denied")


@respond_to("^SLA$", re.IGNORECASE)
#@listen_to("^SLA$")
def sla_report(message):
    """Returns SLA report for the previous month."""
    query = "https://rpm.newrelic.com/optimize/sla_report/run?account_id={}&application_id={}&format=csv&interval=months"
    r = requests.get(query.format(config.NEWRELIC_ACC_ID, config.NEWRELIC_APP_ID),
                     auth=(config.NEWRELIC_USER, config.NEWRELIC_PASS))

    with open("log/sla_report.csv", "w") as f:
        f.write(r.text)

    message.channel.upload_file("sla_report.csv",
                                "log/sla_report.csv",
                                initial_comment="Here's your monthly SLA report.")
