import json
import logging

from pymongo import MongoClient
from pymongo.cursor import Cursor as MongoCursor
from pymongo.results import (
    DeleteResult,
    InsertManyResult,
    InsertOneResult,
    UpdateResult,
)

from django_mongodb.database import InterfaceError, NotSupportedError

logger = logging.getLogger(__name__)


class Cursor:
    def __init__(self, mongo_client: MongoClient, connection):
        self.mongo_client = mongo_client
        self.connection = connection
        self.result: MongoCursor | InsertManyResult | DeleteResult | None = None
        self.batch_size = None
        self.session = mongo_client.start_session()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if self.session:
            self.session.end_session()

    def close(self):
        if self.result is not None and hasattr(self.result, "close"):
            self.result.close()
        self.result = None

    @property
    def collections(self):
        return self.connection

    def __getattr__(self, name):
        try:
            return getattr(self.mongo_client, name)
        except AttributeError:
            pass

        try:
            return getattr(self.connection, name)
        except AttributeError:
            InterfaceError(f"Unsupported operation {name}")

    @property
    def rowcount(self):
        if self.cursor is None:
            raise RuntimeError
        if isinstance(self.result, InsertManyResult):
            return len(self.result.inserted_ids)
        if isinstance(self.result, DeleteResult):
            return self.result.deleted_count
        if isinstance(self.result, MongoCursor):
            if self.result.alive:
                return -1
            return self.result.retrieved
        if isinstance(self.result, UpdateResult):
            return self.result.matched_count  # update might be a no-op in case there are no changes
        raise NotSupportedError

    @property
    def lastrowid(self):
        if self.cursor is None:
            raise RuntimeError
        if isinstance(self.result, InsertOneResult):
            return self.result.inserted_id
        raise NotSupportedError

    def execute(self, command, params=None):
        logger.debug(json.dumps(command, default=str))
        match command:
            case {"op": "aggregate"}:
                self.result = self.connection[command["collection"]].aggregate(
                    command["pipeline"], session=self.session
                )
            case {"op": "insert_one"}:
                self.result = self.connection[command["collection"]].insert_one(
                    command["document"], session=self.session
                )
            case {"op": "update_many"}:
                self.result = self.connection[command["collection"]].update_many(
                    command["filter"], command["update"], session=self.session
                )
            case {"op": "bulk_write"}:
                self.result = self.connection[command["collection"]].bulk_write(
                    command["requests"], session=self.session
                )
            case {"op": "delete_many"}:
                self.result = self.connection[command["collection"]].delete_many(
                    command["filter"], session=self.session
                )
            case _:
                raise NotSupportedError

    def fetchmany(self, size=1):
        rows = []
        if self.batch_size != size:
            self.batch_size = size
            self.result.batch_size(size)
        for _ in range(size):
            try:
                rows.append(self.result.next())
            except StopIteration:
                return rows
        return rows

    def fetchone(self):
        try:
            return next(self.result)
        except StopIteration:
            return None

    def fetchall(self):
        return NotSupportedError

    def commit(self):
        pass
