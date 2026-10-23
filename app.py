"""STRYKE - single-file version. Database, theme, and Streamlit app combined."""

# ========================= DATABASE / BUSINESS LOGIC =========================
"""STRYKE data layer: SQLite persistence + all business rules (server-side)."""
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _env(name, default):
    return os.environ.get(name, default)


DB_PATH = _env("STRYKE_DB", "stryke.db")
PRIVATE_DIR = _env("STRYKE_PRIVATE_DIR", "private_uploads")
COMMISSION_PCT = float(_env("STRYKE_COMMISSION_PCT", "15"))
FREE_CANCEL_HOURS = int(_env("STRYKE_FREE_CANCEL_HOURS", "24"))
MIN_YEARS = int(_env("STRYKE_MIN_YEARS", "5"))
MIN_NOTICE_HOURS = int(_env("STRYKE_MIN_NOTICE_HOURS", "2"))
ADMIN_EMAIL = _env("STRYKE_ADMIN_EMAIL", "").strip().lower()

SPORTS = ["Boxing", "MMA", "Muay Thai", "Kickboxing / K-1", "Brazilian Jiu-Jitsu", "Wrestling"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ACTIVE = ("pending", "confirmed")

# name -> (lat, lon, country, tz, currency)  real city-centre coordinates
CITIES = {
    "Oslo": (59.9139, 10.7522, "NO", "Europe/Oslo", "NOK"),
    "Bergen": (60.3913, 5.3221, "NO", "Europe/Oslo", "NOK"),
    "Trondheim": (63.4305, 10.3951, "NO", "Europe/Oslo", "NOK"),
    "Stavanger": (58.9700, 5.7331, "NO", "Europe/Oslo", "NOK"),
    "Stockholm": (59.3293, 18.0686, "SE", "Europe/Stockholm", "SEK"),
    "Copenhagen": (55.6761, 12.5683, "DK", "Europe/Copenhagen", "DKK"),
    "London": (51.5074, -0.1278, "GB", "Europe/London", "GBP"),
    "Berlin": (52.5200, 13.4050, "DE", "Europe/Berlin", "EUR"),
    "Amsterdam": (52.3676, 4.9041, "NL", "Europe/Amsterdam", "EUR"),
    "Madrid": (40.4168, -3.7038, "ES", "Europe/Madrid", "EUR"),
    "New York": (40.7128, -74.0060, "US", "America/New_York", "USD"),
    "Bangkok": (13.7563, 100.5018, "TH", "Asia/Bangkok", "THB"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL, suspended INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS coaches(
  id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), name TEXT NOT NULL,
  city TEXT NOT NULL, country TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
  tz TEXT NOT NULL, currency TEXT NOT NULL, price_cents INTEGER NOT NULL,
  session_minutes INTEGER NOT NULL DEFAULT 60, sports TEXT NOT NULL, languages TEXT NOT NULL,
  years_exp INTEGER NOT NULL DEFAULT 0, style TEXT DEFAULT '', bio TEXT DEFAULT '',
  record TEXT DEFAULT '', achievements TEXT DEFAULT '', qualifications TEXT DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0, verified_at TEXT, demo INTEGER NOT NULL DEFAULT 0,
  suspended INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS availability(
  id INTEGER PRIMARY KEY, coach_id INTEGER NOT NULL REFERENCES coaches(id),
  weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6), start_t TEXT NOT NULL, end_t TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY, coach_id INTEGER NOT NULL REFERENCES coaches(id),
  user_id INTEGER NOT NULL REFERENCES users(id), start_utc TEXT NOT NULL, end_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','confirmed','completed','cancelled','disputed','refunded')),
  price_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL, currency TEXT NOT NULL,
  payment_status TEXT NOT NULL DEFAULT 'unpaid', note TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_slot ON bookings(coach_id, start_utc)
  WHERE status IN ('pending','confirmed');
CREATE TABLE IF NOT EXISTS favourites(
  user_id INTEGER NOT NULL REFERENCES users(id), coach_id INTEGER NOT NULL REFERENCES coaches(id),
  PRIMARY KEY(user_id, coach_id));
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY, booking_id INTEGER UNIQUE NOT NULL REFERENCES bookings(id),
  coach_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), text TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), data TEXT NOT NULL,
  files TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL CHECK(status IN ('draft','submitted','under_review','needs_info','approved','rejected')),
  admin_note TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL, target TEXT, detail TEXT,
  created_at TEXT NOT NULL);
"""


class StrykeError(Exception):
    """User-presentable error."""


class SlotTaken(StrykeError):
