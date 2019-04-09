"""Access SQL servers via ODBC.

This module handles all of the ODBC interaction for the slackbot, primarily
creating and removing users.
"""
import opsbot.customlogging as logging
import json
import os
import pyodbc
import requests
import time

from datetime import datetime
from datetime import timedelta

import opsbot.config as config

active_sql = config.DATA_PATH + 'active_sql.json'
# active_databases = config.DATA_PATH + 'active_dbs.json'
db_path = config.DATA_PATH + 'databases.json'

notify_hour = config.NOTIFICATION_THRESHOLD_HOUR
notify_tenmins = config.NOTIFICATION_THRESHOLD_TENMINS


def betterprint(text):
    """Print only if there is a console to print to."""
    try:
        print(text)
    except OSError as e:
        pass


def execute_sql(sql, server, database=None, get_rows=False):
    """Execute a SQL statement."""
    if server == "mcgintsql01":
        user = config.AZURE_USER + "@" + server
        password = config.AZURE_PASSWORD
        server = "tcp:{}.database.windows.net".format(config.AZURE_DB)
    elif server == "SQLCLUSTER02":
        user = config.SQL_USER
        password = config.SQL_PASSWORD # TODO: replace in config
        server = config.SQL_SERVER_2 # TODO: replace
    elif server == "SQLCLUSTER01":
        user = config.SQL_USER
        password = config.SQL_PASSWORD # TODO: replace in config
        server = config.SQL_SERVER_1 # TODO: replace

    db = ''
    rows = []
    if database:
        db = 'Database=' + database + ";"
    else:
        db = ""

    #conn_string = 'DSN={};UID={};PWD={};{}'.format(dsn, user, password, db)
    conn_string = ("Driver={{ODBC Driver 17 for SQL Server}};Server={}" +
                   ",1433;{}Uid={};Pwd={};" +
                   "Encrypt=yes;TrustServerCertificate=yes;Connection " +
                   "Timeout=30;").format(server, db, user, password)
    #print (conn_string)
    #print (sql)
    count = 0
    while count < 3:
        try:
            connection = pyodbc.connect(conn_string)
            cursor = connection.execute(sql)
            connection.commit()
            connection.close()
            if get_rows:
                rows = cursor.fetchall()
            break
        except pyodbc.InterfaceError as e:
            betterprint("Login failed. Reason: {}".format(e))
            break
        except pyodbc.OperationalError as e:
            if count < 2:
                betterprint("Timed out...trying again. Reason: {}".format(e))
            else:
                betterprint("Timed out for the third time, I'm outta here.")
        except pyodbc.ProgrammingError as e:
            betterprint("Cannot access this server: {}".format(e))
            break

        count += 1

    #print ("exit now!")
    #time.sleep(60)
    return rows


def execute_sql_count(sql, server, database=None):
    """Execute a SQL statement and return the count value.

    This works like execute_sql() but presumes the SQL looks like:

    SELECT COUNT(*) FROM table

    The query is run and the count value is returned.
    """
    row = execute_sql(sql, server, database)
    #print (row)
    result = -1
    if row:
        result = row[0][0]
    return result


def delete_sql_user(user, server, database):
    """Delete a SQL user."""
    betterprint("Deleting {} from server {} and db {}".format(user, server, database))
    #if not sql_user_exists(user, server, database):
    #    return
    sql = "DROP USER [{}]".format(user)
    #print ("lets delete it now")
    try:
        execute_sql(sql, server, database)
        betterprint("SQL: " + sql)
        return True
    except:
        return False


def delete_sql_login(user, server):
    """Delete a SQL login."""
    #if not sql_user_exists(user, server):
    #    return
    sql = "DROP LOGIN [{}]".format(user)
    try:
        execute_sql(sql, server)
        betterprint("SQL: " + sql)
        return True
    except:
        return False


def sql_user_exists(user, server, database=None):
    """Return True if the SQL login already exists for a user.

    This queries the master if no database is selected (so checks for a
    login) or the specified database (in which case it looks for a
    database user)
    """
    table = 'sys.sql_logins'
    if database:
       table = 'sysusers'
    sql = "SELECT count(*) FROM {} WHERE name = '{}'".format(table, user)
    count = execute_sql_count(sql, server, database)
    #print (count)
    if (count > 0):
       return True
    return False


def create_sql_login(user, password, database, server, expire, readonly, reason):
    """Create a SQL login."""
    # create login qwerty with password='qwertyQ12345'
    # CREATE USER qwerty FROM LOGIN qwerty

    active_logins = {}
    created_user = False
    created_login = False

    # Get active user json
    if os.path.isfile("userdata/{}_active.json".format(clean(user))):
        with open("userdata/{}_active.json".format(clean(user))) as data_file:
            userdata = json.load(data_file)

        if "access" not in userdata:
            userdata["access"] = []
    else:
        userdata = {"name": user, "access": [], "notifications": {"hour": [], "tenmins": [], "deleted": []}}

    # If user does not have access to anything then we create logins
    if not userdata["access"]:
        # If user is trying to extend time without having access first
        if reason == "[EXTENDING ACCESS TIME]":
            return False, False, False
        # Create login on every server
        with open(db_path) as data_file:
            databases = json.load(data_file)
        for serv in databases:
            sql = "CREATE LOGIN [{}] WITH PASSWORD='{}'".format(user, password)
            betterprint("SQL: " + sql)
            logging.info("{} reason=[CREATING LOGIN]".format(user), server, "[NONE]", "createlogin")

            try:
                execute_sql(sql, serv)
            except pyodbc.InterfaceError as e:
                betterprint("Login failed :(")
        created_login = True

    # If user does not have access to this database yet, give access
    found = False
    loc = None
    for i in range(len(userdata["access"])):
        if (userdata["access"][i]["db"] == database and
            userdata["access"][i]["server"] == server):
            found = True
            loc = i

    # Create granted instance
    if not found:
        # If user is trying to extend time without having access first
        if reason == "[EXTENDING ACCESS TIME]":
            return False, False, False
        sql = "CREATE USER [{}] FROM LOGIN [{}]".format(user, user)
        execute_sql(sql, server, database)
        betterprint("SQL: " + sql)
        userdata["access"].append({"server": server, "db": database, "expiration": expire.isoformat()})
        created_user = True
    # Get this granted instance and set expiration time to 4 hours from now
    elif found:
        userdata["access"][loc]["expiration"] = expire.isoformat()

    # Write this all out to file
    with open("userdata/{}_active.json".format(clean(user)), 'w') as outfile:
        json.dump(userdata, outfile)

    # If readwrite, upgrade. Never downgrade
    rights = "readonly"
    roles = ['db_datareader']
    if not readonly:
        rights = 'readwrite'
        roles = ['db_datawriter', 'db_datareader']

    for role in roles:
        sql = "EXEC sp_addrolemember N'{}', N'{}'".format(role, user)
        execute_sql(sql, server, database)
        betterprint("SQL: " + sql)

    # Put reason in quotes if it's user-made
    if not reason.startswith("[") and not reason.endswith("]"):
        reason = "\"{}\"".format(reason)

    log = '{} reason={} rights={}\n'.format(user,
                                            reason,
                                            rights)
    logging.info(log, server, database, "createuser")
    return created_user, created_login, True


def database_list():
    """Return a list of valid databases."""
    with open(db_path) as data_file:
        databases = json.load(data_file)
    return databases


def build_database_list():
    """Get a list of servers and databases and save them to file."""
    # Get bearer token
    got_token = False
    body = {"grant_type": "client_credentials",
            "client_id": config.CLIENT_ID,
            "client_secret": config.CLIENT_SECRET,
            "resource": "https://management.azure.com/"}
    r = requests.post("https://login.microsoftonline.com/{}/oauth2/token".format(config.TENANT_ID),
                      data=body)

    bearer = "Bearer {}".format(r.json()["access_token"])
    got_token = True

    # Get list of servers
    headers = {"Authorization": bearer, "Content-Type": "application/json"}
    r = requests.get("https://management.azure.com/subscriptions/{}/providers/Microsoft.Sql/servers?api-version=2015-05-01-preview".format(config.SUB_ID),
                     headers=headers)

    servers = {}

    for value in r.json()["value"]:
        if "name" in value and value["name"] == "mcgintsql01":
            #if "tags" in value and "CWQI_environment" in value["tags"].keys() and value["tags"]["CWQI_environment"] == "production":
            servers[value["name"]] = []

    for server in servers:
        for group in config.RESOURCE_GROUPS:
            headers = {"Authorization": bearer, "Content-Type": "application/json"}
            r = requests.get("https://management.azure.com/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Sql/servers/{}/databases?api-version=2017-10-01-preview".format(config.SUB_ID, group, server),
                             headers=headers)

            if "value" in r.json():
                for value in r.json()["value"]:
                    if "name" in value and value["name"] != "master":
                        servers[server].append(value["name"])

    # Adding cluster databases to the list.
    clusters = ["SQLCLUSTER02", "SQLCLUSTER01"]
    sql = "SELECT name FROM sys.databases"

    for cluster in clusters:
        servers[cluster] = []
        if cluster == "SQLCLUSTER02":
            cluster_ip = config.SQL_SERVER_2
        elif cluster == "SQLCLUSTER01":
            cluster_ip = config.SQL_SERVER_1
        else:
            pass # This should never happen.

        conn_string = "DRIVER={};SERVER={};UID={};PWD={}".format("{ODBC Driver 17 for SQL Server}", cluster_ip, config.SQL_USER, config.SQL_PASSWORD)
        try:
            connection = pyodbc.connect(conn_string)
            cursor = connection.execute(sql)
            rows = cursor.fetchall()
            connection.commit()
            connection.close()

            banned = ["master"]
            for row in rows:
                if row[0] not in banned:
                    servers[cluster].append(row[0])
        except pyodbc.ProgrammingError as e:
            betterprint("Could not log in to {}: {}".format(cluster, e))

    with open("data/databases.json", 'w') as outfile:
        json.dump(servers, outfile)


# def delete_expired_users():
#     """Find any expired users and remove them."""
#
#     for filename in os.listdir("userdata/"):
#         changed = False
#
#         with open("userdata/{}".format(filename)) as data_file:
#             userdata = json.load(data_file)
#
#         if "access" not in userdata:
#             continue
#
#         name = userdata["name"]
#
#         for i in reversed(range(len(userdata["access"]))):
#             db = userdata["access"][i]["db"]
#             server = userdata["access"][i]["server"]
#             exp = userdata["access"][i]["expiration"]
#             delta = timedelta(hours=config.HOURS_TO_GRANT_ACCESS)
#             expired = datetime.now() # - delta
#             user_expires = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%S.%f")
#             if user_expires < expired:
#                 data = {"db": db, "server": server}
#                 if data in userdata["notifications"]["deleted"]:
#                     success = delete_sql_user(name, server, db)
#                     if success:
#                         logging.info("{} reason=[USER REMOVED SUCCESSFULLY]\n".format(name), server, db, "removeuser")
#                         del userdata["access"][i]
#                         if data in userdata["notifications"]["deleted"]:
#                             userdata["notifications"]["deleted"].remove(data)
#                         if data in userdata["notifications"]["tenmins"]:
#                             userdata["notifications"]["tenmins"].remove(data)
#                         if data in userdata["notifications"]["hour"]:
#                             userdata["notifications"]["hour"].remove(data)
#                         changed = True
#                     else:
#                         logging.info("{} reason=[USER REMOVAL FAILED]\n".format(name), server, db, "removeuserfailure")
#
#         # If list is empty, we delete logins
#         if not userdata["access"] and changed:
#             with open(db_path) as data_file:
#                 databases = json.load(data_file)
#             for server in databases:
#                 success = delete_sql_login(name, server)
#                 if success:
#                     logging.info("{} reason=[LOGIN REMOVED SUCCESSFULLY]\n".format(name), server, "[None]", "removelogin")
#                     changed = True
#                 else:
#                     logging.info("{} reason=[LOGIN REMOVAL FAILED]\n".format(name), server, "[None]", "removeloginfailure")
#
#         if changed:
#             with open("userdata/{}".format(filename), 'w') as outfile:
#                 json.dump(userdata, outfile)


def notify_users(interval):
    """Return a dict of people with databases they can access, that are soon
    to expire.

    Interval (either "hours" or "tenmins") determines what sort of check we're
    performing.
    """
    info = {}

    for filename in os.listdir("userdata/"):
        changed = False

        with open("userdata/{}".format(filename)) as data_file:
            userdata = json.load(data_file)

        if "access" not in userdata:
            continue

        name = userdata["name"]

        info[name] = []
        # For each one: if the user/database are not in notified_users, check
        # if they should be, and then append them to it.
        for i in range(len(userdata["access"])):
            db = userdata["access"][i]["db"]
            server = userdata["access"][i]["server"]
            exp = userdata["access"][i]["expiration"]
            user_expires = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%S.%f")
            expired = datetime.now()
            if interval is "hour":
                data = {"db": db, "server": server}
                delta = timedelta(minutes=notify_hour)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (data not in userdata["notifications"]["hour"]):
                        info[name].append(data)
                        userdata["notifications"]["hour"].append(data)
            elif interval is "tenmins":
                data = {"db": db, "server": server}
                delta = timedelta(minutes=notify_tenmins)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (data not in userdata["notifications"]["tenmins"]):
                        info[name].append(data)
                        userdata["notifications"]["tenmins"].append(data)
            elif interval is "deleted":
                data = {"db": db, "server": server}
                if user_expires < expired and (data not in userdata["notifications"]["deleted"]):
                    info[name].append(data)
                    userdata["notifications"]["deleted"].append(data)

        with open("userdata/{}".format(filename), 'w') as outfile:
            json.dump(userdata, outfile)

    return info


def clean(user):
    """Just a little method that replaces _ with ., and vice versa."""
    if "." in user:
        return user.replace(".", "_")
    elif "_" in user:
        return user.replace("_", ".")
    else:
        return user
