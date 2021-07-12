import datetime
import enum  # We don't `import enum from Enum` to avoid name conflict with sqlalchemy.Enum
from typing import Type, TypeVar

from sqlalchemy import Column, Date, Enum, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from accession.database import (
    FILE_TABLE_NAME,
    QUALITY_METRIC_TABLE_NAME,
    RUN_TABLE_NAME,
    WORKFLOW_LABEL_TABLE_NAME,
)
from accession.encode_models import EncodeFile, EncodeQualityMetric, FileStatus

_DbFile = TypeVar("_DbFile", bound="DbFile")
_QualityMetric = TypeVar("_QualityMetric", bound="QualityMetric")

Base = declarative_base()


class RunStatus(enum.Enum):
    Succeeded = "succeeded"
    Failed = "failed"

    def __str__(self) -> str:
        return self.value


class Run(Base):
    """
    Representation of an accessioning run of a single experiment. `workflow_labels` is
    somewhat special, ideally we would store them inline in an `ARRAY` but that's not
    supported in SQLite, so we need to use a foreign key relationship.
    """

    __tablename__ = RUN_TABLE_NAME
    id = Column(Integer, primary_key=True)
    experiment_at_id = Column(String, nullable=False)
    workflow_id = Column(String, nullable=False)
    date_created = Column(Date, nullable=False, default=datetime.date.today)
    status = Column(Enum(RunStatus), nullable=False)
    files = relationship("DbFile", backref=RUN_TABLE_NAME, uselist=True)
    workflow_labels = relationship(
        "WorkflowLabel", backref=RUN_TABLE_NAME, uselist=True
    )


class WorkflowLabel(Base):
    __tablename__ = WORKFLOW_LABEL_TABLE_NAME
    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    run = Column(Integer, ForeignKey(f"{RUN_TABLE_NAME}.id"))

    def __repr__(self) -> str:
        return self.value


class DbFile(Base):
    __tablename__ = FILE_TABLE_NAME
    id = Column(Integer, primary_key=True)
    portal_at_id = Column(String, nullable=False)
    status = Column(Enum(FileStatus), nullable=False)
    run = Column(Integer, ForeignKey(f"{RUN_TABLE_NAME}.id"))
    quality_metrics = relationship(
        "QualityMetric", backref=FILE_TABLE_NAME, uselist=True
    )

    @classmethod
    def from_encode_file(cls: Type[_DbFile], encode_file: EncodeFile) -> _DbFile:
        return cls(portal_at_id=encode_file.at_id, status=encode_file.status)


class QualityMetric(Base):
    __tablename__ = QUALITY_METRIC_TABLE_NAME
    id = Column(Integer, primary_key=True)
    portal_at_id = Column(String, nullable=False)
    file = Column(Integer, ForeignKey(f"{FILE_TABLE_NAME}.id"))

    @classmethod
    def from_encode_quality_metric(
        cls: Type[_QualityMetric], quality_metric: EncodeQualityMetric
    ) -> _QualityMetric:
        return cls(portal_at_id=quality_metric.at_id)

    def __repr__(self) -> str:
        return self.portal_at_id
