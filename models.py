from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, Text
)
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="viewer", nullable=False)  # 'admin' | 'viewer'

class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    type = Column(String(50), nullable=False)  # academic|lab|library|hostel|cafeteria|admin|lighting
    is_24h = Column(Boolean, default=False, nullable=False)
    peak_kw = Column(Float, nullable=False)
    idle_pct = Column(Float, default=0.15, nullable=False)

    readings = relationship("MeterReading", back_populates="building", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="building", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="building", cascade="all, delete-orphan")

class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    ts = Column(DateTime, nullable=False, index=True)
    kwh = Column(Float, nullable=False)

    building = relationship("Building", back_populates="readings")

    __table_args__ = (
        UniqueConstraint("building_id", "ts", name="uq_building_ts"),
        Index("ix_building_ts", "building_id", "ts"),
    )

class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    rule = Column(String(100), nullable=False)  # after_hours, weekend_waste, daylight_lighting, spike
    start_ts = Column(DateTime, nullable=False)
    end_ts = Column(DateTime, nullable=False)
    wasted_kwh = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False)  # High, Medium, Low
    evidence = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(20), default="open", nullable=False)  # open, resolved

    building = relationship("Building", back_populates="anomalies")

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    anomaly_rule = Column(String(100), nullable=False)
    fix_text = Column(Text, nullable=False)
    capture_rate = Column(Float, nullable=False)
    kwh_week = Column(Float, nullable=False)
    rupees_year = Column(Float, nullable=False)
    co2_t_year = Column(Float, nullable=False)
    applied = Column(Boolean, default=False, nullable=False)

    building = relationship("Building", back_populates="recommendations")

class Weather(Base):
    __tablename__ = "weather"

    id = Column(Integer, primary_key=True, index=True)
    ts = Column(DateTime, unique=True, index=True, nullable=False)
    temp_c = Column(Float, nullable=False)

class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True, nullable=False)
    value = Column(String(255), nullable=False)
