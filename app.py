from flask import Flask, request, render_template, redirect, abort, session, flash, make_response
from client_secret import client_secret, initial_html
from db import user_details_collection, onboarding_details_collection, jobs_details_collection, candidate_job_application_collection, chatbot_collection, resume_details_collection, profile_details_collection
from helpers import  query_update_billbot, add_html_to_db, analyze_resume
import os
from datetime import datetime
import requests
import pathlib
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
import uuid
import time

app = Flask(__name__)
app.secret_key = os.environ['APP_SECRET']

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

url_ = os.environ['APP_URL']

GOOGLE_CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
client_secrets_file = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_config(
    client_config=client_secret,
    scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri=f"{url_}/callback"
)

def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)  
        else:
            return function(*args, **kwargs)
    return wrapper

def is_candidate(function):
    def wrapper(*args, **kwargs):
        if "purpose" not in session:
            return abort(500)  
        else:
            purpose = session.get('purpose')
            if purpose == "candidate":
                return function(*args, **kwargs)
            else:
                abort(500, {"message":{"You are not a candidate."}})
    return wrapper

def is_hirer(function):
    def wrapper(*args, **kwargs):
        if "purpose" not in session:
            return abort(500)  
        else:
            purpose = session.get('purpose')
            print(purpose)
            if purpose == "hirer":
                return function(*args, **kwargs)
            else:
                abort(500, {"message":{"You are not a Hirer."}})
    return wrapper

def is_onboarded(function):
    def wrapper(*args, **kwargs):
        onboarded = session.get("onboarded")
        if onboarded:
            return function(*args, **kwargs)
        else:
            return redirect("/dashboard")
    return wrapper


@app.route("/", methods = ['GET'])
def start():
    if session.get('google_id') is None:
        user_name = session.get("name")
        resp = make_response(render_template("index.html", user_name=user_name))
        return resp
    else:
        return redirect("/dashboard")
    
@app.route("/dashboard", methods = ['GET'], endpoint='dashboard')
@login_is_required
def dashboard():
    user_name = session.get("name")
    onboarded = session.get("onboarded")
    user_id = session.get("google_id")
    if onboarded == False:
        return redirect("/onboarding")
    onboarding_details = onboarding_details_collection.find_one({"user_id": user_id},{"_id": 0})
    purpose = onboarding_details.get("purpose")
    resume_built = onboarding_details.get("resume_built")
    if purpose == 'hirer':
        all_jobs = list(jobs_details_collection.find({"user_id": user_id},{"_id": 0}))
        return render_template('hirer_dashboard.html', user_name=user_name, onboarding_details=onboarding_details, all_jobs=all_jobs)
    else:
        if not resume_built: 
            return redirect("/billbot")
        resume_skills = resume_details_collection.find_one({'user_id': user_id}, {'skills': 1})['skills']
        regex_pattern = '|'.join(resume_skills)
        pipeline = [
                 {
        '$match': {
            'status': 'published',
               '$or': [
                {'job_title': {'$regex': regex_pattern, '$options': 'i'}},
                {'job_description': {'$regex': regex_pattern, '$options': 'i'}},
                {'job_topics': {'$regex': regex_pattern, '$options': 'i'}},
            ]  # You may add other conditions to filter jobs if needed
        }
    },
            {
                '$lookup': {
                    'from': 'onboarding_details', 
                    'localField': 'user_id', 
                    'foreignField': 'user_id', 
                    'as': 'user_details'
                }
            }, 
            {
                '$project': {
                    '_id': 0
                }
            }
        ]
        all_jobs = list(jobs_details_collection.aggregate(pipeline))
        all_updated_jobs = []
        for idx, job in enumerate(all_jobs):
            if applied := candidate_job_application_collection.find_one({"job_id": job.get("job_id"),"user_id":  user_id},{"_id": 0}):
                pass
            else:
                all_updated_jobs.append(job)
        profile_details = profile_details_collection.find_one({"user_id": user_id},{"_id": 0})
        return render_template('candidate_dashboard.html', user_name=user_name, onboarding_details=onboarding_details, all_jobs=all_updated_jobs, profile_details=profile_details)
    
@app.route("/applied_jobs", methods = ['GET'], endpoint='applied_jobs')
@login_is_required
@is_candidate
def applied_jobs():
    user_name = session.get("name")
    onboarded = session.get("onboarded")
    user_id = session.get("google_id")
    if onboarded == False:
        return redirect("/onboarding")
    onboarding_details = onboarding_details_collection.find_one({"user_id": user_id},{"_id": 0})
    resume_built = onboarding_details.get("resume_built")
    if not resume_built: 
        return redirect("/billbot")
    pipeline = [
                {"$match": {"user_id": user_id}},
        {
            '$lookup': {
                'from': 'jobs_details', 
                'localField': 'job_id', 
                'foreignField': 'job_id', 
                'as': 'job_details'
            }
        }, 
        {
            '$project': {
                '_id': 0,
                'job_details._id': 0
            }
        }
    ]
    all_applied_jobs = list(candidate_job_application_collection.aggregate(pipeline))
    # return all_applied_jobs
    return render_template('applied_jobs.html', user_name=user_name, onboarding_details=onboarding_details, all_applied_jobs=all_applied_jobs)


@app.route("/profile", methods=['POST'], endpoint='profile_update')
@login_is_required
@is_candidate
def profile_update():
    user_id = session.get("google_id")
    profile_data = dict(request.form)
    profile_details_collection.update_one({"user_id": user_id},{"$set": profile_data})
    return redirect('/dashboard')



@app.route("/login")
def login():
    if session.get('google_id') is None:
        authorization_url, state = flow.authorization_url()
        session["state"] = state
        return redirect(authorization_url)
    else:
        flash({'type':'error', 'data':"Your are already Logged In"})
        return redirect("/")
        

@app.route("/logout", methods = ['GET'])
def logout():
    if "google_id" not in session:
        return redirect("/")
    all_keys = list(session.keys())
    for key in all_keys:
        session.pop(key)
    return redirect("/")

@app.route("/billbot", methods = ['GET', 'POST'], endpoint='chatbot')
@is_candidate
def chatbot():
    user_id = session.get("google_id")
    if onboarding_details := onboarding_details_collection.find_one({"user_id": user_id}, {"_id": 0}):
        phase = onboarding_details.get('phase')
        if phase == "1":
            messages = list(chatbot_collection.find({},{"_id": 0}))
            return render_template('chatbot.html', messages=messages)
        elif phase == "2":
            messages = [{"user":"billbot","msg": "Hi, The right side of your screen will display your resume. You can give me instruction to build it in the chat."},{"user":"billbot","msg": "You can give me information regarding your inroduction, skills, experiences, achievements and projects. I will create a professional resume for you!"}]
            if resume_details := resume_details_collection.find_one({"user_id": user_id},{"_id": 0}):
                resume_html = resume_details.get("resume_html")
                resume_built = session.get("resume_built")
                return render_template('resume_builder.html', messages=messages, resume_html=resume_html, resume_built=resume_built) 
            else:
                abort(500,{"message":"Something went wrong! Contact ADMIN!"})
        

@app.route("/resume_build", methods = ['POST'], endpoint='resume_build')
@is_candidate
def resume_build():
    user_id = session.get("google_id")
    form_data = dict(request.form)
    userMsg = form_data.get("msg")
    html_code = query_update_billbot(user_id, userMsg)
    add_html_to_db(user_id, html_code)
    return str(html_code)

@app.route("/resume_built", methods = ['POST'], endpoint='resume_built')
@is_candidate
def resume_built():
    user_id = session.get("google_id")
    onboarding_details_collection.update_one({"user_id": user_id},{"$set": {"resume_built": True}})
    analyze_resume(user_id)
    return redirect("/dashboard")
  
@app.route("/have_resume", methods = ['POST'], endpoint='have_resume')
@is_candidate
def have_resume():
    user_id = session.get("google_id")
    onboarding_details_collection.update_one({"user_id": user_id}, {"$set": {"phase": "2"}})
    resume_data = {"user_id": user_id,"resume_html":initial_html}
    resume_details_collection.insert_one(resume_data)
    return redirect("/billbot")


@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        abort(500)  # State does not match!

    credentials = flow.credentials
    
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )
    print(id_info)

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    session["email"] = id_info.get("email")
    if user_details := user_details_collection.find_one({"user_id": id_info.get("sub")},{"_id":0}):
        session["onboarded"] = user_details.get("onboarded")
        if onboarding_details := onboarding_details_collection.find_one({"user_id": id_info.get("sub")},{"_id":0}):
            session["purpose"] = onboarding_details.get("purpose")
            purpose = session["purpose"]
            if purpose and purpose == "candidate":
                session["resume_built"] = onboarding_details.get("resume_built")

        
    else:
        user_data = {
            "user_id": id_info.get("sub"),
            "user_name": id_info.get("name"),
            "email": id_info.get("email"),
            "joined_at": datetime.now(),
            "onboarded": False
        }
        session["onboarded"] = user_data.get("onboarded")
        user_details_collection.insert_one(user_data)
    return redirect("/")

@app.route("/onboarding", methods=['GET', 'POST'])
def onboarding():
    if request.method == 'POST':
        user_id = session.get('google_id')
        if  user_id is None:
            abort(401)
        else:
            onboarding_details = dict(request.form)
            onboarding_details['user_id'] = user_id
            if user_details := user_details_collection.find_one({"user_id": user_id},{"_id": 0}):
                if user_details.get("onboarded") == False:
                    purpose = onboarding_details.get("purpose")
                    session['purpose'] = purpose
                    data = {"onboarded": True}
                    if purpose and purpose == "candidate":
                        onboarding_details['phase'] = "1"
                        onboarding_details['resume_built'] = False
                        session['resume_built'] = False
                        profile_data = {
                            "user_id": user_details.get("user_id"),
                            "name": onboarding_details.get("candidate_name"),
                            "email": user_details.get("email")
                        }
                        profile_details_collection.insert_one(profile_data)
                    onboarding_details_collection.insert_one(onboarding_details)
                    user_details_collection.update_one({"user_id": user_id},{"$set":data})
                    session['onboarded'] = True
                    return redirect("/dashboard") 
                else:
                    abort(500, {"message": "User already Onboarded."})
    onboarded = session.get('onboarded')
    if onboarded == True:
        purpose = session.get("purpose")
        return redirect("/dashboard")
    user_name = session.get("name")
    return render_template('onboarding.html', user_name=user_name)
    

@app.route('/create_job',methods=['POST'], endpoint="create_job")
@is_hirer
def create_job():
    user_id = session.get("google_id")
    job_id = str(uuid.uuid4())
    job_details = dict(request.form)
    job_details['user_id'] = user_id
    job_details['job_id'] = job_id
    job_details['status'] = "draft"
    jobs_details_collection.insert_one(job_details)
    return redirect("/dashboard")

@app.route('/edit/job/<string:job_id>', methods=['GET', 'POST'], endpoint="edit_job")
@login_is_required
@is_hirer
def edit_job(job_id):
    user_id = session.get("google_id")
    if request.method == 'POST':
        incoming_details = dict(request.form)
        jobs_details_collection.update_one({"user_id": str(user_id), "job_id": str(job_id)},{"$set": incoming_details})
        return redirect('/dashboard')
    if job_details := jobs_details_collection.find_one({"user_id": str(user_id), "job_id": str(job_id)},{"_id": 0}):
        return render_template("job_details.html", job_details=job_details)
    
@app.route('/delete/job/<string:job_id>', methods=['POST'], endpoint="delete_job")
@login_is_required
@is_hirer
def delete_job(job_id):
    user_id = session.get("google_id")
    if request.method == 'POST':
        jobs_details_collection.delete_one({"user_id": str(user_id), "job_id": str(job_id)})
        return redirect('/dashboard')
    

@app.route('/apply/job/<string:job_id>', methods=['GET', 'POST'], endpoint="apply_job")
@login_is_required
@is_candidate
def apply_job(job_id):
    user_id = session.get("google_id")
    if request.method == 'POST':
        job_apply_data = {
            "job_id": job_id,
            "user_id": user_id,
            "applied_on": datetime.now(),
            "status": "applied",
        }
        candidate_job_application_collection.insert_one(job_apply_data)
        flash("Successfully Applied for the Job. Recruiters will get back to you soon, if you are a good fit.")
        return redirect(f'/apply/job/{job_id}')
    pipeline = [
              {"$match": {"job_id": str(job_id)}},
                {
                    '$lookup': {
                        'from': 'onboarding_details', 
                        'localField': 'user_id', 
                        'foreignField': 'user_id', 
                        'as': 'user_details'
                    }
                }, 
                {
                    '$project': {
                        '_id': 0,
                        'user_details._id': 0
                    }
                }
            ]
    if job_details := list(jobs_details_collection.aggregate(pipeline)):
        job_details = job_details[0]
        if job_details.get("status") == "published":
            if candidate_job_application_collection.find_one({"user_id": user_id, "job_id": job_id},{"_id": 0}):
               applied = True 
            else:
                applied = False
            return render_template("apply_job.html", job_details=job_details, applied=applied)
        else:
            abort(500, {"message": f"JOB with job_id {job_id} not found!"})
    else:
        abort(500, {"message": f"JOB with job_id {job_id} not found!"})

@app.route('/responses/job/<string:job_id>', methods=['GET', 'POST'], endpoint="job_responses")
@login_is_required
@is_hirer
@is_onboarded
def job_responses(job_id):
    pipeline = [
            {
                "$match": {"job_id": job_id}
            },
            {
                '$lookup': {
                    'from': 'onboarding_details', 
                    'localField': 'user_id', 
                    'foreignField': 'user_id', 
                    'as': 'user_details'
                }
            },
           {
        '$project': {
            '_id': 0, 
            'user_details._id': 0
        }
    }
        ]
    all_responses = list(candidate_job_application_collection.aggregate(pipeline))
    return render_template("job_responses.html", job_id=job_id, all_responses=all_responses)