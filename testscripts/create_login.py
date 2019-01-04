try:
    import testscripts.config as config
except ModuleNotFoundError:
    import config
import pyodbc

#sql = "CREATE LOGIN [POOP] WITH PASSWORD='POOPtest_123_P'"
sql = "DROP LOGIN [POOP]"

conn_string = "DRIVER={};SERVER={};UID={};PWD={}".format("{ODBC Driver 17 for SQL Server}", config.SQL_SERVER, config.SQL_USER, config.SQL_PASSWORD)

try:
    connection = pyodbc.connect(conn_string)
    cursor = connection.execute(sql)
    #rows = cursor.fetchall()
    connection.commit()
    connection.close()

    #print (rows)
except pyodbc.ProgrammingError as e:
    print ("Could not log in to {}: {}".format("SQLCLUSTER02", e))
