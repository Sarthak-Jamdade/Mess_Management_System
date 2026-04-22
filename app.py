from flask import Flask, render_template, request, redirect, session
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "mess_secret_key"

client = MongoClient("mongodb://localhost:27017/")
db = client["messDB"]

@app.route("/")
def home():
    return render_template("login.html")

UPLOAD_FOLDER = "static/profile"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = db.users.find_one({
        "username": username,
        "password": password
    })

    if user:
        session["username"] = user["username"]
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

        # check email
        existing_email = db.users.find_one({"email": email})
        if existing_email:
            return "Email already registered. <a href='/register'>Try Again</a>"

        # check username
        existing_username = db.users.find_one({"username": username})
        if existing_username:
            return "Username already taken. <a href='/register'>Try Again</a>"

        # insert user
        result = db.users.insert_one({
            "username": username,
            "email": email,
            "password": password,
            "role": "student"
        })

        user_id = result.inserted_id

        # insert student
        db.students.insert_one({
            "student_id": user_id,
            "name": username,
            "email": email
        })

        return redirect("/")

    return render_template("register.html")


@app.route("/admin_dashboard")
def admin_dashboard():
    if "role" in session and session["role"] == "admin":

        # Total Students
        total_students = db.users.count_documents({
            "role": "student"
        })

        # Total Active Subscriptions
        total_active = db.subscriptions.count_documents({
            "status": "Active"
        })

        # Total Pending Requests
        total_pending = db.subscriptions.count_documents({
            "status": "Pending"
        })

        # Pending Requests (manual JOIN)
        pending_subs = list(db.subscriptions.find({
            "status": "Pending"
        }))

        requests = []

        for sub in pending_subs:
            user = db.users.find_one({"_id": sub["student_id"]})
            plan = db.meal_plans.find_one({"plan_id": sub["plan_id"]})

            requests.append({
                "subscription_id": str(sub["_id"]),
                "username": user["username"] if user else "",
                "email": user["email"] if user else "",
                "plan_name": plan["plan_name"] if plan else "",
                "status": sub["status"]
            })

        return render_template(
            "admin_dashboard.html",
            total_students=total_students,
            total_active=total_active,
            total_pending=total_pending,
            requests=requests
        )

    return redirect("/")

@app.route("/student_dashboard")
def student_dashboard():
    if "role" in session and session["role"] == "student":

        # Get user
        user = db.users.find_one({
            "username": session["username"]
        })

        student_id = user["_id"]

        # -----------------------------
        # 1. GET ACTIVE SUBSCRIPTION
        # -----------------------------
        subscription = db.subscriptions.find_one({
            "student_id": student_id,
            "status": "Active"
        })

        # Default values
        plan_name = "No Plan"
        days_remaining = 0
        total_attendance = 0
        pending_payment = 0
        meals_taken = 0
        total_meals = 0

        if subscription:

            plan = db.meal_plans.find_one({
                "plan_id": subscription["plan_id"]
            })

            if plan:
                plan_name = plan["plan_name"]

            end_date = subscription["end_date"]
            days_remaining = (end_date.date() - datetime.now().date()).days

            # -----------------------------
            # 2. ATTENDANCE
            # -----------------------------
            attendance_records = list(db.attendance.find({
                "subscription_id": subscription["_id"]
            }))

            meals_taken = len(attendance_records)

            unique_days = len(set([a["date"].date() for a in attendance_records]))
            total_meals = unique_days * 3

            if total_meals > 0:
                total_attendance = round((meals_taken / total_meals) * 100, 2)

            # -----------------------------
            # 3. PAYMENTS
            # -----------------------------
            result = list(db.payments.aggregate([
                {"$match": {"subscription_id": subscription["_id"]}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]))

            pending_payment = result[0]["total"] if result else 0

        return render_template(
            "student_dashboard.html",
            plan_name=plan_name,
            days_remaining=days_remaining,
            total_attendance=total_attendance,
            pending_payment=pending_payment,
            username=session["username"],
            meals_taken=meals_taken,
            total_meals=total_meals
        )

    return redirect("/")

@app.route("/my_subscription")
def my_subscription():

    if "role" in session and session["role"] == "student":

        # Get student
        user = db.users.find_one({
            "username": session["username"]
        })
        student_id = user["_id"]

        # ACTIVE PLAN
        active = db.subscriptions.find_one({
            "student_id": student_id,
            "status": "Active"
        })

        days_left = None
        if active:
            days_left = (active["end_date"].date() - datetime.now().date()).days

            plan = db.meal_plans.find_one({
                "plan_id": active["plan_id"]
            })

            if plan:
                active["plan_name"] = plan["plan_name"]

        # PENDING
        pending = db.subscriptions.find_one({
            "student_id": student_id,
            "status": "Pending"
        })

        if pending:
            plan = db.meal_plans.find_one({
                "plan_id": pending["plan_id"]
            })
            if plan:
                pending["plan_name"] = plan["plan_name"]

        # APPROVED (payment required)
        approved_payment = db.subscriptions.find_one({
            "student_id": student_id,
            "status": "Approved"
        })

        if approved_payment:
            plan = db.meal_plans.find_one({
                "plan_id": approved_payment["plan_id"]
            })
            if plan:
                approved_payment["plan_name"] = plan["plan_name"]
                approved_payment["price"] = plan["price"]

        # HISTORY
        history = list(db.subscriptions.find({
            "student_id": student_id
        }))

        for h in history:
            plan = db.meal_plans.find_one({
                "plan_id": h["plan_id"]
            })
            if plan:
                h["plan_name"] = plan["plan_name"]

        # ALL PLANS
        plans = list(db.meal_plans.find())

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

        plan_id = int(request.form["plan_id"])

        user = db.users.find_one({
            "username": session["username"]
        })
        student_id = user["_id"]

        plan = db.meal_plans.find_one({
            "plan_id": plan_id
        })

        start_date = datetime.now()
        end_date = start_date + timedelta(days=plan["duration_days"])

        existing = db.subscriptions.find_one({
            "student_id": student_id,
            "$or": [
                {"status": "Pending"},
                {
                    "status": "Approved",
                    "end_date": {"$gte": datetime.now()}
                }
            ]
        })

        if existing:
            return redirect("/my_subscription")

        db.subscriptions.insert_one({
            "student_id": student_id,
            "plan_id": plan_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": "Pending"
        })

        return redirect("/my_subscription")

    return redirect("/")

@app.route("/pay_bill", methods=["POST"])
def pay_bill():

    subscription_id = request.form.get("subscription_id")
    mobile = request.form["mobile"]
    amount = float(request.form["amount"])

    if not subscription_id:
        return "Subscription ID missing ❌"

    # 1. Insert payment
    db.payments.insert_one({
        "subscription_id": ObjectId(subscription_id),
        "mobile": mobile,
        "amount": amount,
        "payment_date": datetime.now()
    })

    # 2. Update subscription
    db.subscriptions.update_one(
        {"_id": ObjectId(subscription_id)},
        {"$set": {"status": "Active"}}
    )

    return redirect("/student_dashboard")

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    subscription_id = request.form.get("subscription_id")
    meal_type = request.form["meal_type"]

    if not subscription_id:
        return "Subs id Missing"

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    existing = db.attendance.find_one({
        "subscription_id": ObjectId(subscription_id),
        "meal_type": meal_type,
        "date": {"$gte": today_start, "$lt": today_end}
    })

    if not existing:
        db.attendance.insert_one({
            "subscription_id": ObjectId(subscription_id),
            "meal_type": meal_type,
            "date": datetime.now()
        })

    return redirect("/admin_attendance")

@app.route("/approve/<sub_id>")
def approve(sub_id):

    db.subscriptions.update_one(
        {"_id": ObjectId(sub_id)},
        {"$set": {"status": "Approved"}}
    )

    return redirect("/admin_dashboard")

@app.route("/reject/<sub_id>")
def reject(sub_id):

    if "role" in session and session["role"] == "admin":

        db.subscriptions.update_one(
            {"_id": ObjectId(sub_id)},
            {"$set": {"status": "Rejected"}}
        )

        return redirect("/admin_dashboard")

    return redirect("/")

@app.route("/admin_payments")
def admin_payments():

    if session.get("role") != "admin":
        return redirect("/")

    # 1. GET ALL PAYMENTS
    payments_data = list(db.payments.find({}))

    payments = []

    for p in payments_data:
        sub = db.subscriptions.find_one(
            {"_id": p["subscription_id"]}
        )
        user = db.users.find_one(
            {"_id": sub["student_id"]}
        ) if sub else None

        plan = db.meal_plans.find_one(
            {"plan_id": sub["plan_id"]}
        ) if sub else None

        payments.append({
            "payment_id": str(p["_id"]),
            "username": user["username"] if user else "",
            "plan_name": plan["plan_name"] if plan else "",
            "mobile": p.get("mobile", ""),
            "amount": p.get("amount", 0),
            "payment_date": p.get("payment_date")
        })

    # 2. TOTAL REVENUE
    result = list(db.payments.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]))

    total_revenue = result[0]["total"] if result else 0

    # 3. TODAY PAYMENTS
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    today_payments = db.payments.count_documents({
        "payment_date": {"$gte": today_start, "$lt": today_end}
    })

    # 4. PENDING PAYMENTS
    approved_subs = list(db.subscriptions.find({
        "status": "Approved"
    }))

    pending_payments = 0

    for sub in approved_subs:
        payment = db.payments.find_one({
            "subscription_id": sub["_id"]
        })

        if not payment:
            pending_payments += 1

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

    user = db.users.find_one({
        "username": session["username"]
    })

    if not user:
        return redirect("/")

    subscription = db.subscriptions.find_one({
        "student_id": user["_id"],
        "status": "Approved"
    })

    plan = None

    if subscription:
        plan = db.meal_plans.find_one({
            "plan_id": subscription["plan_id"]
        })

    return render_template(
        "student_payment.html",
        plan=plan,
        subscription_id=str(subscription["_id"]) if subscription else ""
    )

@app.route("/admin_attendance")
def admin_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    active_subs = list(db.subscriptions.find({
        "status": "Active"
    }))

    students = []

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    for sub in active_subs:
        user = db.users.find_one({
            "_id": sub["student_id"]
        })

        plan = db.meal_plans.find_one({
            "plan_id": sub["plan_id"]
        })

        breakfast = db.attendance.find_one({
            "subscription_id": sub["_id"],
            "meal_type": "Breakfast",
            "date": {"$gte": today_start, "$lt": today_end}
        })

        lunch = db.attendance.find_one({
            "subscription_id": sub["_id"],
            "meal_type": "Lunch",
            "date": {"$gte": today_start, "$lt": today_end}
        })

        dinner = db.attendance.find_one({
            "subscription_id": sub["_id"],
            "meal_type": "Dinner",
            "date": {"$gte": today_start, "$lt": today_end}
        })

        students.append({
            "subscription_id": str(sub["_id"]),
            "username": user["username"] if user else "",
            "plan_name": plan["plan_name"] if plan else "",
            "breakfast_marked": True if breakfast else False,
            "lunch_marked": True if lunch else False,
            "dinner_marked": True if dinner else False
        })

    return render_template("admin_attendance.html", students=students)

@app.route("/admin_students")
def admin_students():

    if session.get("role") != "admin":
        return redirect("/")

    active_subs = list(db.subscriptions.find({
        "status": "Active"
    }))

    students = []

    for sub in active_subs:
        user = db.users.find_one({
            "_id": sub["student_id"]
        })

        plan = db.meal_plans.find_one({
            "plan_id": sub["plan_id"]
        })

        students.append({
            "username": user["username"] if user else "",
            "email": user["email"] if user else "",
            "plan_name": plan["plan_name"] if plan else "",
            "end_date": sub.get("end_date")
        })

    return render_template("admin_students.html", students=students)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, port=5001)