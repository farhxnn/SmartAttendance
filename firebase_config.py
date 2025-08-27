# firebase_config.py
import pyrebase
import os  # Make sure to import os

firebaseConfig = {
    "apiKey": os.environ.get("FIREBASE_API_KEY"),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.environ.get("FIREBASE_DATABASE_URL"),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID"),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET"),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
    "appId": os.environ.get("FIREBASE_APP_ID")
}

# Initialize Firebase
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()   # Firebase Authentication
db = firebase.database() # Firebase Realtime Database
storage = firebase.storage() # Firebase Storage (optional)