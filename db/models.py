from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WorkSession(Base):
    __tablename__ = "work_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[str] = mapped_column(String(128), index=True)
    source_file: Mapped[str] = mapped_column(String(256))
    target_current: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)

    logs: Mapped[list["SensorLog"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SensorLog(Base):
    __tablename__ = "sensor_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("work_session.id", ondelete="CASCADE"), nullable=True)
    work_id: Mapped[str] = mapped_column(String(128), index=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    sim_time_sec: Mapped[int] = mapped_column(Integer, default=0)

    power_on: Mapped[bool] = mapped_column(Boolean, default=False)
    voltage: Mapped[float] = mapped_column(Float, default=0.0)
    current: Mapped[float] = mapped_column(Float, default=0.0)
    vacuum: Mapped[float] = mapped_column(Float, default=0.0)
    speed_actual: Mapped[float] = mapped_column(Float, default=0.0)
    speed_recommended: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_target: Mapped[float] = mapped_column(Float, default=0.0)
    current_predicted: Mapped[float | None] = mapped_column(Float, nullable=True)

    position: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    phase: Mapped[str] = mapped_column(String(32), default="")
    buffer_ready: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped[WorkSession | None] = relationship(back_populates="logs")


Index("idx_sensor_log_recorded_work", SensorLog.recorded_at, SensorLog.work_id)