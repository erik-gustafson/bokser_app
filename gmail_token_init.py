"""Interactive Gmail authorization; writes an authorized-user JSON token."""
import csv
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

SCOPES = ["https://mail.google.com/"]


def validate_target(path):
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("GMAIL_TOKEN_PATH must end in .json; existing pickle files are not converted here")
    if path.is_symlink():
        raise ValueError("Token symlinks are not supported")
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Token must be a regular file with one link")
    return path


def restrict_windows_file(path):
    # Numeric SID avoids localized account names and shell interpolation.
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True, capture_output=True, text=True,
    )
    row = next(csv.reader(io.StringIO(result.stdout)))
    sid = row[-1].strip()
    if not sid.startswith("S-1-") or any(c not in "S-0123456789" for c in sid):
        raise ValueError("Unable to resolve current Windows identity")
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
        check=True, capture_output=True, text=True,
    )


def write_token(path, value):
    path = validate_target(path)
    text = json.dumps(value, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError("Token parent must be a directory")
    if os.name != "nt" and (
        parent.st_mode & 0o022 or parent.st_uid not in (0, os.getuid())
    ):
        raise ValueError("Token parent must be owned and not writable by others")
    fd, name = tempfile.mkstemp(prefix=".gmail-json-", dir=path.parent)
    try:
        # Apply the private file ACL before placing any credential bytes in it.
        if os.name == "nt":
            restrict_windows_file(Path(name))
        else:
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        validate_target(path)
        os.replace(name, path)
        name = None
    finally:
        if fd is not None:
            os.close(fd)
        if name is not None:
            Path(name).unlink(missing_ok=True)


def main():
    token_file = validate_target(os.environ["GMAIL_TOKEN_PATH"])
    credentials_file = os.environ["GMAIL_CREDENTIALS_PATH"]
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    if not creds.refresh_token:
        raise ValueError("Authorization did not return a refresh token; token was not saved")
    write_token(token_file, json.loads(creds.to_json()))
    print("Authorized-user JSON token saved. No credential values displayed.")


if __name__ == "__main__":
    main()
