-- Initial Schema Baseline
-- Generated for WenHuaLineBot (Parent, Student, Group, Attendance, etc.)

CREATE TABLE IF NOT EXISTS parents (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    phone_number VARCHAR NOT NULL UNIQUE,
    line_user_id VARCHAR UNIQUE,
    is_bound BOOLEAN DEFAULT FALSE,
    bound_at TIMESTAMP
);
CREATE INDEX idx_parents_phone_number ON parents(phone_number);
CREATE INDEX idx_parents_line_user_id ON parents(line_user_id);

CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    student_number VARCHAR NOT NULL UNIQUE,
    card_number VARCHAR UNIQUE,
    parent_id INTEGER REFERENCES parents(id),
    group_id INTEGER REFERENCES groups(id),
    class_name VARCHAR,
    enrolled_subjects VARCHAR
);
CREATE INDEX idx_students_student_number ON students(student_number);
CREATE INDEX idx_students_card_number ON students(card_number);

CREATE TABLE IF NOT EXISTS class_schedules (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    day_of_week INTEGER NOT NULL,
    arrival_time TIME NOT NULL,
    departure_time TIME NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS notification_logs (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    notification_type VARCHAR NOT NULL,
    date VARCHAR NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendances (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    status VARCHAR NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_swipe_id VARCHAR
);
CREATE INDEX idx_attendances_client_swipe_id ON attendances(client_swipe_id);

CREATE TABLE IF NOT EXISTS otp_records (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR NOT NULL UNIQUE,
    otp VARCHAR NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    attempts INTEGER DEFAULT 0
);
CREATE INDEX idx_otp_records_phone_number ON otp_records(phone_number);

CREATE TABLE IF NOT EXISTS exam_scores (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    exam_name VARCHAR NOT NULL,
    subject VARCHAR,
    score VARCHAR NOT NULL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS timetable_items (
    id SERIAL PRIMARY KEY,
    group_name VARCHAR NOT NULL,
    time_slot VARCHAR NOT NULL,
    day_of_week VARCHAR NOT NULL,
    subject VARCHAR NOT NULL
);
CREATE INDEX idx_timetable_items_group_name ON timetable_items(group_name);
