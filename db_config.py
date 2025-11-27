"""
Database Configuration - PostgreSQL Only
All connections use PostgreSQL via DATABASE_URL environment variable
"""

import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

class DatabaseConfig:
    """PostgreSQL database configuration"""

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise EnvironmentError(
                "DATABASE_URL environment variable is required. "
                "Please set it to your PostgreSQL connection string."
            )

    def get_connection(self, db_name=None):
        """
        Get PostgreSQL database connection

        Args:
            db_name: Ignored (kept for backward compatibility)

        Returns:
            PostgreSQL connection object with RealDictCursor
        """
        return self._get_postgres_connection()

    def _get_postgres_connection(self):
        """Get PostgreSQL connection from DATABASE_URL"""
        try:
            conn = psycopg2.connect(
                self.database_url,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            return conn
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
            print(f"DATABASE_URL: {self.database_url[:50]}...")
            raise

    @contextmanager
    def get_cursor(self, db_name=None):
        """
        Context manager for database cursor
        Automatically commits on success, rollback on error

        Usage:
            with db_config.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                rows = cursor.fetchall()
        """
        conn = self.get_connection(db_name)
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def execute_query(self, query, params=None, db_name=None, fetch=True):
        """
        Execute a SQL query with automatic connection handling

        Args:
            query: SQL query string (PostgreSQL syntax with %s placeholders)
            params: Query parameters (tuple or dict)
            db_name: Ignored (kept for backward compatibility)
            fetch: Whether to fetch results (True) or just execute (False)

        Returns:
            Query results if fetch=True, else None
        """
        with self.get_cursor(db_name) as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if fetch:
                return [dict(row) for row in cursor.fetchall()]
            return None

    def execute_many(self, query, params_list, db_name=None):
        """
        Execute a SQL query multiple times with different parameters

        Args:
            query: SQL query string
            params_list: List of parameter tuples/dicts
            db_name: Ignored (kept for backward compatibility)
        """
        with self.get_cursor(db_name) as cursor:
            cursor.executemany(query, params_list)

    def table_exists(self, table_name, db_name=None):
        """
        Check if a table exists in PostgreSQL

        Args:
            table_name: Name of the table to check
            db_name: Ignored (kept for backward compatibility)

        Returns:
            Boolean indicating if table exists
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            )
        """
        result = self.execute_query(query, (table_name,))
        return result[0]['exists'] if result else False

# Global database configuration instance
db_config = DatabaseConfig()

def get_inventory_conn():
    """Get PostgreSQL connection for inventory data"""
    return db_config.get_connection()

def get_sales_conn():
    """Get PostgreSQL connection for sales data"""
    return db_config.get_connection()

def get_vehicle_cache_conn():
    """Get PostgreSQL connection for vehicle cache data"""
    return db_config.get_connection()

def get_taxonomy_conn():
    """Get PostgreSQL connection for taxonomy data"""
    return db_config.get_connection()
