import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://mail.google.com/",
]

CREDENTIALS_FILE = os.environ["GMAIL_CREDENTIALS_PATH"]
TOKEN_FILE = os.environ["GMAIL_TOKEN_PATH"]


flow = InstalledAppFlow.from_client_secrets_file(
    CREDENTIALS_FILE,
    SCOPES,
)

creds = flow.run_local_server(port=0)

with open(TOKEN_FILE, "wb") as token:
    pickle.dump(creds, token)

print(f"Token saved to {TOKEN_FILE}")
