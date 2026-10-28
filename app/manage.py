"""Local administrator CLI. Passwords are entered privately, never in arguments."""
import argparse
import getpass
import hashlib
import secrets
from app.main import connect

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['add-user','reset-password']);parser.add_argument('username');args=parser.parse_args()
    password=getpass.getpass('Password (12+ characters): ')
    if len(password)<12:raise SystemExit('Use at least 12 characters.')
    if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords differ.')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
    with connect() as db:
        exists=db.execute('SELECT 1 FROM users WHERE username=?',(args.username,)).fetchone()
        if args.command=='add-user' and exists:raise SystemExit('User already exists. Use reset-password.')
        if args.command=='reset-password' and not exists:raise SystemExit('User does not exist.')
        db.execute('INSERT OR REPLACE INTO users VALUES(?,?,?)',(args.username,salt.hex(),digest))
        db.execute('DELETE FROM sessions WHERE username=?',(args.username,))
    print('Account saved.')

if __name__=='__main__':main()
