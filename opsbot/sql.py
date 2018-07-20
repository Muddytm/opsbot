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


def execute_sql(sql, database=None, server=None, get_rows=False):
    """Execute a SQL statement."""
    user = config.AZURE_USER
    if server:
        user += "@{}".format(server)
    password = config.AZURE_PASSWORD
    dsn = config.AZURE_DSN
    db = ''
    rows = []
    if database is not None:
        db = 'database=' + database
    conn_string = 'DSN={};UID={};PWD={};{}'.format(db, user, password, db)
    #conn_string = "Driver={ODBC Driver 13 for SQL Server};Server=tcp:{}." +
    #              "database.windows.net,1433;Database={};Uid={}@{};Pwd={};" +
    #              "Encrypt=yes;TrustServerCertificate=no;Connection" +
    #              "Timeout=30;".format(server, database,)
    connection = pyodbc.connect(conn_string)
    cursor = connection.execute(sql)
    if get_rows:
        rows = cursor.fetchall()
    connection.commit()
    connection.close()
    return rows


def execute_sql_count(sql, database=None):
    """Execute a SQL statement and return the count value.

    This works like execute_sql() but presumes the SQL looks like:

    SELECT COUNT(*) FROM table

    The query is run and the count value is returned.
    """
    row = execute_sql(sql, database, True)
    result = -1
    if row:
        result = row[0][0]
    return result


def delete_sql_user(user, database):
    """Delete a SQL user."""
    if not sql_user_exists(user, database):
        return
    sql = "DROP USER IF EXISTS [{}]".format(user)
    #execute_sql(sql, database)
    print ("SQL: " + sql)


def delete_sql_login(user):
    """Delete a SQL login."""
    if not sql_user_exists(user):
        return

    sql = "DROP LOGIN [{}]".format(user)
    #execute_sql(sql)
    print ("SQL: " + sql)


def sql_user_exists(user, database=None):
    """Return True if the SQL login already exists for a user.

    This queries the master if no database is selected (so checks for a
    login) or the specified database (in which case it looks for a
    database user)
    """
    table = 'sys.sql_logins'
    if database is not None:
       table = 'sysusers'
    sql = "SELECT count(*) FROM {} WHERE name = '{}'".format(table, user)
    count = execute_sql_count(sql, database)
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

    # Get active_sql.json
    if os.path.isfile(active_sql):
        with open(active_sql) as data_file:
            active_logins = json.load(data_file)

    # If user not in active_logins, then user does not currently have access to
    # any dbs (and thus doesn't have a login), so create a login
    if user not in active_logins:
        # Create empty user dict in active_sql
        active_logins[user] = []

        # Create login on every server
        with open(db_path) as data_file:
            databases = json.load(data_file)
        for serv in databases:
            sql = "CREATE LOGIN [{}] WITH PASSWORD='{}'".format(user, password)
            #execute_sql(sql, None, serv)
            print ("SQL: " + sql)
        created_login = True

    # If user does not have access to this database yet, give access
    found = False
    loc = None
    for i in range(len(active_logins[user])):
        if (active_logins[user][i]["db"] == database and
            active_logins[user][i]["server"] == server):
            found = True
            loc = i

    # Create granted instance
    if not found:
        sql = "CREATE USER [{}] FROM LOGIN [{}]".format(user, user)
        #execute_sql(sql, database, server)
        print ("SQL: " + sql)
        active_logins[user].append({"server": server, "db": database, "expiration": expire.isoformat()})
        created_user = True
    # Get this granted instance and set expiration time to 4 hours from now
    elif found:
        active_logins[user][loc]["expiration"] = expire.isoformat()

    # Write this all out to file
    with open(active_sql, 'w') as outfile:
        json.dump(active_logins, outfile)

    # If readwrite, upgrade. Never downgrade
    rights = "readonly"
    if not readonly:
        role = 'db_datawriter'
        rights = 'readwrite'
        sql = "EXEC sp_addrolemember N'{}', N'{}'".format(role, user)
        #execute_sql(sql, database)
        print ("SQL: " + sql)

    log = '{}, \"{}\", {}\n'.format(user,
                                    reason,
                                    rights)
    logging.info(log, database)
    return created_user, created_login


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
        servers[value["name"]] = []

    for server in servers:
        headers = {"Authorization": bearer, "Content-Type": "application/json"}
        r = requests.get("https://management.azure.com/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Sql/servers/{}/databases?api-version=2017-10-01-preview".format(config.SUB_ID, config.RESOURCE_GROUP, server),
                         headers=headers)

        for value in r.json()["value"]:
            if value["name"] != "master":
                servers[server].append(value["name"])

    with open("data/databases.json", 'w') as outfile:
        json.dump(servers, outfile)


def delete_expired_users():
    """Find any expired users and remove them."""
    with open(active_sql) as data_file:
        people = json.load(data_file)

    # Copying the JSON so we can edit it without risk
    people_copy = people.copy()

    people_changed = False
    done = False
    dec_i = False
    while not done:
        try:
            for user in people:
                for i in reversed(range(len(people[user]))):
                    delta = timedelta(hours=config.HOURS_TO_GRANT_ACCESS)
                    expired = datetime.now() # - delta
                    user_expires = datetime.strptime(people[user][i]["expiration"], "%Y-%m-%dT%H:%M:%S.%f")
                    if user_expires < expired:
                        success = True #delete_sql_user(user, people[user][i]["db"])
                        if success:
                            logging.info("{}, [USER REMOVED SUCCESSFULLY]\n".format(user), people[user][i]["db"])
                            del people_copy[user][i]
                            people_changed = True
                        else:
                            logging.info("{}, [USER REMOVAL FAILED]\n".format(user), db)

                # If list is empty, we delete logins
                if not people[user]:
                    with open(db_path) as data_file:
                        databases = json.load(data_file)
                    for serv in databases:
                        success = True #delete_sql_login(user)
                        if success:
                            logging.info("{}, [LOGIN REMOVED SUCCESSFULLY]\n".format(user), serv)
                            people_changed = True
                        else:
                            logging.info("{}, [LOGIN REMOVAL FAILED]\n".format(user), serv)
                    del people_copy[user]
        except RuntimeError:
            print ("Dictionary changed size during iteration, trying again...")
            time.sleep(1)
            with open(active_sql) as data_file:
                people = json.load(data_file)

            people_copy = people.copy()
            continue

        if people_changed:
            with open(active_sql, 'w') as outfile:
                json.dump(people_copy, outfile)
        done = True


def notify_users(interval):
    """Return a dict of people with databases they can access, that are soon
    to expire.

    Interval (either "hours" or "tenmins") determines what sort of check we're
    performing.
    """
    with open(active_sql) as data_file:
        people = json.load(data_file)

    with open("data/notified.json") as notified:
        notified_users = json.load(notified)

    info = {}

    for user in people:
        info[user] = []
        # For each one: if the user/database are not in notified_users, check
        # if they should be, and then append them to it.
        for i in range(len(people[user])):
            db = people[user][i]["db"]
            server = people[user][i]["server"]
            exp = people[user][i]["expiration"]
            if interval is "hour":
                if user not in notified_users["hour"]:
                    notified_users["hour"][user] = []

                user_expires = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%S.%f")
                expired = datetime.now()
                delta = timedelta(minutes=notify_hour)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (db not in notified_users["hour"][user]):
                        info[user].append({"db": db, "server": server})
                        notified_users["hour"][user].append(db)
            elif interval is "tenmins":
                if user not in notified_users["tenmins"]:
                    notified_users["tenmins"][user] = []

                user_expires = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%S.%f")
                expired = datetime.now()
                delta = timedelta(minutes=notify_tenmins)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (db not in notified_users["tenmins"][user]):
                        info[user].append({"db": db, "server": server})
                        notified_users["tenmins"][user].append(db)

    with open("data/notified.json", 'w') as outfile:
        json.dump(notified_users, outfile)

    return info
