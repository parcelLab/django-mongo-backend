threadsafety = 2


class DataError(Exception):
    pass


class OperationalError(Exception):
    pass


class IntegrityError(Exception):
    pass


class InternalError(Exception):
    pass


class ProgrammingError(Exception):
    pass


class NotSupportedError(Exception):
    pass


class DatabaseError(Exception):
    pass


class InterfaceError(Exception):
    pass


class Error(Exception):
    pass
