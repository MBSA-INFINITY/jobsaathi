from flask import Flask, request, render_template, redirect, abort, session, flash, make_response
from helpers import query_update_billbot, add_html_to_db, get_resume_html_db
from client_secret import client_secret, initial_html
from db import user_details_collection, resume_details_collection, onboarding_details_collection, jobs_details_collection
import os
from datetime import datetime
import requests
import pathlib
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests

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
    if purpose == 'hirer':
        all_jobs = list(jobs_details_collection.find({"user_id": user_id},{"_id": 0}))
        return render_template('dashboard.html', user_name=user_name, onboarding_details=onboarding_details, all_jobs=all_jobs)
    else:
        return render_template('dashboard.html', user_name=user_name, onboarding_details=onboarding_details)



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
    session.pop("google_id")
    session.pop("name")
    return redirect("/")


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
                    onboarding_details_collection.insert_one(onboarding_details)
                    session['purpose'] = onboarding_details.get("purpose")
                    user_details_collection.update_one({"user_id": user_id},{"$set":{"onboarded": True}})
                    session['onboarded'] = True
                    return redirect("/dashboard")
                else:
                    abort(500, {"message": "User already Onboarded."})
    else:
        onboarded = session.get('onboarded')
        if onboarded == True:
            return redirect("/dashboard")
        user_name = session.get("name")
        return render_template('onboarding.html', user_name=user_name)
    

@app.route('/create_job',methods=['POST'], endpoint="create_job")
@is_hirer
def create_job():
    user_id = session.get("google_id")
    job_details = dict(request.form)
    job_details['user_id'] = user_id
    job_details['status'] = "draft"
    jobs_details_collection.insert_one(job_details)
    return redirect("/dashboard")