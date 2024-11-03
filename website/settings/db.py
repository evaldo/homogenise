import os
import psycopg2
import platform

from psycopg2 import sql
from configparser import ConfigParser
from sqlalchemy.orm import sessionmaker
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from franz.openrdf.connect import ag_connect


def get_OS():
    return platform.system()

def get_dbconfig():
    OS = get_OS()
    config = ConfigParser()  
    match OS:
        case 'Linux':
            
            config.read(os.path.dirname(os.path.abspath('conf.ini'))+'/website/settings/conf.ini')
        case 'Windows':
            
            config.read(os.path.dirname(os.path.abspath('conf.ini'))+'\\website\\settings\\conf.ini')
        case "Darwin":
            raise InvalidOS("Mac OS Is not Acceptable")
        case _:
            raise InvalidOS("Unknow OS")
    
    return config


def get_allegro(project_id):
    config = get_dbconfig()

    host = config.get('allegro', 'host')
    port = int(config.get('allegro', 'port'))
    user = config.get('allegro', 'user')
    password = config.get('allegro', 'password')

    return ag_connect(str(project_id), host=host, port=port, user=user, password=password)


def get_engine():
    config = get_dbconfig()

    user = config.get('database', 'pguser')
    dbname = config.get('database', 'pgdb')
    password = config.get('database', 'pgpasswd')
    host = config.get('database', 'pghost')
    port = int(config.get('database', 'pgport'))

    url = URL.create(
        drivername="postgresql",
        username=user,
        password=password,
        host=host,
        database=dbname,
        port=port
    )

    con = psycopg2.connect(dbname=dbname, user=user, host=host, password=password)

    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    cur = con.cursor()

    cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = '"+config.get('database', 'pgdb')+"'")
    exists = cur.fetchone()
    if not exists: 
        set_scriptdb(cur)
        print('Created Database!')

        cur.close

    engine = create_engine(url)
    return engine

def get_dbsession():
    
    engine = get_engine()
    
    Session = sessionmaker(bind=engine)
    session = Session()

    return session

def set_scriptdb(cur):

    config = get_dbconfig()

    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.get('database', 'pgdb'))))

    con = psycopg2.connect(dbname=config.get('database', 'pgdb'), user=config.get('database', 'pguser'), host=config.get('database', 'pghost'), password=config.get('database', 'pgpasswd'))         
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    curschema = con.cursor()

    curschema.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS app"))
    
def get_cursor():
    config = get_dbconfig()
    con = psycopg2.connect(dbname=config.get('database', 'pgdb'), user=config.get('database', 'pguser'), host=config.get('database', 'pghost'), password=config.get('database', 'pgpasswd'))         
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return con.cursor()

def set_audit_log():

    cur=get_cursor()

    cur.execute("SELECT 1 FROM information_schema.triggers")
    exists = cur.fetchone()
    if not exists: 

        # Open and read the SQL file
        with open(os.path.dirname(os.path.abspath('trigger_function.sql'))+'/website/settings/trigger_function.sql', 'r') as file:
            sql_queries = file.read()

        # Split the SQL file content into individual queries
        #queries = sql_queries.split(';')
        queries = sql_queries
        cur.execute(queries)   

        # Iterate over the queries and execute them
        #for query in queries:
        #    try:
        #        if query.strip() != '':
        #            cur.execute(query)
        #            cur.commit()
        #            print("Query executed successfully!")
        #    except Exception as e:
        #        print("Error executing query:", str(e))

        # Close the cursor and the database connection 

        # Open and read the SQL file
        with open(os.path.dirname(os.path.abspath('trigger_table.sql'))+'/website/settings/trigger_table.sql', 'r') as file:
            sql_queries = file.read()        
        cur.execute(sql_queries) 

    cur.close

class InvalidOS(Exception):
    def __init__(self, message) -> None:
        super().__init__(message)