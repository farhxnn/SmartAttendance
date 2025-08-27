import pyrebase
import os
import json

# Get the JSON string of the credentials from the environment variable
service_account_json_str = os.environ.get("FIREBASE_CREDENTIALS_JSON")

if not service_account_json_str:
    raise ValueError("FIREBASE_CREDENTIALS_JSON environment variable not set.")

# Convert the JSON string into a Python dictionary
service_account_config = json.loads(service_account_json_str)

config = {
    # Use the service account for authentication
    "serviceAccount": service_account_config,
    # The databaseURL is still needed
    "databaseURL": os.environ.get("FIREBASE_DATABASE_URL")
}

# Initialize Firebase
firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()
storage = firebase.storage()
