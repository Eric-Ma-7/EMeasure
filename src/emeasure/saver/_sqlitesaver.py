import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class SqliteSaver:
    def __init__(
        self,
        db_path: str | Path,
        experiment_name: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the saver.

        The experiment will not be registered in the `experiments` table
        until the first successful call to `add()`.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.experiment_name = experiment_name
        self.meta_dict = meta or {}
        self.meta_json = json.dumps(self.meta_dict, ensure_ascii=False, sort_keys=True)

        self.conn = sqlite3.connect(self.db_path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrent read/write behavior.
        self.conn.execute("PRAGMA journal_mode=WAL;")

        # Wait for a while when the database is locked.
        self.conn.execute("PRAGMA busy_timeout = 5000;")

        # Use a balanced durability/performance setting in WAL mode.
        self.conn.execute("PRAGMA synchronous = NORMAL;")

        self._registered = False
        self._data_keys: tuple[str, ...] | None = None
        self.start_time: str | None = None
        self.table_name: str | None = None

        self._create_experiments_table()

    def _create_experiments_table(self) -> None:
        """
        Create the experiments table if it does not exist.
        """
        sql = """
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            table_name TEXT NOT NULL UNIQUE,
            meta TEXT
        )
        """
        self.conn.execute(sql)
        self.conn.commit()

    def _table_name_exists(self, table_name: str) -> bool:
        """
        Check whether the target table name already exists.
        """
        sql_table = """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """
        row1 = self.conn.execute(sql_table, (table_name,)).fetchone()

        sql_exp = """
        SELECT 1
        FROM experiments
        WHERE table_name = ?
        LIMIT 1
        """
        row2 = self.conn.execute(sql_exp, (table_name,)).fetchone()

        return (row1 is not None) or (row2 is not None)

    def _generate_table_name_and_start_time(self) -> tuple[str, str]:
        """
        Generate a unique table name in the format `data_yymmddhhmmss`.

        If a collision happens within the same second, this method waits
        until the next available second.
        """
        while True:
            now = datetime.now()
            start_time = now.strftime("%Y-%m-%d %H:%M:%S")
            table_name = now.strftime("data_%y%m%d%H%M%S")

            if not self._table_name_exists(table_name):
                return table_name, start_time

            time.sleep(0.05)

    def _validate_column_name(self, name: str) -> None:
        """
        Validate a column name for safe SQL usage.
        """
        if not name.isidentifier():
            raise ValueError(
                f"Invalid column name: {name!r}. "
                "Column names must be valid Python identifiers."
            )

    def _coerce_scalar(self, value: Any) -> Any:
        """
        Convert scalar-like objects to basic Python scalar values when possible.
        """
        if value is None:
            return None

        if isinstance(value, (bool, int, float, str, bytes)):
            return value

        if hasattr(value, "item") and callable(value.item):
            try:
                return value.item()
            except Exception:
                pass

        return value

    def _infer_sqlite_type(self, value: Any) -> str:
        """
        Infer a SQLite column type from a Python value.
        """
        value = self._coerce_scalar(value)

        if isinstance(value, bool):
            return "INTEGER"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "REAL"
        if isinstance(value, bytes):
            return "BLOB"
        return "TEXT"

    def _normalize_value(self, value: Any) -> Any:
        """
        Convert a Python object into a value suitable for SQLite insertion.
        """
        value = self._coerce_scalar(value)

        if value is None:
            return None

        if isinstance(value, bool):
            return int(value)

        if isinstance(value, (int, float, str, bytes)):
            return value

        if hasattr(value, "tolist") and callable(value.tolist):
            try:
                value = value.tolist()
            except Exception:
                pass

        return json.dumps(value, ensure_ascii=False, default=str)

    def _create_data_table(self, table_name: str, data: dict[str, Any]) -> tuple[str, ...]:
        """
        Create the experiment data table based on the first data dictionary.
        """
        if not data:
            raise ValueError("The first data dictionary cannot be empty.")

        keys = tuple(data.keys())

        columns: list[str] = []
        for key in keys:
            self._validate_column_name(key)
            sqlite_type = self._infer_sqlite_type(data[key])
            columns.append(f'"{key}" {sqlite_type}')

        column_sql = ", ".join(columns)

        sql = f'''
        CREATE TABLE "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {column_sql}
        )
        '''
        self.conn.execute(sql)
        return keys

    def _register_experiment(self, start_time: str, table_name: str) -> None:
        """
        Insert the current experiment into the experiments table.
        """
        sql = """
        INSERT INTO experiments (experiment_name, start_time, table_name, meta)
        VALUES (?, ?, ?, ?)
        """
        self.conn.execute(
            sql,
            (self.experiment_name, start_time, table_name, self.meta_json),
        )

    def _insert_row(self, table_name: str, keys_in_order: tuple[str, ...], data: dict[str, Any]) -> None:
        """
        Insert one row into the data table using a fixed key order.
        """
        columns = ", ".join(f'"{key}"' for key in keys_in_order)
        placeholders = ", ".join("?" for _ in keys_in_order)
        values = tuple(self._normalize_value(data[key]) for key in keys_in_order)

        sql = f'''
        INSERT INTO "{table_name}" ({columns})
        VALUES ({placeholders})
        '''
        self.conn.execute(sql, values)

    def add(self, data: dict[str, Any]) -> None:
        """
        Add one row of data.

        On the first successful call, this method will:
        1. Generate the experiment start time and table name
        2. Create the data table
        3. Register the experiment in the experiments table
        4. Insert the first row

        All later calls must use the same set of keys as the first row.
        """
        if not isinstance(data, dict):
            raise TypeError("`data` must be a dictionary.")
        if not data:
            raise ValueError("`data` cannot be empty.")

        if not self._registered:
            table_name, start_time = self._generate_table_name_and_start_time()

            try:
                self.conn.execute("BEGIN")

                keys_in_order = self._create_data_table(table_name, data)
                self._register_experiment(start_time, table_name)
                self._insert_row(table_name, keys_in_order, data)

                self.conn.commit()

            except Exception:
                self.conn.rollback()
                raise

            self.table_name = table_name
            self.start_time = start_time
            self._data_keys = keys_in_order
            self._registered = True
            return

        assert self.table_name is not None
        assert self._data_keys is not None

        current_keys = tuple(data.keys())
        if set(current_keys) != set(self._data_keys):
            raise ValueError(
                "Data keys do not match the first inserted row.\n"
                f"Expected keys: {self._data_keys}\n"
                f"Got keys:      {current_keys}"
            )

        try:
            self._insert_row(self.table_name, self._data_keys, data)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        """
        Close the database connection.
        """
        if getattr(self, "conn", None) is not None:
            self.conn.close()

    def __enter__(self) -> "SqliteSaver":
        """
        Enter the runtime context.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit the runtime context and close the connection.
        """
        self.close()