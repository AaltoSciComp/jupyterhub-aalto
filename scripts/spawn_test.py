"""Test for Jupyter spawning.

This script starts
"""

API = 'http://10.104.184.130:8081/hub/api/'
# This file needs two lines in it: 0th line is token, 1st line is
# username to spawn servers of.  This can be made from the JH Token
# page.
AUTH_DATA_FILE = 'secrets/spawn_test_token.txt'

import logging
import os
import time

import requests

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('requests').setLevel(logging.WARN)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

if 'JUPYTERHUB_API_TOKEN' in os.environ:
    # Running as a subservice
    token = os.environ['JUPYTERHUB_API_TOKEN']
    username = os.environ['SPAWN_TEST_USERNAME']
else:
    auth_data = open(AUTH_DATA_FILE).readlines()
    token = auth_data[0].strip()
    username = auth_data[1].strip()

# Automatic authentication class
class TokenAuth(requests.auth.AuthBase):
    def __call__(self, r):
        # Implement my authentication
        r.headers['Authorization'] = 'token %s'%token
        return r
auth = TokenAuth()

# Handle JH polling for slow starts/stops.
def poll_until_pending_done():
    for _ in range(60):
        time.sleep(1)
        log.info('... polling for finish...')
        r = requests.get(API+'users/%s'%username, auth=auth)
        if r.json()['pending'] is None:
            break
    else:
        # We did not break - action still pending
        raise RuntimeError("stopping server still pending")
    return r.json()



########################################

# List all users
r = requests.get(API+'users', auth=auth)

# Check if server currently running and if so, stop it.
log.debug("Checking if running...")
r = requests.get(API+'users/%s'%username, auth=auth)
log.debug(r.json())
if r.json()['server'] is not None:
    # server running
    log.info('Server running, stopping...')
    r = requests.delete(API+'users/%s/server'%username, auth=auth)
    r.raise_for_status()
    if r.status_code != 204:
        r = poll_until_pending_done()
            
            
# Start the server
log.info('Starting server')
r = requests.post(API+'users/%s/server'%username, json={'profile':['2']}, auth=auth)
log.debug(r.text)
r.raise_for_status()
if r.status_code != 201:
    poll_until_pending_done()

# Verify server is running
log.debug("Verifying running...")
r = requests.get(API+'users/%s'%username, auth=auth)
log.debug(r.json())
r.raise_for_status()
server_url = r.json()['server']
assert server_url, "server not running"
log.info('server URL: %s', server_url)

# Server running.  stop it now.
log.info("Stopping...")
r = requests.delete(API+'users/%s/server'%username, auth=auth)
log.debug(r.text)
r.raise_for_status()
if r.status_code != 204:
    poll_until_pending_done()


