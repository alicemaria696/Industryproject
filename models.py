from app import db
from flask_login import UserMixin
from datetime import datetime

# Table for Admins and Students
class User(db.Model, UserMixin):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'A' = Admin, 'S' = Student

class AuthIdentity(db.Model):
    __tablename__ = 'auth_identity'

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    reg_id = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    department = db.Column(db.String(100))
    role = db.Column(db.String(10))
    status = db.Column(db.Enum('ACTIVE', 'INACTIVE'), default='ACTIVE')

# Table for Teachers
class Teacher(db.Model):
    __tablename__ = 'teacher'
    
    id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    class_ = db.Column(db.String(100), nullable=False)  # matches DB column `class_`
    password = db.Column(db.String(100), nullable=False)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.String(100), unique=True, nullable=False)  # e.g., '4 MCA A'

class Subject(db.Model):
    sub_id = db.Column(db.Integer, primary_key=True)
    s_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)

class Assignment(db.Model):
    __tablename__ = 'assignment'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    time = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    total_marks = db.Column(db.Integer, nullable=False)
    sub_id = db.Column(db.Integer, db.ForeignKey('subject.sub_id'), nullable=False)

    questions = db.Column(db.Text)     # Added
    rubric = db.Column(db.Text)        # Added
    keywords = db.Column(db.Text)      # Added

class Submission(db.Model):
    __tablename__ = 'submission'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'))
    student_id = db.Column(db.String(50), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    submitted_document = db.Column(db.String(200), nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    marks = db.Column(db.Integer)
    status = db.Column(db.String(50))  # 'Pass' or 'Fail'
    on_time = db.Column(db.Boolean)
    
class Result(db.Model):
    __tablename__ = 'result'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    total_matches = db.Column(db.Integer)
    marks = db.Column(db.Integer)
    status = db.Column(db.String(50))  # 'Pass' or 'Fail'
    on_time = db.Column(db.Boolean)
    evaluated_at = db.Column(db.DateTime)
    assignment = db.relationship('Assignment', backref='results', lazy=True)
    
class ScriptAssignment(db.Model):
    __tablename__ = 'script_assignment'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=False)
    total_marks = db.Column(db.Integer, nullable=False)
    questions = db.Column(db.Text)
    
    # Enhanced fields for LeetCode-style implementation
    function_name = db.Column(db.String(100))  # Name of function student should implement
    function_signature = db.Column(db.Text)    # Complete function signature
    template_code = db.Column(db.Text)         # Template code with boilerplate
    language = db.Column(db.String(20), default='c')  # Programming language
    
    testcases = db.Column(db.JSON)             # Test cases with input/output
    rubric = db.Column(db.Text)
    compilation_time = db.Column(db.Integer)
    memory_limit = db.Column(db.Integer, default=128000)  # Memory limit in KB
    time_limit = db.Column(db.Integer, default=2)         # Time limit in seconds
    sub_id = db.Column(db.Integer, db.ForeignKey('subject.sub_id'), nullable=False)

# New model to track individual test case results
class TestCaseResult(db.Model):
    __tablename__ = 'test_case_result'
    
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('script_submission.id'), nullable=False)
    test_case_index = db.Column(db.Integer, nullable=False)  # Which test case (0, 1, 2...)
    input_data = db.Column(db.Text)
    expected_output = db.Column(db.Text)
    actual_output = db.Column(db.Text)
    status = db.Column(db.String(20))  # 'PASSED', 'FAILED', 'ERROR', 'TIMEOUT'
    execution_time = db.Column(db.Float)  # Execution time in seconds
    memory_used = db.Column(db.Integer)   # Memory used in KB
    error_message = db.Column(db.Text)    # Error message if any

# New model for script submissions with detailed results
class ScriptSubmission(db.Model):
    __tablename__ = 'script_submission'
    
    id = db.Column(db.Integer, primary_key=True)
    script_assignment_id = db.Column(db.Integer, db.ForeignKey('script_assignment.id'), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    
    # Submission details
    submitted_code = db.Column(db.Text, nullable=False)
    language_used = db.Column(db.String(20))
    submission_time = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Compilation results
    compilation_status = db.Column(db.String(20))  # 'SUCCESS', 'FAILED'
    compilation_error = db.Column(db.Text)
    compilation_time = db.Column(db.Float)
    
    # Test case results summary
    total_test_cases = db.Column(db.Integer, default=0)
    passed_test_cases = db.Column(db.Integer, default=0)
    failed_test_cases = db.Column(db.Integer, default=0)
    
    # Scoring
    total_marks = db.Column(db.Integer, default=0)
    marks_obtained = db.Column(db.Integer, default=0)
    
    # Rubric-based scoring
    deadline_marks = db.Column(db.Integer, default=0)      # Marks for meeting deadline
    compilation_marks = db.Column(db.Integer, default=0)   # Marks for successful compilation
    testcase_marks = db.Column(db.Integer, default=0)      # Marks for passing test cases
    
    # Final evaluation
    final_status = db.Column(db.String(20))  # 'PASS', 'FAIL'
    is_on_time = db.Column(db.Boolean, default=False)
    
    # Relationship to test case results
    test_results = db.relationship('TestCaseResult', backref='submission', lazy=True, cascade='all, delete-orphan')
    script_assignment = db.relationship('ScriptAssignment', backref='submissions', lazy=True)

class LiveTest(db.Model):
    __tablename__ = 'live_test'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    questions_text = db.Column(db.Text)
    question_file = db.Column(db.String(200))
    duration_minutes = db.Column(db.Integer, nullable=False)
    total_marks = db.Column(db.Integer, nullable=False)
    evaluation_criteria = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sub_id = db.Column(db.Integer, db.ForeignKey('subject.sub_id'), nullable=False)

class LiveTestAttempt(db.Model):
    __tablename__ = 'live_test_attempt'

    id = db.Column(db.Integer, primary_key=True)
    live_test_id = db.Column(db.Integer, db.ForeignKey('live_test.id'), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='IN_PROGRESS')
    recording_path = db.Column(db.String(200))
    focus_lost_count = db.Column(db.Integer, default=0)
    proctor_events = db.Column(db.JSON)
    response_text = db.Column(db.Text)
    response_file = db.Column(db.String(200))

    live_test = db.relationship('LiveTest', backref='attempts', lazy=True)