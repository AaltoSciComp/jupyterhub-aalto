"""Test for Jupyter spawning.

This script starts
"""

API = 'http://10.104.184.130:8081/hub/api/'
# This file needs two lines in it: 0th line is token, 1st line is
# username to spawn servers of.  This can be made from the JH Token
# page.
AUTH_DATA_FILE = 'secrets/spawn_test_token.txt'

from collections import defaultdict
import datetime
import dateutil.parser
import json
import logging
import sys
import time

import requests

now = datetime.datetime.now().timestamp()

if '-v' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)
logging.getLogger('requests').setLevel(logging.WARN)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

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
STATUS= { }

# JH version
r = requests.get(API, auth=auth)
r.raise_for_status()
STATUS['jupyterhub_version'] = r.json()['version']


# List all users
r = requests.get(API+'users', auth=auth)
r.raise_for_status()
STATUS['users_active'] = sum([ 1 if user['server'] or user['pending'] else 0 for user in r.json() ])
STATUS['users_total'] = len(r.json())
STATUS['servers_active'] = sum([ len(user['servers']) for user in r.json() ])
active_pod_names = defaultdict(int)
last_active = defaultdict(int)
for user in r.json():
    log.debug(user['servers'])
    last_activity = None
    for name, server in user['servers'].items():
        components = server['state']['pod_name'].split('-')
        if len(components) < 3:
            active_pod_names['generic'] += 1
        else:
            active_pod_names[components[-1]] += 1
        last_ts = dateutil.parser.parse(server['last_activity']).timestamp()
        secs_ago = now - last_ts
        if secs_ago <  300: last_active['5m'] += 1
        if secs_ago < 1800: last_active['30m'] += 1
        if secs_ago < 3600: last_active['1h'] += 1
        if secs_ago < 7200: last_active['2h'] += 1
STATUS['pods_active'] = active_pod_names
STATUS['servers_last_active'] = last_active


r = requests.get(API+'services', auth=auth)
r.raise_for_status()
STATUS['services_active'] = len(r.json())


r = requests.get(API+'proxy', auth=auth)
r.raise_for_status()
log.debug(r.json())
STATUS['proxy_routes_count'] = len(r.json())
last_active = defaultdict(int)
for prefix, route in r.json().items():
    last_ts = dateutil.parser.parse(route['data']['last_activity']).timestamp()
    secs_ago = now - last_ts
    if secs_ago <  300: last_active['5m'] += 1
    if secs_ago < 1800: last_active['30m'] += 1
    if secs_ago < 3600: last_active['1h'] += 1
    if secs_ago < 7200: last_active['2h'] += 1
STATUS['proxy_last_active'] = last_active
    



print(json.dumps(STATUS, indent=4), )
