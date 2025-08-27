from firebase_config import auth

# Test creating a user (temporary)
try:
    user = auth.create_user_with_email_and_password("testuser@gmail.com", "Test1234")
    print("Firebase connected! User created:", user['email'])
except Exception as e:
    print("Error:", e)
