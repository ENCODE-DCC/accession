from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from accession.database.models import Base

# type hackery for classmethod
_DbSession = TypeVar("_DbSession", bound="DbSession")

ACCESSION_DB_FOLDER = ".accession"
ACCESSION_DB_FILE = "accession.db"


class DbSession:
    """
    Wrapper to encapsulate details of connecting to SQLite via SQLAlchemy
    """

    def __init__(self, uri: str, *args: Any, **kwargs: Any) -> None:
        """
        The engine is already lazy, so no need to wrap it in an @property
        """
        self.engine = create_engine(uri, *args, **kwargs)
        self._session: Optional[Session] = None

    @classmethod
    def with_home_dir_db_path(
        cls: Type[_DbSession], *args: Any, **kwargs: Any
    ) -> _DbSession:
        """
        Creates a new DbSession connected to the DB file in the current user's home
        directory.
        """
        db_path = cls._get_home_dir_db_path()
        db_uri = f"sqlite:///{db_path}"
        return cls(db_uri, *args, **kwargs)

    @classmethod
    def with_in_memory_db(
        cls: Type[_DbSession], *args: Any, **kwargs: Any
    ) -> _DbSession:
        """
        Creates a new DbSession connected to an in-memory, ephermeral DB
        """
        return cls("sqlite:///:memory:", *args, **kwargs)

    @property
    def session(self) -> Session:
        """
        Has the side effect of creating tables that do not already exist.
        """
        if self._session is None:
            Session = sessionmaker(bind=self.engine)
            self._session = Session()
            self._create_tables()
        return self._session

    def _create_tables(self) -> None:
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _get_home_dir_db_path() -> Path:
        """
        Creates a folder in the user's home directory to store the SQLite DB file if it does
        not already exist, and returns the `pathlib.Path` object pointing to where the DB
        file should go.
        """
        accession_db_dir = Path.home() / ACCESSION_DB_FOLDER
        accession_db_dir.mkdir(exist_ok=True)
        return accession_db_dir / ACCESSION_DB_FILE
