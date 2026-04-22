import email
import os
from flask import Flask, render_template, request, redirect,session, jsonify
from datetime import date
import mysql.connector

app = Flask(__name__)
app.secret_key = "mess_secret_key"

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="messuser",   # MUST be this
        password="1234",
        database="ManagementSystem",
        auth_plugin = "mysql_native_password"
    )

@app.route("/")
def home():
    return render_template("login.html")

UPLOAD_FOLDER = "static/profile"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    
    password = request.form["password"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone() 
    
    '''
    now user = {
        "user_id": 1,
        "username": "john_doe",
        "email": "abc@gmail.com",
        "password": "1234",
        "role": "user"
    }
    '''
    cursor.close()
    conn.close()

    #if user is not NULL then

    if user:
        session["username"] = user["username"] #Here section["username"] means we are creating a session variable named "username" and storing the value of user["username"] in it. This allows us to keep track of the logged-in user's username across different pages of the application.
        session["role"] = user["role"]
        if user["role"] == "admin":
            return redirect("/admin_dashboard")
        else:
            return redirect("/student_dashboard")
    else:
        return "Invalid Login"

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()

        #cheak if email is already registered
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        existing_email = cursor.fetchone()
        if existing_email:
            cursor.close()
            conn.close()
            return "Email already registered. <a href='/register'>Try Again</a>"

        # Check if username is already taken
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing_username = cursor.fetchone()
        if existing_username:
            cursor.close()
            conn.close()
            return "Username already taken. <a href='/register'>Try Again</a>"


        # Insert into users
        cursor.execute("""
        INSERT INTO users (username, email, password, role)
        VALUES (%s, %s, %s, 'student')
        """, (username, email, password))

        # Get user_id
        user_id = cursor.lastrowid 

        # Insert into students table
        cursor.execute("""
        INSERT INTO students (student_id, name, email)
        VALUES (%s, %s, %s)
        """, (user_id, username, email))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/")

    return render_template("register.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    if "role" in session and session["role"] == "admin": #here role is present in session and its value is admin then only we will show admin dashboard otherwise we will redirect to home page

        conn = get_connection() #Database connection
        cursor = conn.cursor(dictionary=True) #Curser to write sql queries and dictionary=True means we will get result in form of dictionary instead of tuple

        # Total Students
        cursor.execute("""
            SELECT COUNT(*) AS total_students
            FROM users
            WHERE role = 'student'
        """)
        total_students = cursor.fetchone()["total_students"] #here we count how many students are there in users table and we fetch the result and store it in total_students variable
        #For example total_students = {
        #   "total_students": 100
        #}
        # Total Active Subscriptions
        cursor.execute("""
            SELECT COUNT(*) AS total_active
            FROM subscriptions
            WHERE LOWER(TRIM(status)) = 'active'
            AND end_date >= CURDATE()
        """)
        total_active = cursor.fetchone()["total_active"]

        # Total Pending Requests
        cursor.execute("""
            SELECT COUNT(*) AS total_pending
            FROM subscriptions
            WHERE status = 'Pending'
        """)
        total_pending = cursor.fetchone()["total_pending"]

        # Pending Request Table
        cursor.execute("""
            SELECT s.subscription_id,
                   u.username,
                   u.email,
                   m.plan_name,
                   s.status
            FROM subscriptions s
            JOIN users u ON s.student_id = u.user_id
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.status = 'Pending'
        """)
        requests = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "admin_dashboard.html",
            total_students=total_students,
            total_active=total_active,
            total_pending=total_pending,
            requests=requests
        )

    return redirect("/")


UPLOAD_FOLDER = "static/profile"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# create folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload_profile", methods=["POST"])


def upload_profile():

    if "photo" not in request.files:
        return jsonify({"status": "error"})

    file = request.files["photo"]

    if file.filename == "":
        return jsonify({"status": "error"})

    # save photo using username
    filename = session["username"] + ".jpg"

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(filepath)

    return jsonify({
        "status": "success",
        "filename": filename
    })


@app.route("/approve/<int:sub_id>")
def approve(sub_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE subscriptions
    SET status='Approved'
    WHERE subscription_id=%s
    """,(sub_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin_dashboard")

@app.route("/reject/<int:sub_id>")
def reject(sub_id):
    if "role" in session and session["role"] == "admin":

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET status = 'Rejected'
            WHERE subscription_id = %s
        """, (sub_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/admin_dashboard")

    return redirect("/")

@app.route("/student_dashboard")
def student_dashboard():
    if "role" in session and session["role"] == "student":

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student subscription + plan (JOIN)
        cursor.execute("""
            SELECT s.subscription_id, s.end_date, m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            JOIN users u ON u.username = %s
            WHERE s.student_id = u.user_id
            AND s.status='Active'
            ORDER BY s.subscription_id DESC
            LIMIT 1
            """,(session["username"],))
        
        subscription = cursor.fetchone()

        # Get Username
        cursor.execute(
            "SELECT username FROM users WHERE username=%s",
            (session["username"],)
        )

        UserName = cursor.fetchone()
        username = UserName["username"]

        # Default values
        plan_name = "No Plan"
        days_remaining = 0
        total_attendance = 0
        pending_payment = 0
        meals_taken = 0
        total_meals = 0

        if subscription:
            plan_name = subscription["plan_name"]
            end_date = subscription["end_date"]

            days_remaining = (end_date - date.today()).days

            # Attendance Calculation
            cursor.execute("""
            SELECT 
                COUNT(*) AS meals_taken,                                                                                                            
                COUNT(DISTINCT date) * 3 AS total_meals
            FROM attendance
            WHERE subscription_id=%s
            """, (subscription["subscription_id"],))

            att = cursor.fetchone()

            meals_taken = att["meals_taken"] or 0
            total_meals = att["total_meals"] or 0

            if total_meals > 0:
                total_attendance = round((meals_taken / total_meals) * 100, 2)
            else:
                total_attendance = 0

            # Sum payments
            cursor.execute("""
                SELECT SUM(amount) AS total
                FROM payments
                WHERE subscription_id = %s
            """, (subscription["subscription_id"],))
            payment = cursor.fetchone()["total"]

            pending_payment = payment if payment else 0

        cursor.close()
        conn.close()

        return render_template(
            "student_dashboard.html",
            plan_name=plan_name,
            days_remaining=days_remaining,
            total_attendance=total_attendance,
            pending_payment=pending_payment,
            username=username,
            meals_taken=meals_taken,   
            total_meals=total_meals 
        )

    return redirect("/")

@app.route("/my_subscription")
def my_subscription():

    if "role" in session and session["role"] == "student":

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student id
        cursor.execute(
            "SELECT user_id FROM users WHERE username=%s",
            (session["username"],)
        )
        student = cursor.fetchone()
        student_id = student["user_id"]

        # ACTIVE PLAN (Paid plan)
        cursor.execute("""
            SELECT s.*, m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            AND s.status='Active'
            AND s.end_date >= CURDATE()
        """, (student_id,))
        active = cursor.fetchone()

        days_left = None
        if active:
            days_left = (active["end_date"] - date.today()).days


        # PENDING REQUEST (waiting for admin approval)
        cursor.execute("""
            SELECT m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            AND s.status='Pending'
        """, (student_id,))
        pending = cursor.fetchone()


        # APPROVED BUT NOT PAID (payment required)
        cursor.execute("""
            SELECT s.subscription_id, m.plan_name, m.price
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            AND s.status='Approved'
        """, (student_id,))
        approved_payment = cursor.fetchone()


        # SUBSCRIPTION HISTORY
        cursor.execute("""
            SELECT m.plan_name, s.start_date, s.end_date, s.status
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            ORDER BY s.subscription_id DESC
        """, (student_id,))
        history = cursor.fetchall()


        # ALL AVAILABLE PLANS
        cursor.execute("SELECT * FROM meal_plans")
        plans = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "my_subscription.html",
            active=active,
            pending=pending,
            approved_payment=approved_payment,
            days_left=days_left,
            history=history,
            plans=plans
        )

    return redirect("/")

@app.route("/buy_plan", methods=["POST"])
def buy_plan():
    if "role" in session and session["role"] == "student":

        plan_id = request.form["plan_id"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student id
        cursor.execute(
            "SELECT user_id FROM users WHERE username=%s",
            (session["username"],)
        )
        student = cursor.fetchone()
        student_id = student["user_id"]

        #  CHECK if already has Pending or Active
        cursor.execute("""
            SELECT * FROM subscriptions
            WHERE student_id=%s
            AND (
                status='Pending'
                OR
                (status='Approved' AND end_date >= CURDATE())
            )
        """, (student_id,))

        existing = cursor.fetchone()

        if existing:
            cursor.close()
            conn.close()
            return redirect("/my_subscription")

        # Get duration
        cursor.execute(
            "SELECT duration_days FROM meal_plans WHERE plan_id=%s",
            (plan_id,)
        )
        plan = cursor.fetchone()
        duration = plan["duration_days"]

        # Insert Pending request
        cursor.execute("""
            INSERT INTO subscriptions
            (student_id, plan_id, start_date, end_date, status)
            VALUES (%s, %s, CURDATE(),
            DATE_ADD(CURDATE(), INTERVAL %s DAY),
            'Pending')
        """, (student_id, plan_id, duration))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/my_subscription")

    return redirect("/")

@app.route("/admin_attendance")
def admin_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT s.subscription_id,
           u.username,
           m.plan_name,

           EXISTS(
               SELECT 1 FROM attendance a
               WHERE a.subscription_id = s.subscription_id
               AND a.date = CURDATE()
               AND a.meal_type = 'Breakfast'
           ) AS breakfast_marked,

           EXISTS(
               SELECT 1 FROM attendance a
               WHERE a.subscription_id = s.subscription_id
               AND a.date = CURDATE()
               AND a.meal_type = 'Lunch'
           ) AS lunch_marked,

           EXISTS(
               SELECT 1 FROM attendance a
               WHERE a.subscription_id = s.subscription_id
               AND a.date = CURDATE()
               AND a.meal_type = 'Dinner'
           ) AS dinner_marked

    FROM subscriptions s
    JOIN users u ON s.student_id = u.user_id
    JOIN meal_plans m ON s.plan_id = m.plan_id

    WHERE LOWER(TRIM(s.status)) = 'active'
    AND s.end_date >= CURDATE()
""")



    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_attendance.html", students=students)

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    subscription_id = request.form["subscription_id"]
    meal_type = request.form["meal_type"]

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO attendance (subscription_id, date, meal_type)
            VALUES (%s, CURDATE(), %s)
        """, (subscription_id, meal_type))

        connection.commit()

    except:
        print("Attendance already marked")

    cursor.close()
    connection.close()

    return redirect("/admin_attendance")


@app.route("/admin_students")
def admin_students():

    if session.get("role") != "admin":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            u.username,
            u.email,
            m.plan_name,
            s.end_date
        FROM subscriptions s
        JOIN users u ON s.student_id = u.user_id
        JOIN meal_plans m ON s.plan_id = m.plan_id
        WHERE LOWER(TRIM(s.status)) = 'active'
        AND s.end_date >= CURDATE()
        ORDER BY s.end_date
    """)

    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_students.html", students=students)

@app.route("/admin_payments")
def admin_payments():

    if session.get("role") != "admin":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Payment list
    cursor.execute("""
        SELECT 
            p.payment_id,
            u.username,
            m.plan_name,
            p.mobile,
            p.amount,
            p.payment_date
        FROM payments p
        JOIN subscriptions s 
            ON p.subscription_id = s.subscription_id
        JOIN users u 
            ON s.student_id = u.user_id
        JOIN meal_plans m
            ON s.plan_id = m.plan_id
        ORDER BY p.payment_date DESC
    """)
    
    payments = cursor.fetchall()

    # Total revenue
    cursor.execute("""
        SELECT SUM(amount) AS total_revenue
        FROM payments
    """)
    
    result = cursor.fetchone()
    total_revenue = result["total_revenue"] if result["total_revenue"] else 0


    # Today's payments
    cursor.execute("""
        SELECT COUNT(*) AS today_payments
        FROM payments
        WHERE payment_date = CURDATE()
    """)
    
    today_payments = cursor.fetchone()["today_payments"]


    # Pending payments
    cursor.execute("""
        SELECT COUNT(*) AS pending_payments
        FROM subscriptions s
        LEFT JOIN payments p 
        ON s.subscription_id = p.subscription_id
        WHERE s.status='Approved'
        AND p.payment_id IS NULL
    """)

    pending_payments = cursor.fetchone()["pending_payments"]


    cursor.close()
    conn.close()

    return render_template(
        "admin_payments.html",
        payments=payments,
        total_revenue=total_revenue,
        today_payments=today_payments,
        pending_payments=pending_payments
    )

@app.route("/student_payment")
def student_payment():

    if session.get("role") != "student":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT 
        s.subscription_id,
        m.plan_name,
        m.price
    FROM subscriptions s
    JOIN meal_plans m ON s.plan_id = m.plan_id
    JOIN users u ON s.student_id = u.user_id
    WHERE u.username = %s
    AND s.status = 'Approved'
    ORDER BY s.subscription_id DESC
    LIMIT 1
    """,(session["username"],))

    plan = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("student_payment.html", plan=plan)


@app.route("/pay_bill", methods=["POST"])
def pay_bill():

    subscription_id=request.form["subscription_id"]
    mobile=request.form["mobile"]
    amount=request.form["amount"]

    conn=get_connection()
    cursor=conn.cursor()

    cursor.execute("""
    INSERT INTO payments
    (subscription_id,mobile,amount,payment_date)
    VALUES(%s,%s,%s,CURDATE())
    """,(subscription_id,mobile,amount))

    cursor.execute("""
    UPDATE subscriptions
    SET status='Active'
    WHERE subscription_id=%s
    """,(subscription_id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/student_dashboard")

@app.route("/mark_payment", methods=["POST"])
def mark_payment():

    if session.get("role") != "admin":
        return redirect("/")

    subscription_id = request.form["subscription_id"]
    mobile = request.form["mobile"]
    amount = request.form["amount"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO payments
        (subscription_id, mobile, amount, payment_date)
        VALUES (%s,%s,%s,CURDATE())
    """,(subscription_id, mobile, amount))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/admin_payments")

@app.route("/student_profile", methods=["GET", "POST"])
def student_profile():

    if session.get("role") != "student":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 Get user
    cursor.execute(
        "SELECT user_id, email FROM users WHERE username=%s",
        (session["username"],)
    )
    user = cursor.fetchone()
    student_id = user["user_id"]

    # 🔹 SAVE / UPDATE PROFILE
    if request.method == "POST":

        name = request.form.get("name")
        father_name = request.form.get("father_name")
        student_phone = request.form.get("student_phone")
        father_phone = request.form.get("father_phone")
        town = request.form.get("town")

        # Check if profile exists
        cursor.execute(
            "SELECT * FROM student_profiles WHERE student_id=%s",
            (student_id,)
        )
        existing = cursor.fetchone()

        if existing:
            # UPDATE
            cursor.execute("""
                UPDATE student_profiles
                SET name=%s,
                    father_name=%s,
                    student_phone=%s,
                    father_phone=%s,
                    town=%s
                WHERE student_id=%s
            """, (name, father_name, student_phone, father_phone, town, student_id))
        else:
            # INSERT
            cursor.execute("""
                INSERT INTO student_profiles
                (student_id, name, father_name, student_phone, father_phone, town)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (student_id, name, father_name, student_phone, father_phone, town))

        conn.commit()

    # 🔹 GET PROFILE
    cursor.execute(
        "SELECT * FROM student_profiles WHERE student_id=%s",
        (student_id,)
    )
    profile = cursor.fetchone()

    # 🔥 🔥 ACTIVE PLAN FIX (MAIN ISSUE SOLVED HERE)
    cursor.execute("""
        SELECT m.plan_name
        FROM subscriptions s
        LEFT JOIN meal_plans m ON s.plan_id = m.plan_id
        WHERE s.student_id=%s
        AND LOWER(TRIM(s.status))='active'
        LIMIT 1
    """, (student_id,))

    plan = cursor.fetchone()

    # 🔹 DEBUG (remove later)
    print("Student ID:", student_id)
    cursor.execute("SELECT * FROM subscriptions WHERE student_id=%s", (student_id,))
    print("Subscriptions:", cursor.fetchall())

    cursor.close()
    conn.close()

    return render_template(
        "student_profile.html",
        profile=profile,
        email=user["email"],
        plan=plan
    )

#logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
