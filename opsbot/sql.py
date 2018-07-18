"""Access SQL servers via ODBC.

This module handles all of the ODBC interaction for the slackbot, primarily
creating and removing users.
"""
import opsbot.customlogging as logging
import json
import os
import pyodbc
import time

from datetime import datetime
from datetime import timedelta

import opsbot.config as config

sql_logins = config.DATA_PATH + 'active_sql.json'
# active_databases = config.DATA_PATH + 'active_dbs.json'
db_path = config.DATA_PATH + 'databases.json'

notify_hour = config.NOTIFICATION_THRESHOLD_HOUR
notify_tenmins = config.NOTIFICATION_THRESHOLD_TENMINS


def execute_sql(sql, database=None, get_rows=False):
    """Execute a SQL statement."""
    user = config.AZURE_USER
    password = config.AZURE_PASSWORD
    dsn = config.AZURE_DSN
    db = ''
    rows = []
    if database is not None:
        db = 'database=' + database
    conn_string = 'DSN={};UID={};PWD={};{}'.format(dsn, user, password, db)
    connection = pyodbc.connect(conn_string)
    #logging.info("SQL RAN: on database \"{}\", running SQL: {}".format(database, sql))
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
    execute_sql(sql, database)
    print ("SQL: " + sql)


def delete_sql_login(user):
    """Delete a SQL login."""
    if not sql_user_exists(user):
        return

    sql = "DROP LOGIN [{}]".format(user)
    execute_sql(sql)
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


def create_sql_login(user, password, database, expire, readonly, reason):
    """Create a SQL login."""
    # create login qwerty with password='qwertyQ12345'
    # CREATE USER qwerty FROM LOGIN qwerty

    active_logins = {}
    created_login = False

    # Get active_sql.json
    if os.path.isfile(sql_logins):
        with open(sql_logins) as data_file:
            active_logins = json.load(data_file)

    # If user not in active_logins, then user does not currently have access to
    # any dbs (and thus doesn't have a login), so create a login
    if user not in active_logins:
        active_logins[user] = {}
        sql = "CREATE LOGIN [{}] WITH PASSWORD='{}'".format(user, password)
        execute_sql(sql)
        print ("SQL: " + sql)
        created_login = True

    #delete_sql_user(user, database)
    if database not in active_logins[user]:
        sql = "CREATE USER [{}] FROM LOGIN [{}]".format(user, user)
        execute_sql(sql, database)
        print ("SQL: " + sql)

    active_logins[user][database] = expire.isoformat()

    with open(sql_logins, 'w') as outfile:
        json.dump(active_logins, outfile)

    if not readonly:
        role = 'db_datawriter'
        rights = 'readwrite'
    else:
        role = 'db_datareader'
        rights = 'readonly'

    sql = "EXEC sp_addrolemember N'{}', N'{}'".format(role, user)
    execute_sql(sql, database)
    print ("SQL: " + sql)

    log = '{}, \"{}\", {}\n'.format(user,
                                    reason,
                                    rights)
    #print (log)
    logging.info(log, database)
    return created_login


def database_list():
    """Return a list of valid databases."""
    with open(db_path) as data_file:
        databases = json.load(data_file)
    return databases


def build_database_list():
    """Get a list of databases and save them to file."""
    dbs = execute_sql('SELECT * FROM sys.databases', '', True)
    #people = execute_sql('SELECT * FROM sys.database_principals', '', True)
    db_list = {}
    #svr = config.AZURE_SQL_SERVERS[0]
    for db in dbs:
        if db[0] == 'master':
            continue
        db_list[db[0]] = {}

    with open(db_path, 'w') as outfile:
        json.dump(db_list, outfile)


# def build_server_list():
#     """Get a list of servers and save them to file."""
#     dbs = execute_sql('SELECT * FROM sys.databases', '', True)
#     #people = execute_sql('SELECT * FROM sys.database_principals', '', True)
#     db_list = {}
#     #svr = config.AZURE_SQL_SERVERS[0]
#     for db in dbs:
#         if db[0] == 'master':
#             continue
#         db_list[db[0]] = {}
#
#     with open(db_path, 'w') as outfile:
#         json.dump(db_list, outfile)


def delete_expired_users():
    """Find any expired users and remove them."""
    with open(sql_logins) as data_file:
        people = json.load(data_file)
    people_changed = False
    done = False
    while not done:
        try:
            # For user and list of dbs that user is in
            for user, dbs in people.items():
                # For db in list of dbs, and expiration time for db
                for db, expiration in list(dbs.items()):
                    delta = timedelta(hours=config.HOURS_TO_GRANT_ACCESS)
                    expired = datetime.now() # - delta
                    user_expires = datetime.strptime(people[user][db], "%Y-%m-%dT%H:%M:%S.%f")
                    if user_expires < expired:
                        del people[user][db] # Get rid of db record for this user
                        people_changed = True

                        # Deleting user from notified.json
                        # TODO: make this shorter
                        with open("data/notified.json") as notified:
                            notified_users = json.load(notified)

                        if (user in notified_users["hour"]) and (db in notified_users["hour"][user]):
                            notified_users["hour"][user].remove(db)

                        if (user in notified_users["tenmins"]) and (db in notified_users["tenmins"][user]):
                            notified_users["tenmins"][user].remove(db)

                        with open("data/notified.json", 'w') as outfile:
                            json.dump(notified_users, outfile)

                        # Adding user to deleted.json
                        # TODO: make this shorter
                        with open("data/deleted.json") as deleted:
                            deleted_users = json.load(deleted)

                        if user not in deleted_users:
                            deleted_users[user] = []

                        deleted_users[user].append(db)

                        with open("data/deleted.json", 'w') as outfile:
                            json.dump(deleted_users, outfile)

                        delete_sql_user(user, db)

                        logging.info("{}, [USER REMOVED SUCCESSFULLY]\n".format(user), db)
                    else:
                        pass

                if not people[user]: # If all users have been removed, remove login
                    delete_sql_login(user)
                    #sql = "DROP LOGIN [{}]".format(user)
                    #execute_sql(sql)
                    logging.info("{}, [LOGIN REMOVED SUCCESSFULLY]\n".format(user), "[SERVER]")
                    del people[user]
                    with open(sql_logins, 'w') as outfile:
                        json.dump(people, outfile)
        except RuntimeError:
            print ("Dictionary changed size during iteration, trying again...")
            time.sleep(1)
            with open(sql_logins) as data_file:
                people = json.load(data_file)
            continue

        # We call this done just so we can exit the loop
        done = True

def notify_users(interval):
    """Return a dict of people with databases they can access, that are soon
    to expire.

    Interval (either "hours" or "tenmins") determines what sort of check we're
    performing.
    """
    with open(sql_logins) as data_file:
        people = json.load(data_file)

    with open("data/notified.json") as notified:
        notified_users = json.load(notified)

    info = {}

    for user in people:
        info[user] = []
        # For each one: if the user/database are not in notified_users, check
        # if they should be, and then append them to it.
        if interval is "hour":
            if user not in notified_users["hour"]:
                notified_users["hour"][user] = []
            for db in people[user]:
                user_expires = datetime.strptime(people[user][db], "%Y-%m-%dT%H:%M:%S.%f")
                expired = datetime.now()
                delta = timedelta(minutes=notify_hour)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (db not in notified_users["hour"][user]):
                        info[user].append(db)
                        notified_users["hour"][user].append(db)
        elif interval is "tenmins":
            if user not in notified_users["tenmins"]:
                notified_users["tenmins"][user] = []
            for db in people[user]:
                user_expires = datetime.strptime(people[user][db], "%Y-%m-%dT%H:%M:%S.%f")
                expired = datetime.now()
                delta = timedelta(minutes=notify_tenmins)
                if user_expires > expired:
                    if ((user_expires - expired) < delta) and (db not in notified_users["tenmins"][user]):
                        info[user].append(db)
                        notified_users["tenmins"][user].append(db)

    with open("data/notified.json", 'w') as outfile:
        json.dump(notified_users, outfile)

    return info
