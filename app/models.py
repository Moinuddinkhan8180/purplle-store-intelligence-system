from sqlalchemy.orm import declarative_base

from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Float
from sqlalchemy import Boolean
from sqlalchemy import DateTime

from sqlalchemy import JSON

Base = declarative_base()


class Event(Base):

    __tablename__ = "events"

    event_id = Column(String, primary_key=True)

    store_id = Column(String, index=True)

    camera_id = Column(String)

    visitor_id = Column(String, index=True)

    event_type = Column(String, index=True)

    timestamp = Column(DateTime, index=True)

    zone_id = Column(String)

    dwell_ms = Column(Integer)

    is_staff = Column(Boolean)

    confidence = Column(Float)

    event_metadata = Column(JSON)


class POSTransaction(Base):

    __tablename__ = "pos_transactions"

    transaction_id = Column(String, primary_key=True)

    store_id = Column(String, index=True)

    timestamp = Column(DateTime)

    basket_value = Column(Float)