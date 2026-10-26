"""Local operator console; passwords are read without echo or command-line arguments."""
import argparse,getpass
from pcs_agent.config import load
from pcs_agent.auth import Accounts

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['create-admin','create-user','reset-password']);parser.add_argument('username');parser.add_argument('--config')
    args=parser.parse_args()
    from pathlib import Path
    cfg=load(Path(args.config) if args.config else None)
    password=getpass.getpass('Password (15 or more characters): ')
    if password!=getpass.getpass('Repeat password: '):raise ValueError('Passwords do not match.')
    accounts=Accounts(cfg['data_dir'])
    if args.action=='reset-password':accounts.reset(args.username,password)
    else:accounts.create(args.username,password,'admin' if args.action=='create-admin' else 'user')
    print('Account updated. Existing sessions are revoked on password reset.')
if __name__=='__main__':main()
