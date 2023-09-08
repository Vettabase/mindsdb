from collections import OrderedDict

import pandas as pd
import mysql.connector
from sqlalchemy import create_engine

from mindsdb_sql import parse_sql
from mindsdb_sql.render.sqlalchemy_render import SqlalchemyRender
from mindsdb_sql.parser.ast.base import ASTNode

from mindsdb.utilities import log
from mindsdb.integrations.libs.base import DatabaseHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
    RESPONSE_TYPE
)
from mindsdb.integrations.libs.const import HANDLER_CONNECTION_ARG_TYPE as ARG_TYPE


class MySQLHandler(DatabaseHandler):
    """
    This handler handles connection and execution of the MySQL statements.
    """

    name = 'mysql'

    def __init__(self, name, **kwargs):
        super().__init__(name)
        self.mysql_url = None
        self.parser = parse_sql
        self.dialect = 'mysql'
        self.connection_data = kwargs.get('connection_data', {})
        self.database = self.connection_data.get('database')

        self.connection = None
        self.is_connected = False

    def __del__(self):
        if self.is_connected is True:
            self.disconnect()

    def connect(self):
        if self.is_connected is True:
            return self.connection

        config = {
            'host': self.connection_data.get('host'),
            'port': self.connection_data.get('port'),
            'user': self.connection_data.get('user'),
            'password': self.connection_data.get('password'),
            'database': self.connection_data.get('database')
        }
        
        if 'conn_attrs' in self.connection_data:
            config['conn_attrs'] = self.connection_data['conn_attrs']

        ssl = self.connection_data.get('ssl')
        if ssl is True:
            ssl_ca = self.connection_data.get('ssl_ca')
            ssl_cert = self.connection_data.get('ssl_cert')
            ssl_key = self.connection_data.get('ssl_key')
            config['client_flags'] = [mysql.connector.constants.ClientFlag.SSL]
            if ssl_ca is not None:
                config["ssl_ca"] = ssl_ca
            if ssl_cert is not None:
                config["ssl_cert"] = ssl_cert
            if ssl_key is not None:
                config["ssl_key"] = ssl_key

        connection = mysql.connector.connect(**config)
        self.is_connected = True
        self.connection = connection
        return self.connection

    def disconnect(self):
        if self.is_connected is False:
            return
        self.connection.close()
        self.is_connected = False
        return

    def check_connection(self) -> StatusResponse:
        """
        Check the connection of the MySQL database
        :return: success status and error message if error occurs
        """

        result = StatusResponse(False)
        need_to_close = self.is_connected is False

        try:
            connection = self.connect()
            result.success = connection.is_connected()
        except Exception as e:
            log.logger.error(f'Error connecting to MySQL {self.connection_data["database"]}, {e}!')
            result.error_message = str(e)

        if result.success is True and need_to_close:
            self.disconnect()
        if result.success is False and self.is_connected is True:
            self.is_connected = False

        return result

    def native_query(self, query: str) -> Response:
        """
        Receive SQL query and runs it
        :param query: The SQL query to run in MySQL
        :return: returns the records from the current recordset
        """

        need_to_close = self.is_connected is False

        connection = self.connect()
        if query.trim().startswith('i'):
            query = query.replace('i', '', 1)
            query = query.replace('FROM ', 'FROM information_schema.')
        with connection.cursor(dictionary=True, buffered=True) as cur:
            try:
                cur.execute(query)
                if cur.with_rows:
                    result = cur.fetchall()
                    response = Response(
                        RESPONSE_TYPE.TABLE,
                        pd.DataFrame(
                            result,
                            columns=[x[0] for x in cur.description]
                        )
                    )
                else:
                    response = Response(RESPONSE_TYPE.OK)
                connection.commit()
            except Exception as e:
                log.logger.error(f'Error running query: {query} on {self.connection_data["database"]}!')
                response = Response(
                    RESPONSE_TYPE.ERROR,
                    error_message=str(e)
                )
                connection.rollback()

        if need_to_close is True:
            self.disconnect()

        return response

    def query(self, query: ASTNode) -> Response:
        """
        Retrieve the data from the SQL statement.
        """
        renderer = SqlalchemyRender('mysql')
        query_str = renderer.get_string(query, with_failback=True)
        return self.native_query(query_str)

    def get_tables(self) -> Response:
        """
        Get a list with all of the tabels in MySQL
        """
        q = "SHOW TABLES;"
        result = self.native_query(q)
        df = result.data_frame
        result.data_frame = df.rename(columns={df.columns[0]: 'table_name'})
        return result

    def get_columns(self, table_name) -> Response:
        """
        Show details about the table
        """
        q = f"DESCRIBE {table_name};"
        result = self.native_query(q)
        return result


connection_args = OrderedDict(
    user={
        'type': ARG_TYPE.STR,
        'description': 'The user name used to authenticate with the MySQL server.',
        'required': True,
        'label': 'User'
    },
    password={
        'type': ARG_TYPE.PWD,
        'description': 'The password to authenticate the user with the MySQL server.',
        'required': True,
        'label': 'Password'
    },
    database={
        'type': ARG_TYPE.STR,
        'description': 'The database name to use when connecting with the MySQL server.',
        'required': True,
        'label': 'Database'
    },
    host={
        'type': ARG_TYPE.STR,
        'description': 'The host name or IP address of the MySQL server. NOTE: use \'127.0.0.1\' instead of \'localhost\' to connect to local server.',
        'required': True,
        'label': 'Host'
    },
    port={
        'type': ARG_TYPE.INT,
        'description': 'The TCP/IP port of the MySQL server. Must be an integer.',
        'required': True,
        'label': 'Port'
    },
    ssl={
        'type': ARG_TYPE.BOOL,
        'description': 'Set it to False to disable ssl.',
        'required': False,
        'label': 'ssl'
    },
    ssl_ca={
        'type': ARG_TYPE.PATH,
        'description': 'Path or URL of the Certificate Authority (CA) certificate file',
        'required': False,
        'label': 'ssl_ca'
    },
    ssl_cert={
        'type': ARG_TYPE.PATH,
        'description': 'Path name or URL of the server public key certificate file',
        'required': False,
        'label': 'ssl_cert'
    },
    ssl_key={
        'type': ARG_TYPE.PATH,
        'description': 'The path name or URL of the server private key file',
        'required': False,
        'label': 'ssl_key',
    }
)

connection_args_example = OrderedDict(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='password',
    database='database'
)
