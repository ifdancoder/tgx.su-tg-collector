from sqlalchemy import Unicode, create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Table, UnicodeText, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import dotenv
import pytz

dotenv.load_dotenv()
username = os.getenv('MYSQL_USERNAME')
password = os.getenv('MYSQL_PASSWORD')
database = os.getenv('MYSQL_DATABASE')
host = os.getenv('MYSQL_HOST')

engine = create_engine('mysql://' + username + ':' + password + '@' + host + '/' + database + '?charset=utf8')

Base = declarative_base()
Session = sessionmaker(bind=engine)

class Timezones(Base):
    __tablename__ = 'timezones'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Unicode(255))
    offset = Column(Integer)

Base.metadata.create_all(engine)

def get_unique_time_shifts():
    time_shifts_set = set()
    for timezone_str in pytz.all_timezones:
        timezone = pytz.timezone(timezone_str)
        now = datetime.now()
        aware_datetime = timezone.localize(now)
        offset = aware_datetime.utcoffset()
        time_shifts_set.add(offset.total_seconds())
    time_shifts_set = sorted(list(time_shifts_set))

    time_shifts = []
    for time_shift in time_shifts_set:
        offset_time = datetime.fromtimestamp(abs(time_shift))
        time_str = offset_time.strftime('%H:%M')
        if time_shift < 0:
            time_str = f"UTC -{time_str}"
        else:
            time_str = f"UTC +{time_str}"
        time_shifts.append((time_str, time_shift // 60))
    return time_shifts

if not 'timezones' in Base.metadata.tables:
    Base.metadata.create_all(engine)

with Session() as session:
    if not session.query(Timezones).count():
        for timezone, offset_minutes in get_unique_time_shifts():
            new_timezone = Timezones(name=timezone, offset=offset_minutes)
            session.add(new_timezone)
            session.commit()

if __name__ == '__main__':
    Base.metadata.create_all(engine)