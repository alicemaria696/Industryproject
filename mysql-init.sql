CREATE DATABASE IF NOT EXISTS assessment_system;
USE assessment_system;

-- Create devuser and grant permissions
CREATE USER IF NOT EXISTS 'devuser'@'%' IDENTIFIED BY 'dev@user1';
GRANT ALL PRIVILEGES ON assessment_system.* TO 'devuser'@'%';
FLUSH PRIVILEGES;

-- User table
CREATE TABLE IF NOT EXISTS user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reg_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL,
    role VARCHAR(10) NOT NULL
);

-- Auth tables
CREATE TABLE IF NOT EXISTS auth_identity (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(15) UNIQUE NOT NULL,
    reg_id VARCHAR(50) UNIQUE,
    name VARCHAR(100),
    email VARCHAR(100),
    department VARCHAR(100),
    role VARCHAR(10),
    status ENUM('ACTIVE','INACTIVE') DEFAULT 'ACTIVE'
);

-- Alter auth_identity table to add missing columns if they don't exist
SET @add_name := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'auth_identity'
           AND COLUMN_NAME = 'name') = 0,
        'ALTER TABLE auth_identity ADD COLUMN name VARCHAR(100);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_name;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_email := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'auth_identity'
           AND COLUMN_NAME = 'email') = 0,
        'ALTER TABLE auth_identity ADD COLUMN email VARCHAR(100);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_email;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_department := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'auth_identity'
           AND COLUMN_NAME = 'department') = 0,
        'ALTER TABLE auth_identity ADD COLUMN department VARCHAR(100);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_department;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS auth_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    auth_id INT,
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (auth_id) REFERENCES auth_identity(id)
);

CREATE TABLE IF NOT EXISTS auth_otp_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(15),
    otp VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teacher table
CREATE TABLE IF NOT EXISTS teacher (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reg_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    department VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL
);

-- Student table
CREATE TABLE IF NOT EXISTS student (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reg_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    department VARCHAR(100) NOT NULL,
    class_ VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL
);

-- Class table
CREATE TABLE IF NOT EXISTS class (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_id VARCHAR(100) NOT NULL UNIQUE
);

-- Subject table
CREATE TABLE IF NOT EXISTS subject (
    sub_id INT AUTO_INCREMENT PRIMARY KEY,
    s_name VARCHAR(100) NOT NULL,
    class_id INT NOT NULL,
    teacher_id INT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES class(id),
    FOREIGN KEY (teacher_id) REFERENCES teacher(id)
);

-- Assignment table
CREATE TABLE IF NOT EXISTS assignment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    time VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL,
    total_marks INT NOT NULL,
    questions TEXT,
    rubric TEXT,
    keywords TEXT,
    sub_id INT NOT NULL,
    FOREIGN KEY (sub_id) REFERENCES subject(sub_id)
);

-- Submission table
CREATE TABLE IF NOT EXISTS submission (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assignment_id INT,
    student_id VARCHAR(50) NOT NULL,
    subject_name VARCHAR(100) NOT NULL,
    submitted_document VARCHAR(200) NOT NULL,
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    marks INT,
    status VARCHAR(50),
    on_time BOOLEAN
);

-- Result table
CREATE TABLE IF NOT EXISTS result (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assignment_id INT NOT NULL,
    student_id VARCHAR(50) NOT NULL,
    subject_name VARCHAR(100) NOT NULL,
    file_name VARCHAR(200) NOT NULL,
    total_matches INT,
    marks INT,
    status VARCHAR(50),
    on_time BOOLEAN,
    evaluated_at DATETIME,
    FOREIGN KEY (assignment_id) REFERENCES assignment(id)
);

-- Script Assignment table
CREATE TABLE IF NOT EXISTS script_assignment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    deadline DATETIME NOT NULL,
    total_marks INT NOT NULL,
    questions TEXT,
    testcases JSON,
    rubric TEXT,
    compilation_time INT DEFAULT 0,
    function_name VARCHAR(100),
    function_signature TEXT,
    template_code TEXT,
    language VARCHAR(20) DEFAULT 'c',
    memory_limit INT DEFAULT 128000,
    time_limit INT DEFAULT 2,
    sub_id INT NOT NULL,
    FOREIGN KEY (sub_id) REFERENCES subject(sub_id)
);

-- Script Submission table
CREATE TABLE IF NOT EXISTS script_submission (
    id INT AUTO_INCREMENT PRIMARY KEY,
    script_assignment_id INT NOT NULL,
    student_id VARCHAR(50) NOT NULL,
    subject_name VARCHAR(100) NOT NULL,
    submitted_code TEXT NOT NULL,
    language_used VARCHAR(20),
    submission_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    compilation_status VARCHAR(20),
    compilation_error TEXT,
    compilation_time DECIMAL(10,3),
    total_test_cases INT DEFAULT 0,
    passed_test_cases INT DEFAULT 0,
    failed_test_cases INT DEFAULT 0,
    total_marks INT DEFAULT 0,
    marks_obtained INT DEFAULT 0,
    deadline_marks INT DEFAULT 0,
    compilation_marks INT DEFAULT 0,
    testcase_marks INT DEFAULT 0,
    final_status VARCHAR(20),
    is_on_time BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (script_assignment_id) REFERENCES script_assignment(id) ON DELETE CASCADE
);

-- Test Case Result table
CREATE TABLE IF NOT EXISTS test_case_result (
    id INT AUTO_INCREMENT PRIMARY KEY,
    submission_id INT NOT NULL,
    test_case_index INT NOT NULL,
    input_data TEXT,
    expected_output TEXT,
    actual_output TEXT,
    status VARCHAR(20),
    execution_time DECIMAL(10,3),
    memory_used INT,
    error_message TEXT,
    FOREIGN KEY (submission_id) REFERENCES script_submission(id) ON DELETE CASCADE
);

-- Live Test table
CREATE TABLE IF NOT EXISTS live_test (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    questions_text TEXT,
    question_file VARCHAR(200),
    duration_minutes INT NOT NULL,
    total_marks INT NOT NULL,
    evaluation_criteria TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sub_id INT NOT NULL,
    FOREIGN KEY (sub_id) REFERENCES subject(sub_id)
);

-- Live Test Attempt table
CREATE TABLE IF NOT EXISTS live_test_attempt (
    id INT AUTO_INCREMENT PRIMARY KEY,
    live_test_id INT NOT NULL,
    student_id VARCHAR(50) NOT NULL,
    started_at DATETIME,
    ended_at DATETIME,
    status VARCHAR(20) DEFAULT 'IN_PROGRESS',
    recording_path VARCHAR(200),
    focus_lost_count INT DEFAULT 0,
    proctor_events JSON,
    response_text TEXT,
    response_file VARCHAR(200),
    FOREIGN KEY (live_test_id) REFERENCES live_test(id) ON DELETE CASCADE
);

-- Create indexes (conditional for MySQL versions without IF NOT EXISTS)
SET @add_idx_script_submission_student := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'script_submission'
           AND INDEX_NAME = 'idx_script_submission_student') = 0,
        'CREATE INDEX idx_script_submission_student ON script_submission(student_id);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_idx_script_submission_student;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_idx_script_submission_assignment := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'script_submission'
           AND INDEX_NAME = 'idx_script_submission_assignment') = 0,
        'CREATE INDEX idx_script_submission_assignment ON script_submission(script_assignment_id);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_idx_script_submission_assignment;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_idx_test_case_result_submission := (
    SELECT IF(
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
         WHERE TABLE_SCHEMA = 'assessment_system'
           AND TABLE_NAME = 'test_case_result'
           AND INDEX_NAME = 'idx_test_case_result_submission') = 0,
        'CREATE INDEX idx_test_case_result_submission ON test_case_result(submission_id);',
        'SELECT 1;'
    )
);
PREPARE stmt FROM @add_idx_test_case_result_submission;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;