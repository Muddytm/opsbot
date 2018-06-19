"""Access SQL servers via ODBC.

This module handles all of the ODBC interaction for the slackbot, primarily
creating and removing users.
"""
import json
import logging
import os
import pyodbc

from datetime import datetime
from datetime import timedelta

import opsbot.config as config

sql_log_base = config.LOG_PATH
sql_logins = config.DATA_PATH + 'active_sql.json'
# active_databases = config.DATA_PATH + 'active_dbs.json'
db_path = config.DATA_PATH + 'databases.json'

notify_time = config.NOTIFICATION_THRESHOLD


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
    logging.debug("On database '{}', running SQL: {}".format(database, sql))
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
    print ("This is where I would tell sql to: " + sql)


def create_sql_login(user, password, database, expire, readonly, reason):
    """Create a SQL login."""
    # create login qwerty with password='qwertyQ12345'
    # CREATE USER qwerty FROM LOGIN qwerty

    active_logins = {}

    created_login = False
    if os.path.isfile(sql_logins):
        with open(sql_logins) as data_file:
            active_logins = json.load(data_file)

    user_exists = sql_user_exists(user)
    if (user not in active_logins) or (not user_exists) or (not active_logins[user]):
        active_logins[user] = {}
        # if user_exists:
        #     #sql = "ALTER LOGIN [{}] WITH PASSWORD='{}'".format(user, password)
        #     active_logins[user][database] = expire.isoformat()
        # else:
        #     #sql = "CREATE LOGIN [{}] WITH PASSWORD='{}'".format(user, password)
        #     active_logins[user][database] = expire.isoformat()
        #print ("SQL: " + sql) #execute_sql(sql)
        created_login = True

    active_logins[user][database] = expire.isoformat()
    with open(sql_logins, 'w') as outfile:
        json.dump(active_logins, outfile)

    #delete_sql_user(user, database)
    sql = "CREATE USER [{}] FROM LOGIN [{}]".format(user, user)
    #execute_sql(sql, database)
    print ("SQL: " + sql)
    role = 'db_datareader'
    if not readonly:
        role = 'db_datawriter'
    sql = "EXEC sp_addrolemember N'{}', N'{}'".format(role, user)
    #execute_sql(sql, database)
    print ("SQL: " + sql)
    rights = 'readonly'
    if not readonly:
        rights = 'readwrite'
    log = '{} - {}: {}, {}, {}\n'.format(datetime.today(),
                                    user,
                                    database,
                                    rights,
                                    reason)
    filename = datetime.today().strftime("%Y-%m.csv")
    if os.path.exists('{}{}'.format(sql_log_base, filename)):
        fd = open('{}{}'.format(sql_log_base, filename), 'a')
    else:
        fd = open('{}{}'.format(sql_log_base, filename), "w+")
    fd.write(log)
    fd.close()
    return created_login


def sql_user_exists(user, database=None):
    """Return True if the SQL login already exists for a user.

    This queries the master if no database is selected (so checks for a
    login) or the specified database (in which case it looks for a
    database user)
    """
    #table = 'sys.sql_logins'
    #if database is not None:
    #    table = 'sysusers'
    #sql = "SELECT count(*) FROM {} WHERE name = '{}'".format(table, user)
    #count = execute_sql_count(sql, database)
    #if (count > 0):
    #    return True
    #return False
    with open("data/active_sql.json") as sql_users:
        users = json.load(sql_users)

    if database:
        if (user in users) and (database in users[user]):
            return True
        else:
            return False
    else:
        if user in users:
            return True
        else:
            return False


def database_list():
    """Return a list of valid databases."""
    with open(db_path) as data_file:
        databases = json.load(data_file)
    return databases


def build_database_list():
    """Get a list of databases and save them to file."""
    #dbs = execute_sql('SELECT * FROM sys.databases', '', True)
    #db_list = {}
    db_list = {"cooldb": "db", "awesomedb": "db", "radicaldb": "db", "tubulardb": "db"}
    #svr = config.AZURE_SQL_SERVERS[0]
    #for db in dbs:
    #    if db[0] == 'master':
    #        continue
    #    db_list[db[0]] = svr
    #logging.debug('Databases found: {}'.format(len(db_list)))
    with open(db_path, 'w') as outfile:
        json.dump(db_list, outfile)


def delete_expired_users():
    """Find any expired users and remove them."""
    with open(sql_logins) as data_file:
        people = json.load(data_file)
    people_changed = False
    for user, dbs in people.items():
        for db, expiration in list(dbs.items()):
            delta = timedelta(hours=config.HOURS_TO_GRANT_ACCESS)
            expired = datetime.now() # - delta
            user_expires = datetime.strptime(people[user][db], "%Y-%m-%dT%H:%M:%S.%f")
            #print (str(user_expires) + " vs " + str(expired))
            if user_expires < expired:
                logging.info('User {} expired on database {}. Removing.'.format(user, db))
                if sql_user_exists(user):
                    sql = "DROP LOGIN [{}]".format(user)
                    #execute_sql(sql, database)
                    print ("SQL: " + sql)
                    del people[user][db]
                    people_changed = True

                    with open("data/notified.json") as notified:
                        notified_users = json.load(notified)

                    notified_users[user].remove(db)

                    with open("data/notified.json", 'w') as outfile:
                        json.dump(notified_users, outfile)
            else:
                logging.debug('User: {}, on database: {}, expires: {}'.format(user, db, people[user][db]))

    if people_changed:
        with open(sql_logins, 'w') as outfile:
            json.dump(people, outfile)


def notify_users():
    """Notify users that their db access is about to expire."""
    with open(sql_logins) as data_file:
        people = json.load(data_file)

    with open("data/notified.json") as notified:
        notified_users = json.load(notified)

    info = {}

    for user in people:
        info[user] = []
        if user not in notified_users:
            notified_users[user] = []
        for db in people[user]:
            user_expires = datetime.strptime(people[user][db], "%Y-%m-%dT%H:%M:%S.%f")
            expired = datetime.now()
            delta = timedelta(hours=notify_time)
            if user_expires > expired:
                if ((user_expires - expired) < delta) and (db not in notified_users[user]):
                    info[user].append(db)
                    notified_users[user].append(db)

    with open("data/notified.json", 'w') as outfile:
        json.dump(notified_users, outfile)

    return info
