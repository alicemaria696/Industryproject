from flask import json, render_template, request, redirect, url_for, flash, session, send_from_directory, make_response
import json
import time
import requests
from app import app, db
from app.models import (Teacher, User, Student, Class, Subject, Assignment, 
                       Submission, Result, ScriptAssignment, ScriptSubmission, 
                       TestCaseResult, AuthIdentity, LiveTest, LiveTestAttempt)
from datetime import datetime,timedelta
import csv
from io import TextIOWrapper, StringIO
import os
from werkzeug.utils import secure_filename
from flask import jsonify
from PyPDF2 import PdfReader
import re
import docx2txt
from flask import request, jsonify, session, redirect
import requests
import jwt

JWT_SECRET = "ZEROTRUSTSECRETKEY"


def extract_live_test_score(attempt):
    """Return a numeric live-test score from persisted attempt data."""
    if not attempt:
        return 0.0

    if attempt.response_text:
        try:
            parsed_response = json.loads(attempt.response_text)
            if isinstance(parsed_response, dict):
                score_val = parsed_response.get('score')
                if score_val is not None:
                    return float(score_val)
        except Exception:
            # Some legacy rows may not contain JSON. Fall back to proctor events.
            pass

    if isinstance(attempt.proctor_events, list):
        for event in reversed(attempt.proctor_events):
            if not isinstance(event, dict):
                continue
            score_val = event.get('score')
            if score_val is not None:
                try:
                    return float(score_val)
                except Exception:
                    continue

    return 0.0


def calculate_pass_fail_status(marks_obtained, total_marks, pass_label='Pass', fail_label='Fail'):
    """Use a simple 50% threshold so manual edits stay consistent with auto-evaluation."""
    if int(total_marks or 0) <= 0:
        return fail_label
    return pass_label if float(marks_obtained or 0) >= (0.5 * int(total_marks or 0)) else fail_label


def resolve_teacher_id():
    """Support both legacy teacher sessions and OTP-based teacher logins."""
    teacher_id = session.get('teacher_id')
    if teacher_id:
        return teacher_id

    reg_id = session.get('reg_id')
    if not reg_id:
        return None

    teacher = Teacher.query.filter_by(reg_id=reg_id).first()
    if not teacher:
        return None

    session['teacher_id'] = teacher.id
    return teacher.id

"""@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        reg_id = request.form['reg_id']
        password = request.form['password']

        user = User.query.filter_by(reg_id=reg_id, password=password).first()
        if user and user.role == 'A':
            return redirect(url_for('admin_dashboard'))

        teacher = Teacher.query.filter_by(reg_id=reg_id, password=password).first()
        if teacher:
            session['teacher_id'] = teacher.id
            return redirect(url_for('home'))

        student = Student.query.filter_by(reg_id=reg_id, password=password).first()
        if student:
            session['reg_id'] = student.reg_id
            return redirect(url_for('student_dashboard'))

        flash("Invalid credentials. Please try again.")
        return redirect(url_for('login_page'))

    return render_template('login.html')"""
@app.route('/', methods=['GET'])
def login_page():
    return render_template("login.html")

@app.route('/register', methods=['POST'])
def register():
    """Proxy endpoint for user registration"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required_fields = ['reg_id', 'phone', 'password', 'role', 'name', 'email', 'department']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        resp = requests.post(
            "http://auth-registration:5001/register",
            json=data,
            timeout=5
        )
        
        if resp.status_code != 200:
            try:
                error_msg = resp.json().get("message", "Registration failed") if resp.text else "Registration failed"
            except:
                error_msg = "Registration failed"
            return jsonify({"error": error_msg}), resp.status_code
        
        # If student role and successful auth registration, create/update student record
        if data.get('role') == 'STUDENT':
            reg_id = data.get('reg_id')
            name = data.get('name')
            email = data.get('email')
            department = data.get('department')
            password = data.get('password')
            
            student = Student.query.filter_by(reg_id=reg_id).first()
            if student:
                # Update existing student with registration data
                student.name = name
                student.email = email
                student.department = department
            else:
                # Create new student with default unassigned class
                student = Student(
                    reg_id=reg_id,
                    name=name,
                    email=email,
                    department=department,
                    class_='Unassigned',
                    password=password
                )
                db.session.add(student)
            
            db.session.commit()
        
        return resp.json(), 200
    except requests.exceptions.ConnectionError:
        print(f"✗ Auth-registration service unreachable")
        return jsonify({"error": "Registration service unavailable. Please try again."}), 503
    except Exception as e:
        print(f"✗ Registration error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/send-otp', methods=['POST'])
def send_otp():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        phone = data.get("phone", "").strip()
        if not phone:
            return jsonify({"error": "Phone number is required"}), 400
        
        resp = requests.post(
            "http://auth-otp:5002/send-otp",
            json={"phone": phone},
            timeout=5
        )
        
        if resp.status_code != 200:
            try:
                error_msg = resp.json().get("error", "Failed to send OTP") if resp.text else "Failed to send OTP"
            except:
                error_msg = "Failed to send OTP"
            return jsonify({"error": error_msg}), resp.status_code
        
        return resp.json(), 200
    except requests.exceptions.ConnectionError:
        print(f"✗ OTP service unreachable")
        return jsonify({"error": "OTP service unavailable. Please try again."}), 503
    except Exception as e:
        print(f"✗ OTP send error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/verify-login', methods=['POST'])
def verify_login():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        phone = data.get("phone", "").strip()
        otp = data.get("otp", "").strip()
        
        if not phone or not otp:
            return jsonify({"error": "Phone and OTP are required"}), 400

        resp = requests.post(
            "http://auth-otp:5002/verify-otp",
            json={"phone": phone, "otp": otp},
            timeout=5
        )

        if resp.status_code != 200:
            try:
                error_msg = resp.json().get("error", "Invalid OTP") if resp.text else "Invalid OTP"
            except:
                error_msg = "Invalid OTP"
            return jsonify({"error": error_msg}), resp.status_code

        token_data = resp.json()
        token = token_data.get("token")
        
        if not token:
            return jsonify({"error": "No token received from auth service"}), 500
        
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.InvalidTokenError as je:
            print(f"✗ JWT decode error: {je}")
            return jsonify({"error": "Invalid token received"}), 401

        session.permanent = True
        session["reg_id"] = payload.get("reg_id")
        session["role"] = payload.get("role")
        session["phone"] = payload.get("phone")

        role = payload.get("role", "STUDENT")
        if role == "ADMIN":
            return jsonify({"redirect": "/admin"}), 200
        elif role == "TEACHER":
            return jsonify({"redirect": "/teacher"}), 200
        else:
            return jsonify({"redirect": "/student"}), 200
    
    except requests.exceptions.ConnectionError:
        print(f"✗ Auth service unreachable")
        return jsonify({"error": "Auth service unavailable. Please try again."}), 503
    except Exception as e:
        print(f"✗ OTP verification error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/admin')
def admin():
    """Redirect to admin dashboard"""
    return redirect(url_for('admin_dashboard'))


@app.route('/teacher')
def teacher():
    """Redirect to teacher home"""
    return redirect(url_for('home'))


@app.route('/student')
def student():
    """Redirect to student dashboard"""
    return redirect(url_for('student_dashboard'))


@app.route('/admindashboard')
def admin_dashboard():
    return render_template('admindashboard.html')

@app.route('/assign_class', methods=['GET', 'POST'])
def assign_class():
    classes = Class.query.all()

    if request.method == 'POST':
        reg_id = request.form.get('reg_id', '').strip()
        class_id = request.form.get('class_id', '').strip()

        if not reg_id or not class_id:
            flash('Registration ID and class are required.')
            return redirect(url_for('assign_class'))

        identity = AuthIdentity.query.filter_by(reg_id=reg_id).first()
        if not identity:
            flash('Selected Registration ID not found in auth_identity.')
            return redirect(url_for('assign_class'))

        cls = Class.query.filter_by(id=class_id).first()
        if not cls:
            flash('Selected class not found.')
            return redirect(url_for('assign_class'))

        student = Student.query.filter_by(reg_id=reg_id).first()
        if student:
            # Just update class, keep existing name/email/department
            student.class_ = cls.class_id
        else:
            # Student doesn't exist in student table yet - they only registered in auth_identity
            # Create with default values - admin should use "Add Student" for full details
            student = Student(
                reg_id=reg_id,
                name=reg_id,  # Temporary - admin can update via Add Student
                email=f"{reg_id}@student.chrsituniversity.in",
                department='General',
                class_=cls.class_id,
                password='default_password'
            )
            db.session.add(student)

        db.session.commit()
        flash('Student assigned to class successfully.')
        return redirect(url_for('assign_class'))

    # Get all identities to populate dropdown
    identities = AuthIdentity.query.filter(
        AuthIdentity.role == 'STUDENT',
        AuthIdentity.status == 'ACTIVE'
    ).all()
    
    # Get all students for display table (these have proper data)
    students = Student.query.all()

    return render_template(
        'assign_class.html',
        identities=identities,
        students=students,
        classes=classes
    )

@app.route('/home')
def home():
    classes = Class.query.all()
    return render_template('home.html', classes=classes)

@app.route('/add_teacher', methods=['GET', 'POST'])
def add_teacher():
    if request.method == 'POST':
        reg_id = request.form['reg_id']
        name = request.form['name']
        email = request.form['email']
        department = request.form['department']
        password = request.form['password']

        new_teacher = Teacher(reg_id=reg_id, name=name, email=email, department=department, password=password)
        db.session.add(new_teacher)
        db.session.commit()
        flash('Teacher added successfully!')
        return redirect(url_for('admin_dashboard'))

    return render_template('add_teacher.html')

@app.route('/upload_csv', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'POST':
        file = request.files['file']
        stream = TextIOWrapper(file.stream, encoding='utf-8')
        csv_input = csv.reader(stream)
        next(csv_input)

        for row in csv_input:
            reg_id, name, email, department, password = row
            teacher = Teacher(reg_id=reg_id, name=name, email=email, department=department, password=password)
            db.session.add(teacher)

        db.session.commit()
        flash('CSV uploaded and teachers added.')
        return redirect(url_for('admin_dashboard'))

    return render_template('upload_csv.html')

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        reg_id = request.form['reg_id']
        name = request.form['name']
        email = request.form['email']
        department = request.form['department']
        class_ = request.form['class_']
        password = request.form['password']

        new_student = Student(reg_id=reg_id, name=name, email=email, department=department, class_=class_, password=password)
        db.session.add(new_student)
        db.session.commit()
        flash('Student added successfully!')
        return redirect(url_for('admin_dashboard'))

    # Get all classes for the dropdown
    classes = Class.query.all()
    return render_template('add_student.html', classes=classes)
@app.route('/upload_student_csv', methods=['GET', 'POST'])
def upload_student_csv():
    if request.method == 'POST':
        file = request.files['file']
        stream = TextIOWrapper(file.stream, encoding='utf-8')
        csv_input = csv.reader(stream)
        next(csv_input)

        for row in csv_input:
            reg_id, name, email, department, class_, password = row
            student = Student(reg_id=reg_id, name=name, email=email, department=department, class_=class_, password=password)
            db.session.add(student)

        db.session.commit()
        flash('CSV uploaded and students added.')
        return redirect(url_for('admin_dashboard'))

    return render_template('upload_student_csv.html')

@app.route('/view_teachers')
def view_teachers():
    teachers = Teacher.query.all()
    return render_template('view_teachers.html', teachers=teachers)

@app.route('/view_students')
def view_students():
    students = Student.query.all()
    return render_template('view_students.html', students=students)

@app.route('/add_class', methods=['GET', 'POST'])
def add_class():
    if request.method == 'POST':
        class_id = request.form['class_id']
        new_class = Class(class_id=class_id)
        db.session.add(new_class)
        db.session.commit()
        flash('Class added successfully!')
        return redirect(url_for('view_classes'))

    return render_template('add_class.html')

@app.route('/view_classes')
def view_classes():
    classes = Class.query.all()
    return render_template('view_classes.html', classes=classes)

@app.route('/delete_class/<int:id>', methods=['POST'])
def delete_class(id):
    class_to_delete = Class.query.get_or_404(id)
    db.session.delete(class_to_delete)
    db.session.commit()
    flash('Class deleted successfully.')
    return redirect(url_for('view_classes'))

@app.route('/class/<int:class_id>/add_subject', methods=['GET', 'POST'])
def add_subject(class_id):
    teacher_id = session.get('teacher_id')
    if not teacher_id:
        reg_id = session.get('reg_id')
        if reg_id:
            teacher = Teacher.query.filter_by(reg_id=reg_id).first()
            if teacher:
                teacher_id = teacher.id
                session['teacher_id'] = teacher_id
    if request.method == 'POST':
        s_name = request.form.get('s_name', '').strip()
        if not teacher_id:
            flash('Teacher session not found. Please log in again.')
            return redirect(url_for('home'))
        if not s_name:
            flash('Subject name is required.')
            return redirect(url_for('add_subject', class_id=class_id))
        new_subject = Subject(s_name=s_name, class_id=class_id, teacher_id=teacher_id)
        db.session.add(new_subject)
        db.session.commit()
        return redirect(url_for('class_dashboard', class_id=class_id))
    return render_template('add_subject.html', class_id=class_id)

@app.route('/class/<int:class_id>/subjects')
def class_dashboard(class_id):
    subjects = Subject.query.filter_by(class_id=class_id).all()
    return render_template('class_dashboard.html', class_id=class_id, subjects=subjects)

@app.route("/class/<int:class_id>/students")
def view_students_by_class(class_id):
    # Fetch class info from Class model
    cls = Class.query.filter_by(id=class_id).first()
    if not cls:
        return "Class not found", 404

    #  Fix here: filter using class_ (string), not class_id
    students = Student.query.filter_by(class_=cls.class_id).all()

    # Fetch subjects for sidebar
    subjects = Subject.query.filter_by(class_id=class_id).all()

    return render_template(
        "students_by_class.html",
        class_id=class_id,
        class_name=cls.class_id,   # ex: "4 MCA A"
        students=students,
        subjects=subjects
    )



@app.route('/subject/<int:sub_id>/assignments', methods=['GET', 'POST'])
def subject_assignments(sub_id):
    subject = Subject.query.get_or_404(sub_id)

    if request.method == 'POST':
        title = request.form['title']
        time = request.form['time']
        total_marks = request.form['total_marks']
        type_ = request.form['type']

        new_assignment = Assignment(
            title=title,
            time=time,
            total_marks=int(total_marks),
            type=type_,
            sub_id=sub_id
        )
        db.session.add(new_assignment)
        db.session.commit()
        flash("Assignment added.")
        return redirect(url_for('subject_assignments', sub_id=sub_id))

    # ✅ fetch all subjects for this class (so sidebar has them)
    subjects = Subject.query.filter_by(class_id=subject.class_id).all()

    assignments = Assignment.query.filter_by(sub_id=sub_id).all()
    script_assignments = ScriptAssignment.query.filter_by(sub_id=sub_id).all()
    live_tests = LiveTest.query.filter_by(sub_id=sub_id).all()

    return render_template(
        "assignment_dashboard.html",
        subject=subject,
        subjects=subjects,              
        assignments=assignments,
        script_assignments=script_assignments,
        live_tests=live_tests
    )


@app.route('/subject/<int:sub_id>/assignments/create', methods=['GET', 'POST'])
def create_assignment(sub_id):
    subject = Subject.query.get_or_404(sub_id)
    if request.method == 'POST':
        title = request.form['title']
        type_ = request.form['type']
        time = request.form['time']
        total_marks = request.form['total_marks']
        questions = request.form.get('questions')
        rubric = request.form.get('rubric')
        keywords = request.form.get('keywords')

        new_assignment = Assignment(
            title=title,
            type=type_,
            time=time,
            total_marks=total_marks,
            sub_id=sub_id,
            questions=questions,
            rubric=rubric,
            keywords=keywords
        )
        db.session.add(new_assignment)
        db.session.commit()
        flash('Assignment created successfully!')
        return redirect(url_for('subject_assignments', sub_id=sub_id))

    return render_template('assignment_creation.html', subject=subject)

@app.route('/subject/<int:sub_id>/live_tests/create', methods=['GET', 'POST'])
def create_live_test(sub_id):
    subject = Subject.query.get_or_404(sub_id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        duration_minutes = int(request.form.get('duration_minutes', 0) or 0)
        total_marks = int(request.form.get('total_marks', 0) or 0)
        mcq_payload_raw = request.form.get('mcq_payload', '[]').strip()
        evaluation_criteria = request.form.get('evaluation_criteria', '').strip()

        if not title or duration_minutes <= 0 or total_marks <= 0:
            flash('Title, duration, and total marks are required.')
            return redirect(url_for('create_live_test', sub_id=sub_id))

        try:
            mcq_payload = json.loads(mcq_payload_raw) if mcq_payload_raw else []
        except Exception:
            flash('Invalid MCQ payload. Please re-add the questions.')
            return redirect(url_for('create_live_test', sub_id=sub_id))

        if not isinstance(mcq_payload, list) or len(mcq_payload) == 0:
            flash('Please add at least one MCQ question.')
            return redirect(url_for('create_live_test', sub_id=sub_id))

        if len(mcq_payload) > 40:
            flash('Maximum 40 MCQ questions are allowed.')
            return redirect(url_for('create_live_test', sub_id=sub_id))

        normalized_questions = []
        for index, question in enumerate(mcq_payload, start=1):
            prompt = str(question.get('question', '')).strip()
            options = question.get('options', [])
            correct_index = question.get('correct_index', None)

            if not prompt:
                flash(f'Question {index} is empty.')
                return redirect(url_for('create_live_test', sub_id=sub_id))
            if not isinstance(options, list) or len(options) != 4:
                flash(f'Question {index} must have exactly 4 options.')
                return redirect(url_for('create_live_test', sub_id=sub_id))

            cleaned_options = [str(opt).strip() for opt in options]
            if any(not opt for opt in cleaned_options):
                flash(f'Question {index} has empty options.')
                return redirect(url_for('create_live_test', sub_id=sub_id))

            if correct_index is None or int(correct_index) < 0 or int(correct_index) > 3:
                flash(f'Question {index} has an invalid correct option.')
                return redirect(url_for('create_live_test', sub_id=sub_id))

            normalized_questions.append({
                'question': prompt,
                'options': cleaned_options,
                'correct_index': int(correct_index)
            })

        live_test = LiveTest(
            title=title,
            questions_text=json.dumps(normalized_questions),
            question_file=None,
            duration_minutes=duration_minutes,
            total_marks=total_marks,
            evaluation_criteria=evaluation_criteria,
            sub_id=sub_id
        )
        db.session.add(live_test)
        db.session.commit()

        flash('Live test created successfully!')
        return redirect(url_for('subject_assignments', sub_id=sub_id))

    return render_template('live_test_creation.html', subject=subject)

@app.route('/live_test/<int:test_id>/start')
def live_test_start(test_id):
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return redirect(url_for('login_page'))

    test = LiveTest.query.get_or_404(test_id)

    mcq_questions = []
    if test.questions_text:
        try:
            parsed_questions = json.loads(test.questions_text)
            if isinstance(parsed_questions, list):
                mcq_questions = parsed_questions
        except Exception:
            mcq_questions = []

    return render_template('live_test_start.html', test=test, mcq_questions=mcq_questions)

@app.route('/live_test/<int:test_id>/begin', methods=['POST'])
def live_test_begin(test_id):
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return jsonify({'error': 'Not authenticated'}), 401

    test = LiveTest.query.get_or_404(test_id)

    # Reuse an existing attempt so that a page-refresh doesn't orphan the recording
    existing = (
        LiveTestAttempt.query
        .filter_by(live_test_id=test_id, student_id=student_reg_id)
        .order_by(LiveTestAttempt.started_at.desc())
        .first()
    )
    if existing:
        if existing.status in ('SUBMITTED', 'TIME_EXPIRED'):
            return jsonify({'error': 'You have already completed this test'}), 409
        # Return the same attempt_id so the recording stays attached
        end_time = existing.started_at + timedelta(minutes=test.duration_minutes)
        return jsonify({'attempt_id': existing.id, 'end_time': f"{end_time.isoformat()}Z"})

    attempt = LiveTestAttempt(
        live_test_id=test.id,
        student_id=student_reg_id,
        started_at=datetime.utcnow(),
        status='IN_PROGRESS'
    )
    db.session.add(attempt)
    db.session.commit()

    end_time = attempt.started_at + timedelta(minutes=test.duration_minutes)
    return jsonify({'attempt_id': attempt.id, 'end_time': f"{end_time.isoformat()}Z"})

@app.route('/live_test/<int:test_id>/upload_recording', methods=['POST'])
def live_test_upload_recording(test_id):
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return jsonify({'error': 'Not authenticated'}), 401

    attempt_id = request.form.get('attempt_id')
    recording = request.files.get('recording')
    if not attempt_id or not recording:
        return jsonify({'error': 'Missing attempt or recording'}), 400

    attempt = LiveTestAttempt.query.filter_by(
        id=attempt_id,
        live_test_id=test_id,
        student_id=student_reg_id
    ).first()
    if not attempt:
        return jsonify({'error': 'Attempt not found'}), 404

    recordings_dir = os.path.join(os.getcwd(), 'uploads', 'live_tests', 'recordings')
    os.makedirs(recordings_dir, exist_ok=True)
    filename = secure_filename(
        f"live_test_{test_id}_attempt_{attempt_id}_{int(time.time())}.webm"
    )
    recording.save(os.path.join(recordings_dir, filename))

    attempt.recording_path = filename
    db.session.commit()

    return jsonify({'status': 'ok', 'filename': filename})

@app.route('/live_test/<int:test_id>/submit', methods=['POST'])
def live_test_submit(test_id):
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return jsonify({'error': 'Not authenticated'}), 401

    attempt_id = request.form.get('attempt_id')
    attempt = LiveTestAttempt.query.filter_by(
        id=attempt_id,
        live_test_id=test_id,
        student_id=student_reg_id
    ).first()
    if not attempt:
        return jsonify({'error': 'Attempt not found'}), 404

    answers_json_raw = request.form.get('answers_json', '[]')
    focus_lost_count = int(request.form.get('focus_lost_count', 0) or 0)
    status = request.form.get('status', 'SUBMITTED')
    proctor_events_raw = request.form.get('proctor_events', '[]')


    try:
        proctor_events = json.loads(proctor_events_raw)
    except Exception:
        proctor_events = []

    try:
        submitted_answers = json.loads(answers_json_raw) if answers_json_raw else []
    except Exception:
        submitted_answers = []

    test = LiveTest.query.get_or_404(test_id)
    question_bank = []
    try:
        parsed = json.loads(test.questions_text) if test.questions_text else []
        if isinstance(parsed, list):
            question_bank = parsed
    except Exception:
        question_bank = []

    total_questions = len(question_bank)
    correct_answers = 0

    if isinstance(submitted_answers, list) and total_questions > 0:
        for idx, question in enumerate(question_bank):
            correct_idx = question.get('correct_index')
            selected_idx = submitted_answers[idx] if idx < len(submitted_answers) else None
            try:
                if selected_idx is not None and int(selected_idx) == int(correct_idx):
                    correct_answers += 1
            except Exception:
                continue

    score = 0
    if total_questions > 0:
        score = round((correct_answers / total_questions) * int(test.total_marks or 0), 2)

    if not isinstance(proctor_events, list):
        proctor_events = []
    proctor_events.append({
        'type': 'evaluation',
        'score': score,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'test_total_marks': int(test.total_marks or 0)
    })

    attempt.response_text = json.dumps({
        'answers': submitted_answers,
        'score': score,
        'correct_answers': correct_answers,
        'total_questions': total_questions
    })
    attempt.response_file = None
    attempt.focus_lost_count = focus_lost_count
    attempt.proctor_events = proctor_events
    attempt.status = status
    attempt.ended_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'score': score,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'total_marks': int(test.total_marks or 0)
    })

@app.route('/live_test/<int:test_id>/attempts')
def live_test_attempts(test_id):
    test = LiveTest.query.get_or_404(test_id)
    attempts = LiveTestAttempt.query.filter_by(live_test_id=test_id)
    attempts = attempts.order_by(LiveTestAttempt.started_at.desc()).all()

    for attempt in attempts:
        attempt.score_display = 'N/A'
        try:
            extracted_score = extract_live_test_score(attempt)
            if extracted_score.is_integer():
                attempt.score_display = str(int(extracted_score))
            else:
                attempt.score_display = str(round(extracted_score, 2))
        except Exception:
            attempt.score_display = 'N/A'

    return render_template('live_test_attempts.html', test=test, attempts=attempts)

@app.route('/live_test/recordings/<path:filename>')
def live_test_recording(filename):
    # Only teachers (no student reg_id check — role-based gate done at template level)
    # ?download=1  forces browser save-as, omitting it streams inline
    as_attachment = request.args.get('download') == '1'
    recordings_dir = os.path.join(os.getcwd(), 'uploads', 'live_tests', 'recordings')
    return send_from_directory(recordings_dir, filename, as_attachment=as_attachment)

@app.route('/live_test/<int:test_id>/recordings')
def live_test_recordings(test_id):
    """Teacher view: one recording card per student (their latest completed attempt)."""
    teacher_id = session.get('teacher_id')
    if not teacher_id:
        return redirect(url_for('login_page'))
    test = LiveTest.query.get_or_404(test_id)

    # Fetch all attempts newest-first, then keep only the best (completed) attempt
    # per student so the teacher sees exactly one card per student.
    all_attempts = (
        LiveTestAttempt.query
        .filter_by(live_test_id=test_id)
        .order_by(LiveTestAttempt.started_at.desc())
        .all()
    )
    DONE = {'SUBMITTED', 'TIME_EXPIRED'}
    best = {}          # student_id -> attempt
    for a in all_attempts:
        sid = a.student_id
        if sid not in best:
            best[sid] = a   # first seen = newest; prefer completed over in-progress
        elif a.status in DONE and best[sid].status not in DONE:
            best[sid] = a   # upgrade: replace an in-progress placeholder with a completed one

    attempts = sorted(best.values(), key=lambda a: a.student_id)
    return render_template('live_test_recordings.html', test=test, attempts=attempts)

@app.route('/live_test/questions/<path:filename>')
def live_test_question_file(filename):
    questions_dir = os.path.join(os.getcwd(), 'uploads', 'live_tests', 'questions')
    return send_from_directory(questions_dir, filename, as_attachment=True)

@app.route('/live_test/responses/<path:filename>')
def live_test_response_file(filename):
    responses_dir = os.path.join(os.getcwd(), 'uploads', 'live_tests', 'responses')
    return send_from_directory(responses_dir, filename, as_attachment=True)

@app.route('/submission/<path:filename>')
def view_submission_file(filename):
    """Serve a student theory submission file; ?download=1 forces save-as."""
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    as_attachment = request.args.get('download') == '1'
    return send_from_directory(uploads_dir, filename, as_attachment=as_attachment)

@app.route('/studentdashboard')
def student_dashboard():
    """Render student dashboard - assignments will be loaded via AJAX"""
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return redirect(url_for('login_page'))
    
    student = Student.query.filter_by(reg_id=student_reg_id).first()
    if not student:
        flash("Student not found.")
        return redirect(url_for('login_page'))
    
    return render_template('studentdashboard.html')

@app.route('/upload_submission/<int:assignment_id>', methods=['POST'])
def upload_submission(assignment_id):
    student_id = session.get('reg_id')
    assignment = Assignment.query.get_or_404(assignment_id)
    subject = Subject.query.get(assignment.sub_id)

    if 'document' not in request.files:
        flash('No file uploaded.')
        return redirect(url_for('studentdashboard'))

    file = request.files['document']
    if file.filename == '':
        flash('No selected file.')
        return redirect(url_for('studentdashboard'))

    filename = secure_filename(file.filename)
    
    # Create uploads directory if it doesn't exist
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    
    filepath = os.path.join(uploads_dir, filename)
    file.save(filepath)

    new_submission = Submission(
        assignment_id=assignment.id,
        student_id=student_id,
        subject_name=subject.s_name,
        submitted_document=filename,
        upload_time=datetime.now(),
        marks=0,
        status='Submitted',
        on_time=True
    )
    db.session.add(new_submission)
    db.session.commit()

    flash('Assignment uploaded successfully!')
    return redirect(url_for('studentdashboard'))

@app.route('/evaluate_submission', methods=['POST'])
def evaluate_submission():
    try:
        import spacy
    except ModuleNotFoundError:
        spacy = None
    from collections import Counter
    from flask import request, jsonify, session
    from werkzeug.utils import secure_filename
    from datetime import datetime
    from PyPDF2 import PdfReader
    import docx2txt
    import os
    import requests
    import base64
    import time

    if spacy:
        try:
            nlp = spacy.load("en_core_web_md")
        except Exception:
            try:
                nlp = spacy.load("en_core_web_sm")
                print("⚠️ Warning: Falling back to en_core_web_sm — semantic scoring may be weaker.")
            except Exception:
                nlp = None
    else:
        nlp = None

    assignment_title = request.form['assignment_title']
    file = request.files['document']

    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = os.path.join(uploads_dir, filename)
    file.save(filepath)

    assignment = Assignment.query.filter_by(title=assignment_title).first()
    if not assignment:
        return jsonify({'error': 'Assignment not found'}), 404

    keywords = [k.strip().lower() for k in assignment.keywords.split(',')] if assignment.keywords else []

    try:
        if filename.endswith('.pdf'):
            reader = PdfReader(filepath)
            text = ''.join([page.extract_text() or '' for page in reader.pages])
        elif filename.endswith('.docx'):
            text = docx2txt.process(filepath)
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
    except Exception as e:
        return jsonify({'error': f"Error reading file: {str(e)}"}), 500

    if nlp:
        doc = nlp(text.lower())
        words = [token.text for token in doc if token.is_alpha]
        word_freq = Counter(words)
        match_count = sum(word_freq.get(kw, 0) for kw in keywords)
        
        # Semantic scoring
        semantic_score = 0
        for kw in keywords:
            kw_doc = nlp(kw)
            similarities = [kw_doc.similarity(sent) for sent in doc.sents]
            if similarities and max(similarities) > 0.75:
                semantic_score += 1
        semantic_score = (semantic_score / len(keywords)) * 100 if keywords else 0
    else:
        # Basic text processing without spacy
        words = re.findall(r'\w+', text.lower())
        word_freq = Counter(words)
        match_count = sum(word_freq.get(kw, 0) for kw in keywords)
        semantic_score = 0

    keyword_score = min(match_count / max(len(keywords), 1), 1.0) * 100
    word_count = len(words)
    word_score = min(word_count / 100, 1.0) * 100

    try:
        deadline = datetime.strptime(assignment.time, "%Y-%m-%dT%H:%M")
    except ValueError:
        return jsonify({'error': 'Invalid deadline format'}), 400

    on_time = datetime.now() <= deadline
    deadline_score = 100 if on_time else 0

    total_score = (keyword_score + word_score + deadline_score + semantic_score) / 4
    status = 'Pass' if total_score >= 50 else 'Fail'

    student_id = session.get('reg_id')
    subject = Subject.query.filter_by(sub_id=assignment.sub_id).first()

    # Update or create submission
    submission = Submission.query.filter_by(assignment_id=assignment.id, student_id=student_id).first()
    if submission:
        submission.marks = int(total_score)
        submission.status = status
        submission.on_time = on_time
        submission.upload_time = datetime.now()
    else:
        submission = Submission(
            assignment_id=assignment.id,
            student_id=student_id,
            subject_name=subject.s_name,
            submitted_document=filename,
            upload_time=datetime.now(),
            marks=int(total_score),
            status=status,
            on_time=on_time
        )
        db.session.add(submission)

    # Create or update result
    result = Result.query.filter_by(assignment_id=assignment.id, student_id=student_id).first()
    if result:
        result.total_matches = match_count
        result.marks = int(total_score)
        result.status = status
        result.on_time = on_time
        result.evaluated_at = datetime.now()
    else:
        result = Result(
            assignment_id=assignment.id,
            student_id=student_id,
            subject_name=subject.s_name,
            file_name=filename,
            total_matches=match_count,
            marks=int(total_score),
            status=status,
            on_time=on_time,
            evaluated_at=datetime.now()
        )
        db.session.add(result)
    
    db.session.commit()

    return jsonify({
        'title': assignment.title,
        'matches': match_count,
        'marks': int(total_score),
        'status': status,
        'on_time': on_time
    })

@app.route('/teacher/<int:class_id>/performance')
def student_performance(class_id):
    regular_results = Result.query.join(Assignment, Result.assignment_id == Assignment.id)\
                          .join(Subject, Assignment.sub_id == Subject.sub_id)\
                          .filter(Subject.class_id == class_id)\
                          .order_by(Result.evaluated_at.desc()).all()
    
    # Get script assignment results
    script_results = ScriptSubmission.query.join(ScriptAssignment, ScriptSubmission.script_assignment_id == ScriptAssignment.id)\
                                          .join(Subject, ScriptAssignment.sub_id == Subject.sub_id)\
                                          .filter(Subject.class_id == class_id)\
                                          .order_by(ScriptSubmission.submission_time.desc()).all()

    # Get latest live test attempt per student per test
    live_attempts = LiveTestAttempt.query.join(LiveTest, LiveTestAttempt.live_test_id == LiveTest.id)\
                                      .join(Subject, LiveTest.sub_id == Subject.sub_id)\
                                      .filter(Subject.class_id == class_id)\
                                      .order_by(LiveTestAttempt.ended_at.desc(), LiveTestAttempt.started_at.desc()).all()

    latest_live_attempts = {}
    for attempt in live_attempts:
        key = (attempt.student_id, attempt.live_test_id)
        if key not in latest_live_attempts:
            latest_live_attempts[key] = attempt

    live_results = []
    for attempt in latest_live_attempts.values():
        total_marks = int(attempt.live_test.total_marks if attempt.live_test else 0)
        marks_obtained = extract_live_test_score(attempt)
        marks_obtained = max(0, min(marks_obtained, total_marks))

        live_subject_name = 'N/A'
        if attempt.live_test:
            live_subject = Subject.query.get(attempt.live_test.sub_id)
            live_subject_name = live_subject.s_name if live_subject else 'N/A'

        result_status = 'Fail'
        if total_marks > 0 and marks_obtained >= (0.5 * total_marks):
            result_status = 'Pass'

        live_results.append({
            'id': attempt.id,
            'student_id': attempt.student_id,
            'subject_name': live_subject_name,
            'assignment_title': attempt.live_test.title if attempt.live_test else 'N/A',
            'assignment_type': 'live',
            'marks_obtained': marks_obtained,
            'total_marks': total_marks,
            'status': result_status,
            'attempt_status': attempt.status or 'N/A',
            'on_time': (attempt.status != 'TIME_EXPIRED'),
            'focus_lost_count': int(attempt.focus_lost_count or 0),
            'recording_path': attempt.recording_path,
            'response_file': attempt.response_file,
            'edit_url': url_for('edit_live_test_marks', class_id=class_id, attempt_id=attempt.id),
            'submitted_at': (attempt.ended_at or attempt.started_at or datetime.now())
        })
    
    # Create combined results for the "All Results" tab
    combined_results = []
    
    # Add regular assignment results
    for result in regular_results:
        combined_results.append({
            'id': result.id,
            'student_id': result.student_id,
            'subject_name': result.subject_name,
            'assignment_title': result.assignment.title if result.assignment else 'N/A',
            'assignment_type': 'regular',
            'marks_obtained': result.marks,
            'total_marks': result.assignment.total_marks if result.assignment else 0,
            'status': result.status,
            'on_time': result.on_time,
            'file_name': result.file_name,
            'edit_url': url_for('edit_theory_marks', class_id=class_id, result_id=result.id),
            'submitted_at': result.evaluated_at if result.evaluated_at else datetime.now()
        })
    
    # Add script assignment results
    for script_result in script_results:
        combined_results.append({
            'student_id': script_result.student_id,
            'subject_name': script_result.subject_name,
            'assignment_title': script_result.script_assignment.title if script_result.script_assignment else 'N/A',
            'assignment_type': 'script',
            'marks_obtained': script_result.marks_obtained,
            'total_marks': script_result.total_marks,
            'status': script_result.final_status,
            'on_time': script_result.is_on_time,
            'submitted_at': script_result.submission_time if script_result.submission_time else datetime.now()
        })

    # Add live test results
    for live_result in live_results:
        combined_results.append(live_result)
    
    # Sort combined results by submission time (newest first)
    combined_results.sort(key=lambda x: x['submitted_at'], reverse=True)
    
    subjects = Subject.query.filter_by(class_id=class_id).all()
    
    return render_template('class_dashboard.html', 
                         regular_results=regular_results, 
                         script_results=script_results,
                         live_results=live_results,
                         combined_results=combined_results,
                         subjects=subjects, 
                         class_id=class_id)


@app.route('/teacher/<int:class_id>/performance/theory/<int:result_id>/edit', methods=['GET', 'POST'])
def edit_theory_marks(class_id, result_id):
    teacher_id = resolve_teacher_id()
    if not teacher_id:
        return redirect(url_for('login_page'))

    result = Result.query.join(Assignment, Result.assignment_id == Assignment.id)\
        .join(Subject, Assignment.sub_id == Subject.sub_id)\
        .filter(Result.id == result_id, Subject.class_id == class_id)\
        .first_or_404()

    total_marks = int(result.assignment.total_marks if result.assignment else 0)

    if request.method == 'POST':
        try:
            updated_marks = int(request.form.get('marks', 0))
        except (TypeError, ValueError):
            flash('Enter a valid mark value.')
            return redirect(request.url)

        if updated_marks < 0 or updated_marks > total_marks:
            flash(f'Marks must be between 0 and {total_marks}.')
            return redirect(request.url)

        updated_status = calculate_pass_fail_status(updated_marks, total_marks)
        result.marks = updated_marks
        result.status = updated_status
        result.evaluated_at = datetime.utcnow()

        submission = Submission.query.filter_by(
            assignment_id=result.assignment_id,
            student_id=result.student_id
        ).first()
        if submission:
            submission.marks = updated_marks
            submission.status = updated_status

        db.session.commit()
        flash('Theory marks updated successfully.')
        return redirect(f"{url_for('student_performance', class_id=class_id)}#regular-tab")

    return render_template(
        'edit_marks.html',
        class_id=class_id,
        assessment_kind='Theory Assignment',
        subject_name=result.subject_name,
        student_id=result.student_id,
        assessment_title=result.assignment.title if result.assignment else 'N/A',
        current_marks=int(result.marks or 0),
        total_marks=total_marks,
        back_url=url_for('student_performance', class_id=class_id),
        review_links=[
            {
                'label': 'View document',
                'url': url_for('view_submission_file', filename=result.file_name)
            },
            {
                'label': 'Download document',
                'url': url_for('view_submission_file', filename=result.file_name, download='1')
            }
        ] if result.file_name else []
    )


@app.route('/teacher/<int:class_id>/performance/live/<int:attempt_id>/edit', methods=['GET', 'POST'])
def edit_live_test_marks(class_id, attempt_id):
    teacher_id = resolve_teacher_id()
    if not teacher_id:
        return redirect(url_for('login_page'))

    attempt = LiveTestAttempt.query.join(LiveTest, LiveTestAttempt.live_test_id == LiveTest.id)\
        .join(Subject, LiveTest.sub_id == Subject.sub_id)\
        .filter(LiveTestAttempt.id == attempt_id, Subject.class_id == class_id)\
        .first_or_404()

    total_marks = int(attempt.live_test.total_marks if attempt.live_test else 0)

    if request.method == 'POST':
        try:
            updated_marks = int(request.form.get('marks', 0))
        except (TypeError, ValueError):
            flash('Enter a valid mark value.')
            return redirect(request.url)

        if updated_marks < 0 or updated_marks > total_marks:
            flash(f'Marks must be between 0 and {total_marks}.')
            return redirect(request.url)

        response_payload = {}
        if attempt.response_text:
            try:
                parsed_payload = json.loads(attempt.response_text)
                if isinstance(parsed_payload, dict):
                    response_payload = parsed_payload
            except Exception:
                response_payload = {}

        response_payload['score'] = updated_marks
        response_payload['manual_override'] = True
        response_payload['manual_override_at'] = datetime.utcnow().isoformat()
        response_payload.setdefault('total_questions', response_payload.get('total_questions', 0))
        response_payload.setdefault('correct_answers', response_payload.get('correct_answers', 0))
        attempt.response_text = json.dumps(response_payload)

        proctor_events = attempt.proctor_events if isinstance(attempt.proctor_events, list) else []
        proctor_events.append({
            'type': 'manual_score_override',
            'score': updated_marks,
            'updated_at': datetime.utcnow().isoformat(),
            'teacher_id': teacher_id
        })
        attempt.proctor_events = proctor_events

        db.session.commit()
        flash('Live test marks updated successfully.')
        return redirect(f"{url_for('student_performance', class_id=class_id)}#live-tab")

    review_links = []
    if attempt.recording_path:
        review_links.append({
            'label': 'View recording',
            'url': url_for('live_test_recording', filename=attempt.recording_path)
        })
        review_links.append({
            'label': 'Download recording',
            'url': url_for('live_test_recording', filename=attempt.recording_path, download='1')
        })
    if attempt.response_file:
        review_links.append({
            'label': 'Download response file',
            'url': url_for('live_test_response_file', filename=attempt.response_file)
        })

    live_subject = Subject.query.get(attempt.live_test.sub_id) if attempt.live_test else None

    return render_template(
        'edit_marks.html',
        class_id=class_id,
        assessment_kind='Live Test',
        subject_name=live_subject.s_name if live_subject else 'N/A',
        student_id=attempt.student_id,
        assessment_title=attempt.live_test.title if attempt.live_test else 'N/A',
        current_marks=int(extract_live_test_score(attempt) or 0),
        total_marks=total_marks,
        back_url=url_for('student_performance', class_id=class_id),
        review_links=review_links
    )


@app.route('/teacher/<int:class_id>/reports')
def teacher_reports(class_id):
    cls = Class.query.get_or_404(class_id)
    subjects = Subject.query.filter_by(class_id=class_id).all()

    students = Student.query.filter_by(class_=cls.class_id).all()
    student_progress = {}
    for student in students:
        student_progress[student.reg_id] = {
            'student_id': student.reg_id,
            'student_name': student.name,
            'theory_obtained': 0,
            'theory_total': 0,
            'script_obtained': 0,
            'script_total': 0,
            'live_obtained': 0,
            'live_total': 0,
            'overall_obtained': 0,
            'overall_total': 0,
            'overall_percent': 0.0
        }

    regular_results = Result.query.join(Assignment, Result.assignment_id == Assignment.id)\
                          .join(Subject, Assignment.sub_id == Subject.sub_id)\
                          .filter(Subject.class_id == class_id).all()

    for result in regular_results:
        if result.student_id not in student_progress:
            student_progress[result.student_id] = {
                'student_id': result.student_id,
                'student_name': result.student_id,
                'theory_obtained': 0,
                'theory_total': 0,
                'script_obtained': 0,
                'script_total': 0,
                'live_obtained': 0,
                'live_total': 0,
                'overall_obtained': 0,
                'overall_total': 0,
                'overall_percent': 0.0
            }

        total_marks = result.assignment.total_marks if result.assignment else 0
        student_progress[result.student_id]['theory_obtained'] += int(result.marks or 0)
        student_progress[result.student_id]['theory_total'] += int(total_marks or 0)

    script_results = ScriptSubmission.query.join(ScriptAssignment, ScriptSubmission.script_assignment_id == ScriptAssignment.id)\
                                          .join(Subject, ScriptAssignment.sub_id == Subject.sub_id)\
                                          .filter(Subject.class_id == class_id).all()

    for script_result in script_results:
        if script_result.student_id not in student_progress:
            student_progress[script_result.student_id] = {
                'student_id': script_result.student_id,
                'student_name': script_result.student_id,
                'theory_obtained': 0,
                'theory_total': 0,
                'script_obtained': 0,
                'script_total': 0,
                'live_obtained': 0,
                'live_total': 0,
                'overall_obtained': 0,
                'overall_total': 0,
                'overall_percent': 0.0
            }

        student_progress[script_result.student_id]['script_obtained'] += int(script_result.marks_obtained or 0)
        student_progress[script_result.student_id]['script_total'] += int(script_result.total_marks or 0)

    live_attempts = LiveTestAttempt.query.join(LiveTest, LiveTestAttempt.live_test_id == LiveTest.id)\
                                      .join(Subject, LiveTest.sub_id == Subject.sub_id)\
                                      .filter(Subject.class_id == class_id)\
                                      .order_by(LiveTestAttempt.ended_at.desc(), LiveTestAttempt.started_at.desc()).all()

    latest_attempt_by_test = {}
    for attempt in live_attempts:
        key = (attempt.student_id, attempt.live_test_id)
        if key not in latest_attempt_by_test:
            latest_attempt_by_test[key] = attempt

    for attempt in latest_attempt_by_test.values():
        if attempt.student_id not in student_progress:
            student_progress[attempt.student_id] = {
                'student_id': attempt.student_id,
                'student_name': attempt.student_id,
                'theory_obtained': 0,
                'theory_total': 0,
                'script_obtained': 0,
                'script_total': 0,
                'live_obtained': 0,
                'live_total': 0,
                'overall_obtained': 0,
                'overall_total': 0,
                'overall_percent': 0.0
            }

        test_total = int(attempt.live_test.total_marks if attempt.live_test else 0)
        student_progress[attempt.student_id]['live_total'] += test_total
        obtained = extract_live_test_score(attempt)

        obtained = max(0, min(obtained, test_total))
        student_progress[attempt.student_id]['live_obtained'] += obtained

    progress_rows = []
    for _, row in student_progress.items():
        row['overall_obtained'] = row['theory_obtained'] + row['script_obtained'] + row['live_obtained']
        row['overall_total'] = row['theory_total'] + row['script_total'] + row['live_total']
        if row['overall_total'] > 0:
            row['overall_percent'] = round((row['overall_obtained'] / row['overall_total']) * 100, 2)
        else:
            row['overall_percent'] = 0.0
        progress_rows.append(row)

    progress_rows.sort(key=lambda value: value['student_id'])

    return render_template(
        'reports_dashboard.html',
        is_teacher_view=True,
        class_id=class_id,
        class_name=cls.class_id,
        subjects=subjects,
        progress_rows=progress_rows
    )


@app.route('/student/reports')
def student_reports():
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return redirect(url_for('login_page'))

    student = Student.query.filter_by(reg_id=student_reg_id).first()
    if not student:
        flash('Student not found.')
        return redirect(url_for('login_page'))

    regular_results = Result.query.filter_by(student_id=student_reg_id)\
                          .order_by(Result.evaluated_at.desc()).all()

    script_results = ScriptSubmission.query.filter_by(student_id=student_reg_id)\
                          .order_by(ScriptSubmission.submission_time.desc()).all()

    live_attempts = LiveTestAttempt.query.filter_by(student_id=student_reg_id)\
                          .order_by(LiveTestAttempt.ended_at.desc(), LiveTestAttempt.started_at.desc()).all()

    theory_obtained, theory_total = 0, 0
    script_obtained, script_total = 0, 0
    live_obtained, live_total = 0, 0

    detail_rows = []

    for result in regular_results:
        total_marks = int(result.assignment.total_marks if result.assignment else 0)
        obtained = int(result.marks or 0)
        theory_obtained += obtained
        theory_total += total_marks
        detail_rows.append({
            'category': 'Theory',
            'subject_name': result.subject_name,
            'assessment_name': result.assignment.title if result.assignment else 'N/A',
            'obtained': obtained,
            'total': total_marks,
            'status': result.status or 'N/A',
            'submitted_at': result.evaluated_at
        })

    for script_result in script_results:
        total_marks = int(script_result.total_marks or 0)
        obtained = int(script_result.marks_obtained or 0)
        script_obtained += obtained
        script_total += total_marks
        detail_rows.append({
            'category': 'Script',
            'subject_name': script_result.subject_name,
            'assessment_name': script_result.script_assignment.title if script_result.script_assignment else 'N/A',
            'obtained': obtained,
            'total': total_marks,
            'status': script_result.final_status or 'N/A',
            'submitted_at': script_result.submission_time
        })

    latest_attempt_by_test = {}
    for attempt in live_attempts:
        key = attempt.live_test_id
        if key not in latest_attempt_by_test:
            latest_attempt_by_test[key] = attempt

    for attempt in latest_attempt_by_test.values():
        test_total = int(attempt.live_test.total_marks if attempt.live_test else 0)
        obtained = extract_live_test_score(attempt)

        obtained = max(0, min(obtained, test_total))
        live_obtained += obtained
        live_total += test_total

        subject_name = 'N/A'
        if attempt.live_test:
            live_subject = Subject.query.get(attempt.live_test.sub_id)
            subject_name = live_subject.s_name if live_subject else 'N/A'

        detail_rows.append({
            'category': 'Live Test',
            'subject_name': subject_name,
            'assessment_name': attempt.live_test.title if attempt.live_test else 'N/A',
            'obtained': obtained,
            'total': test_total,
            'status': attempt.status or 'N/A',
            'submitted_at': attempt.ended_at or attempt.started_at
        })

    detail_rows.sort(key=lambda item: item['submitted_at'] or datetime.min, reverse=True)

    overall_obtained = theory_obtained + script_obtained + live_obtained
    overall_total = theory_total + script_total + live_total
    overall_percent = round((overall_obtained / overall_total) * 100, 2) if overall_total > 0 else 0.0

    return render_template(
        'reports_dashboard.html',
        is_teacher_view=False,
        student=student,
        theory_obtained=theory_obtained,
        theory_total=theory_total,
        script_obtained=script_obtained,
        script_total=script_total,
        live_obtained=live_obtained,
        live_total=live_total,
        overall_obtained=overall_obtained,
        overall_total=overall_total,
        overall_percent=overall_percent,
        detail_rows=detail_rows
    )


@app.route('/teacher/<int:class_id>/performance/download')
def download_student_performance(class_id):
    regular_results = Result.query.join(Assignment, Result.assignment_id == Assignment.id)\
                          .join(Subject, Assignment.sub_id == Subject.sub_id)\
                          .filter(Subject.class_id == class_id)\
                          .order_by(Result.evaluated_at.desc()).all()

    script_results = ScriptSubmission.query.join(ScriptAssignment, ScriptSubmission.script_assignment_id == ScriptAssignment.id)\
                                          .join(Subject, ScriptAssignment.sub_id == Subject.sub_id)\
                                          .filter(Subject.class_id == class_id)\
                                          .order_by(ScriptSubmission.submission_time.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Student ID',
        'Subject',
        'Assignment',
        'Type',
        'Marks Obtained',
        'Total Marks',
        'Status',
        'On Time',
        'Submitted At'
    ])

    for result in regular_results:
        writer.writerow([
            result.student_id,
            result.subject_name,
            result.assignment.title if result.assignment else 'N/A',
            'Regular',
            result.marks,
            result.assignment.total_marks if result.assignment else 0,
            result.status,
            'Yes' if result.on_time else 'No',
            result.evaluated_at.strftime('%Y-%m-%d %H:%M') if result.evaluated_at else 'N/A'
        ])

    for script_result in script_results:
        writer.writerow([
            script_result.student_id,
            script_result.subject_name,
            script_result.script_assignment.title if script_result.script_assignment else 'N/A',
            'Script',
            script_result.marks_obtained,
            script_result.total_marks,
            script_result.final_status,
            'Yes' if script_result.is_on_time else 'No',
            script_result.submission_time.strftime('%Y-%m-%d %H:%M') if script_result.submission_time else 'N/A'
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=class_{class_id}_results.csv'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response

@app.route('/subject/<int:sub_id>/results')
def view_results(sub_id):
    """View all results for assignments in a subject"""
    subject = Subject.query.get_or_404(sub_id)
    
    # Get results for regular assignments
    regular_results = Result.query.join(Assignment, Result.assignment_id == Assignment.id)\
                                 .filter(Assignment.sub_id == sub_id)\
                                 .order_by(Result.evaluated_at.desc()).all()
    
    # Get results for script assignments
    script_results = ScriptSubmission.query.join(ScriptAssignment, ScriptSubmission.script_assignment_id == ScriptAssignment.id)\
                                          .filter(ScriptAssignment.sub_id == sub_id)\
                                          .order_by(ScriptSubmission.submission_time.desc()).all()
    
    return render_template('results.html', subject=subject, regular_results=regular_results, script_results=script_results)

def evaluate_script(compilation_success, deadline_time):
    on_time = datetime.now() <= deadline_time
    if compilation_success and on_time:
        return 100, "✅ Compilation Successful - Submitted on Time", True
    elif compilation_success:
        return 70, "✅ Compilation Successful - ❌ Deadline Missed", False
    else:
        return 0, "❌ Compilation Failed", False

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for('login_page'))

@app.route('/teacher_activity')
def teacher_activity():
    """Show teachers with activity filtering and sorting options"""
    # Get filter parameters from query string
    show_filter = request.args.get('show', 'all')  # all, active, inactive
    sort_filter = request.args.get('sort', 'most_active')  # most_active, least_active, name_asc, name_desc
    
    # Calculate date one month ago for inactivity threshold
    one_month_ago = datetime.now() - timedelta(days=30)
    
    # Get all teachers
    all_teachers = Teacher.query.all()
    teachers_data = []
    
    for teacher in all_teachers:
        # Get the teacher's subjects
        subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
        subject_ids = [subject.sub_id for subject in subjects]
        subject_names = [subject.s_name for subject in subjects]
        
        # Check for regular assignments in the last month
        recent_regular_assignments = Assignment.query.filter(
            Assignment.sub_id.in_(subject_ids),
            Assignment.timestamp >= one_month_ago
        ).first()
        
        # Check for script assignments in the last month
        recent_script_assignments = ScriptAssignment.query.filter(
            ScriptAssignment.sub_id.in_(subject_ids),
            ScriptAssignment.timestamp >= one_month_ago
        ).first()
        
        # Determine if teacher is active (has assignments in last month)
        is_active = recent_regular_assignments is not None or recent_script_assignments is not None
        
        # Find the most recent assignment (if any exists)
        last_regular = Assignment.query.filter(
            Assignment.sub_id.in_(subject_ids)
        ).order_by(Assignment.timestamp.desc()).first()
        
        last_script = ScriptAssignment.query.filter(
            ScriptAssignment.sub_id.in_(subject_ids)
        ).order_by(ScriptAssignment.timestamp.desc()).first()
        
        # Determine the last activity date
        last_activity = None
        if last_regular and last_script:
            last_activity = max(last_regular.timestamp, last_script.timestamp)
        elif last_regular:
            last_activity = last_regular.timestamp
        elif last_script:
            last_activity = last_script.timestamp
        
        # Calculate days since last activity
        days_since_activity = None
        if last_activity:
            days_since_activity = (datetime.now() - last_activity).days
        
        teachers_data.append({
            'id': teacher.id,
            'name': teacher.name,
            'reg_id': teacher.reg_id,
            'email': teacher.email,
            'department': teacher.department,
            'last_activity': last_activity,
            'days_since_activity': days_since_activity,
            'subjects': subject_names,
            'is_active': is_active
        })
    
    # Apply filters
    if show_filter == 'active':
        teachers_data = [t for t in teachers_data if t['is_active']]
    elif show_filter == 'inactive':
        teachers_data = [t for t in teachers_data if not t['is_active']]
    
    # Apply sorting
    if sort_filter == 'most_active':
        teachers_data.sort(key=lambda x: (
            x['is_active'],  # Active teachers first
            -x['days_since_activity'] if x['days_since_activity'] is not None else float('-inf')  # Then by most recent activity
        ), reverse=True)
    elif sort_filter == 'least_active':
        teachers_data.sort(key=lambda x: (
            not x['is_active'],  # Inactive teachers first
            x['days_since_activity'] if x['days_since_activity'] is not None else float('inf')  # Then by least recent activity
        ), reverse=True)
    elif sort_filter == 'name_asc':
        teachers_data.sort(key=lambda x: x['name'].lower())
    elif sort_filter == 'name_desc':
        teachers_data.sort(key=lambda x: x['name'].lower(), reverse=True)
    
    # Count active and inactive teachers
    active_teachers_count = sum(1 for t in teachers_data if t['is_active'])
    inactive_teachers_count = sum(1 for t in teachers_data if not t['is_active'])
    
    return render_template('teacher_activity.html', 
                         teachers=teachers_data,
                         total_teachers=len(all_teachers),
                         active_teachers_count=active_teachers_count,
                         inactive_teachers_count=inactive_teachers_count,
                         show_filter=show_filter,
                         sort_filter=sort_filter)

@app.route('/subject/<int:sub_id>/assignments/create_script', methods=['GET', 'POST'])
def create_script_assignment(sub_id):
    subject = Subject.query.get_or_404(sub_id)

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            language = request.form.get('language', 'c')
            deadline_str = request.form.get('deadline')
            total_marks = int(request.form.get('total_marks'))
            questions = request.form.get('questions', '')
            
            # Convert deadline string to datetime
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            
            # Optional function template details
            function_name = request.form.get('function_name') or None
            return_type = request.form.get('return_type') or None
            template_code = request.form.get('template_code') or None
            
            # Execution limits
            time_limit = int(request.form.get('time_limit', 2))
            memory_limit = int(request.form.get('memory_limit', 128000))
            
            # Rubric criteria
            rubric_selected = request.form.getlist('rubric_criteria')
            rubric = ', '.join(rubric_selected)

            # Collect test cases dynamically
            testcases = []
            i = 1
            while True:
                input_key = f'test_input_{i}'
                output_key = f'test_output_{i}'
                weight_key = f'test_weight_{i}'
                hidden_key = f'test_hidden_{i}'
                
                if input_key in request.form and output_key in request.form:
                    inp = request.form[input_key].strip()
                    out = request.form[output_key].strip()
                    weight = int(request.form.get(weight_key, 10))
                    is_hidden = bool(request.form.get(hidden_key))
                    
                    if inp and out:
                        testcases.append({
                            'input': inp,
                            'expected_output': out,
                            'weight': weight,
                            'is_hidden': is_hidden,
                            'index': i-1
                        })
                    i += 1
                else:
                    break

            # Generate function signature if function details provided
            function_signature = None
            if function_name and return_type:
                function_signature = f"{return_type} {function_name}();"

            # Generate basic template if none provided but function details given
            if not template_code and function_name and return_type:
                if language.lower() == 'c':
                    template_code = f"""#include <stdio.h>
#include <stdlib.h>

{return_type} {function_name}() {{
    // Write your code here
    
}}"""
                elif language.lower() == 'cpp':
                    template_code = f"""#include <iostream>
using namespace std;

{return_type} {function_name}() {{
    // Write your code here
    
}}"""
                elif language.lower() == 'python':
                    template_code = f"""def {function_name}():
    # Write your code here
    pass"""
                elif language.lower() == 'java':
                    template_code = f"""public class Solution {{
    public static {return_type} {function_name}() {{
        // Write your code here
        
    }}
}}"""

            new_script = ScriptAssignment(
                title=title,
                deadline=deadline,
                total_marks=total_marks,
                questions=questions,
                function_name=function_name,
                function_signature=function_signature,
                template_code=template_code,
                language=language,
                testcases=testcases,
                rubric=rubric,
                time_limit=time_limit,
                memory_limit=memory_limit,
                sub_id=sub_id,
                timestamp=datetime.now()
            )
            db.session.add(new_script)
            db.session.commit()

            flash('Script assignment created successfully!')
            return redirect(url_for('subject_assignments', sub_id=sub_id))
            
        except Exception as e:
            flash(f'Error creating assignment: {str(e)}')
            return redirect(url_for('create_script_assignment', sub_id=sub_id))

    return render_template('create_script_assignment.html', subject=subject)

def get_language_id(language):
    """Get Judge0 language ID"""
    language_map = {
        'c': 50,         # C (GCC 9.2.0)
        'cpp': 54,       # C++ (GCC 9.2.0)
        'java': 62,      # Java (OpenJDK 13.0.1)
        'python': 71     # Python (3.8.1)
    }
    return language_map.get(language.lower(), 50)

def execute_test_case(complete_code, test_input, language, time_limit=2, memory_limit=128000):
    """Execute single test case using Judge0"""
    try:
        payload = {
            "source_code": complete_code,
            "language_id": get_language_id(language),
            "stdin": test_input,
            "cpu_time_limit": time_limit,
            "memory_limit": memory_limit,
            "wall_time_limit": time_limit + 1,
            "max_processes_and_or_threads": 30,
            "enable_per_process_and_thread_time_limit": False,
            "enable_per_process_and_thread_memory_limit": False,
            "max_file_size": 1024
        }
        
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": "7d2f3e542amshe0fc0fe7f077e94p1e5b46jsn07418d37bf0f",  # Replace with your API key
            "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com"
        }
        
        response = requests.post(
            "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&wait=true", 
            json=payload, 
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            return {
                'status': 'ERROR',
                'error': f'Judge0 API error: {response.status_code}',
                'stdout': '',
                'stderr': response.text,
                'time': 0,
                'memory': 0
            }
        
        result = response.json()
        return {
            'status': 'SUCCESS' if result.get('status', {}).get('id') == 3 else 'ERROR',
            'stdout': result.get('stdout', '').strip(),
            'stderr': result.get('stderr', ''),
            'compile_output': result.get('compile_output', ''),
            'time': float(result.get('time', 0) or 0),
            'memory': int(result.get('memory', 0) or 0),
            'status_id': result.get('status', {}).get('id', 0),
            'status_description': result.get('status', {}).get('description', '')
        }
        
    except Exception as e:
        return {
            'status': 'ERROR',
            'error': f'Execution error: {str(e)}',
            'stdout': '',
            'stderr': str(e),
            'time': 0,
            'memory': 0
        }

def evaluate_script_submission(student_code, script_assignment, test_mode=False):
    """Evaluate script submission against all test cases"""
    testcases = script_assignment.testcases or []
    results = {
        'compilation_status': 'UNKNOWN',
        'compilation_error': '',
        'total_test_cases': len(testcases),
        'passed_test_cases': 0,
        'failed_test_cases': 0,
        'test_results': [],
        'marks_breakdown': {},
        'final_marks': 0,
        'final_status': 'FAIL'
    }
    
    # Check if submission is on time
    is_on_time = datetime.now() <= script_assignment.deadline
    
    # Simple test to check compilation
    simple_test = {
        'input': '5\n',
        'expected_output': '5'
    }
    
    compile_result = execute_test_case(
        student_code, 
        simple_test['input'], 
        script_assignment.language,
        script_assignment.time_limit,
        script_assignment.memory_limit
    )
    
    results['compilation_status'] = 'SUCCESS' if compile_result['status'] == 'SUCCESS' else 'FAILED'
    results['compilation_error'] = compile_result.get('stderr', '') or compile_result.get('compile_output', '')
    
    if results['compilation_status'] == 'FAILED':
        results['marks_breakdown'] = {
            'deadline_marks': 30 if is_on_time else 0,
            'compilation_marks': 0,
            'testcase_marks': 0
        }
        results['final_marks'] = results['marks_breakdown']['deadline_marks']
        return results
    
    # If compilation successful, run all test cases
    passed_count = 0
    applicable_testcases = testcases
    if test_mode:
        applicable_testcases = [tc for tc in testcases if not tc.get('is_hidden', False)]

    total_test_weight = sum(tc.get('weight', 10) for tc in applicable_testcases)
    earned_test_weight = 0
    
    for i, test_case in enumerate(applicable_testcases):
        test_result = execute_test_case(
            student_code,
            test_case['input'],
            script_assignment.language,
            script_assignment.time_limit,
            script_assignment.memory_limit
        )
        
        # Compare outputs
        expected = test_case['expected_output'].strip()
        actual = test_result['stdout'].strip()
        
        test_passed = (expected == actual and test_result['status'] == 'SUCCESS')
        
        if test_passed:
            passed_count += 1
            earned_test_weight += test_case.get('weight', 10)
        
        results['test_results'].append({
            'test_case_index': i,
            'input_data': test_case['input'],
            'expected_output': expected,
            'actual_output': actual,
            'status': 'PASSED' if test_passed else 'FAILED',
            'execution_time': test_result['time'],
            'memory_used': test_result['memory'],
            'error_message': test_result.get('stderr', '') if not test_passed else '',
            'weight': test_case.get('weight', 10),
            'is_hidden': test_case.get('is_hidden', False)
        })
    
    results['passed_test_cases'] = passed_count
    results['failed_test_cases'] = len(applicable_testcases) - passed_count
    results['total_test_cases'] = len(applicable_testcases)
    
    # Calculate marks based on rubric
    testcase_score = (earned_test_weight / total_test_weight * 50) if total_test_weight > 0 else 0
    
    results['marks_breakdown'] = {
        'deadline_marks': 30 if is_on_time else 0,
        'compilation_marks': 20,  # Full marks for successful compilation
        'testcase_marks': int(testcase_score)
    }
    
    results['final_marks'] = sum(results['marks_breakdown'].values())
    results['final_status'] = 'PASS' if results['final_marks'] >= 50 else 'FAIL'
    
    return results

@app.route('/evaluate_script', methods=['POST'])
def evaluate_script_enhanced():
    """Enhanced script evaluation with LeetCode-style test cases"""
    data = request.get_json()
    assignment_id = data.get("assignment_id")
    student_code = data.get("student_code", "")
    test_mode = bool(data.get("test_mode", False))
    
    # For backwards compatibility, also handle the old format
    if not student_code and 'compilation_success' in data:
        compilation_success = data.get("compilation_success")
        assignment = Assignment.query.get(assignment_id)
        if assignment:
            try:
                deadline_time = datetime.strptime(assignment.time, "%Y-%m-%dT%H:%M")
            except ValueError:
                return jsonify({'message': 'Invalid deadline format', 'marks': 0}), 400
            marks, message, _ = evaluate_script(compilation_success, deadline_time)
            return jsonify({'marks': marks, 'message': message})
    
    # New enhanced evaluation
    script_assignment = ScriptAssignment.query.get(assignment_id)
    if not script_assignment:
        return jsonify({'message': 'Script assignment not found', 'marks': 0}), 404
    
    if not student_code:
        return jsonify({'message': 'No code provided', 'marks': 0}), 400
    
    # Evaluate the submission
    evaluation_results = evaluate_script_submission(student_code, script_assignment, test_mode=test_mode)
    
    # Save submission to database
    student_id = session.get('reg_id')
    if student_id:
        subject = Subject.query.get(script_assignment.sub_id)
        submission = ScriptSubmission(
            script_assignment_id=script_assignment.id,
            student_id=student_id,
            subject_name=subject.s_name if subject else 'Unknown Subject',
            submitted_code=student_code,
            language_used=script_assignment.language,
            submission_time=datetime.now(),
            compilation_status=evaluation_results['compilation_status'],
            compilation_error=evaluation_results['compilation_error'],
            total_test_cases=evaluation_results['total_test_cases'],
            passed_test_cases=evaluation_results['passed_test_cases'],
            failed_test_cases=evaluation_results['failed_test_cases'],
            total_marks=script_assignment.total_marks,
            marks_obtained=evaluation_results['final_marks'],
            deadline_marks=evaluation_results['marks_breakdown']['deadline_marks'],
            compilation_marks=evaluation_results['marks_breakdown']['compilation_marks'],
            testcase_marks=evaluation_results['marks_breakdown']['testcase_marks'],
            final_status=evaluation_results['final_status'],
            is_on_time=datetime.now() <= script_assignment.deadline
        )
        
        db.session.add(submission)
        db.session.flush()  # Get the submission ID
        
        # Save individual test case results
        for test_result in evaluation_results['test_results']:
            tc_result = TestCaseResult(
                submission_id=submission.id,
                test_case_index=test_result['test_case_index'],
                input_data=test_result['input_data'],
                expected_output=test_result['expected_output'],
                actual_output=test_result['actual_output'],
                status=test_result['status'],
                execution_time=test_result['execution_time'],
                memory_used=test_result['memory_used'],
                error_message=test_result['error_message']
            )
            db.session.add(tc_result)
        
        db.session.commit()
    
    return jsonify({
        'marks': evaluation_results['final_marks'],
        'status': evaluation_results['final_status'],
        'message': f"Compilation: {evaluation_results['compilation_status']}, "
                  f"Test Cases: {evaluation_results['passed_test_cases']}/{evaluation_results['total_test_cases']} passed",
        'compilation_status': evaluation_results['compilation_status'],
        'test_results': [
            {
                'index': t['test_case_index'] + 1,
                'status': t['status'],
                'expected': 'Hidden' if (test_mode and t.get('is_hidden')) else t['expected_output'],
                'actual': t['actual_output'],
                'error': t.get('error_message', '')
            }
            for t in evaluation_results['test_results']
        ],
        'marks_breakdown': evaluation_results['marks_breakdown']
    })

# Add this route to provide template code to students
@app.route('/get_script_template/<int:assignment_id>')
def get_script_template(assignment_id):
    """Provide template code for script assignments"""
    script_assignment = ScriptAssignment.query.get(assignment_id)
    if not script_assignment:
        return jsonify({'error': 'Assignment not found'}), 404
    
    return jsonify({
        'template_code': script_assignment.template_code or '',
        'function_name': script_assignment.function_name or '',
        'language': script_assignment.language,
        'function_signature': script_assignment.function_signature or ''
    })
    
@app.route('/get_student_subjects')
def get_student_subjects():
    """Get subjects for the current student based on their class"""
    student_reg_id = session.get('reg_id')
    if not student_reg_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    student = Student.query.filter_by(reg_id=student_reg_id).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    # Get class ID from class name
    class_obj = Class.query.filter_by(class_id=student.class_).first()
    if not class_obj:
        return jsonify({'error': 'Class not found'}), 404
    
    # Get subjects for this class
    subjects = Subject.query.filter_by(class_id=class_obj.id).all()
    
    subjects_data = []
    for subject in subjects:
        subjects_data.append({
            'sub_id': subject.sub_id,
            's_name': subject.s_name
        })
    
    return jsonify({'subjects': subjects_data})

@app.route('/get_subject_assignments/<int:sub_id>')
def get_subject_assignments(sub_id):
    """Get all assignments (regular and script) for a specific subject"""
    assignments_data = []
    
    # Get regular assignments
    regular_assignments = Assignment.query.filter_by(sub_id=sub_id).all()
    for a in regular_assignments:
        formatted_time = a.time.strftime('%Y-%m-%d %H:%M') if isinstance(a.time, datetime) else a.time.replace('T', ' ')
        assignments_data.append({
            'assignment_id': a.id,
            'title': a.title,
            'timestamp': a.timestamp.strftime('%Y-%m-%d %H:%M'),
            'time': formatted_time,
            'type': a.type,
            'total_marks': a.total_marks,
            'questions': a.questions or 'No description provided'
        })
    
    # Get script assignments
    script_assignments = ScriptAssignment.query.filter_by(sub_id=sub_id).all()
    for sa in script_assignments:
        deadline_formatted = (
            sa.deadline.strftime('%Y-%m-%d %H:%M')
            if isinstance(sa.deadline, datetime)
            else str(sa.deadline).replace('T', ' ')
        )
        assignments_data.append({
            'assignment_id': sa.id,
            'title': sa.title,
            'timestamp': sa.timestamp.strftime('%Y-%m-%d %H:%M') if sa.timestamp else 'N/A',
            'time': deadline_formatted,
            'type': 'script',
            'total_marks': sa.total_marks,
            'questions': sa.questions or 'No description provided'
        })

    # Get live tests
    live_tests = LiveTest.query.filter_by(sub_id=sub_id).all()
    for lt in live_tests:
        question_count = 0
        try:
            parsed = json.loads(lt.questions_text) if lt.questions_text else []
            if isinstance(parsed, list):
                question_count = len(parsed)
        except Exception:
            question_count = 0

        assignments_data.append({
            'assignment_id': lt.id,
            'title': lt.title,
            'timestamp': lt.created_at.strftime('%Y-%m-%d %H:%M') if lt.created_at else 'N/A',
            'time': f"{lt.duration_minutes} minutes",
            'type': 'live',
            'total_marks': lt.total_marks,
            'questions': f"MCQ Live Test ({question_count} questions)" if question_count else 'MCQ Live Test'
        })
    
    return jsonify({'assignments': assignments_data})