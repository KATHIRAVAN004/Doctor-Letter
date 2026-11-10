"""PostgreSQL storage for Doctor Letters."""

import os
import secrets
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

import s3_store


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS doctors (
        mobile VARCHAR(10) PRIMARY KEY,
        name TEXT NOT NULL,
        qualification TEXT,
        reg_no TEXT,
        clinic TEXT,
        address TEXT
    );

    ALTER TABLE doctors
    ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

    CREATE TABLE IF NOT EXISTS letters (
        id VARCHAR(32) PRIMARY KEY,
        doctor_mobile VARCHAR(10) NOT NULL REFERENCES doctors(mobile),
        type TEXT NOT NULL,
        type_label TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        final_html TEXT,
        s3_key TEXT,
        created_at TIMESTAMPTZ NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id BIGSERIAL PRIMARY KEY,
        doctor_mobile VARCHAR(10) NOT NULL,
        letter_id VARCHAR(32) NOT NULL,
        event TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS share_links (
        token TEXT PRIMARY KEY,
        doctor_mobile VARCHAR(10) NOT NULL REFERENCES doctors(mobile),
        letter_id VARCHAR(32) NOT NULL REFERENCES letters(id),
        expires_at TIMESTAMPTZ NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_letters_doctor
    ON letters(doctor_mobile);

    CREATE INDEX IF NOT EXISTS idx_letters_created
    ON letters(created_at DESC);
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def get_doctor(mobile):
    if not mobile:
        return None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM doctors WHERE mobile = %s",
                (mobile,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def save_doctor(mobile, profile):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO doctors
                (mobile, name, qualification, reg_no, clinic, address)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (mobile) DO UPDATE SET
                    name = EXCLUDED.name,
                    qualification = EXCLUDED.qualification,
                    reg_no = EXCLUDED.reg_no,
                    clinic = EXCLUDED.clinic,
                    address = EXCLUDED.address
            """, (
                mobile,
                profile.get("name", ""),
                profile.get("qualification", ""),
                profile.get("reg_no", ""),
                profile.get("clinic", ""),
                profile.get("address", "")
            ))

def set_doctor_active(mobile, active):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE doctors SET active = %s WHERE mobile = %s",
                (bool(active), mobile)
            )

def audit(mobile, letter_id, event):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_logs
                (doctor_mobile, letter_id, event)
                VALUES (%s, %s, %s)
            """, (mobile, letter_id, event))


def save_letter(mobile, letter, final_html):
    s3_key = s3_store.upload_html(mobile, letter["id"], final_html)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO letters
                (id, doctor_mobile, type, type_label, title,
                 body, s3_key, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                letter["id"],
                mobile,
                letter["type"],
                letter["type_label"],
                letter["title"],
                letter["body"],
                s3_key,
                letter["created_at"]
            ))

            cur.execute("""
                INSERT INTO audit_logs
                (doctor_mobile, letter_id, event)
                VALUES (%s, %s, %s)
            """, (mobile, letter["id"], "created"))


def list_letters(mobile, limit=100):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, type, type_label, title, body,
                       doctor_mobile, created_at
                FROM letters
                WHERE doctor_mobile = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (mobile, limit))

            rows = cur.fetchall()
            result = []

            for row in rows:
                item = dict(row)
                item["created_at"] = item["created_at"].isoformat()
                result.append(item)

            return result


def get_letter(mobile, letter_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, type, type_label, title, body,
                       doctor_mobile, created_at
                FROM letters
                WHERE doctor_mobile = %s AND id = %s
            """, (mobile, letter_id))

            row = cur.fetchone()

            if not row:
                return None

            item = dict(row)
            item["created_at"] = item["created_at"].isoformat()
            return item
def get_letter_verification(letter_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id, l.type_label, l.created_at,
                       d.name, d.qualification, d.reg_no,
                       d.clinic, d.address, d.active
                FROM letters l
                JOIN doctors d ON d.mobile = l.doctor_mobile
                WHERE l.id = %s
            """, (letter_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def _load_html(row):
    if not row:
        return None
    if row["s3_key"]:
        return s3_store.download_html(row["s3_key"])
    return row["final_html"]


def get_letter_html(mobile, letter_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s3_key, final_html FROM letters
                WHERE doctor_mobile = %s AND id = %s
            """, (mobile, letter_id))
            return _load_html(cur.fetchone())


def create_share_token(mobile, letter_id, days=7):
    token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(days=days)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO share_links
                (token, doctor_mobile, letter_id, expires_at)
                SELECT %s, doctor_mobile, id, %s
                FROM letters
                WHERE doctor_mobile = %s AND id = %s
            """, (token, expires, mobile, letter_id))

            if cur.rowcount == 0:
                raise ValueError("Letter not found")

            cur.execute("""
                INSERT INTO audit_logs
                (doctor_mobile, letter_id, event)
                VALUES (%s, %s, %s)
            """, (mobile, letter_id, "shared"))

    return token


def get_shared_html(token):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.s3_key, l.final_html
                FROM share_links s
                JOIN letters l ON l.id = s.letter_id
                WHERE s.token = %s
                AND s.expires_at > NOW()
            """, (token,))
            return _load_html(cur.fetchone())