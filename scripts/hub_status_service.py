"""Test for Jupyter spawning.

This script starts
"""

API = 'http://localhost:8081/hub/api/'
# This file needs two lines in it: 0th line is token, 1st line is
# username to spawn servers of.  This can be made from the JH Token
# page.
AUTH_DATA_FILE = 'secrets/spawn_test_token.txt'

import asyncio
from collections import defaultdict
import copy
import datetime
import dateutil.parser
import json
import logging
import os
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests

INTERVAL_SPAWN_ATTEMPT = 60
INTERVAL_SPAWN_LIMIT = 130

LAST_SUCCESSFUL_SPAWN_TIME = None
LAST_SUCCESSFUL_SPAWN_ATTEMPT_TIME = None
if '-v' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.WARN)
logging.getLogger('requests').setLevel(logging.WARN)
log = logging.getLogger('test_spawn')
log.setLevel(logging.WARN)


# Automatic authentication class for requests
class TokenAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        # Implement my authentication
        r.headers['Authorization'] = 'token %s'%self.token
        return r

def get_requests(path):
    r = requests.get(API+path, auth=auth)
    r.raise_for_status()
    return r.json()


# Handle JH polling for slow starts/stops.
def poll_until_pending_done(get):
    for _ in range(60):
        time.sleep(1)
        log.info('... polling for finish...')
        r = get(API+'users/%s'%username, auth=auth)
        if r['pending'] is None:
            break
    else:
        # We did not break - action still pending
        raise RuntimeError("stopping server still pending")
    return r.json()



########################################
def get_stats(get):
    now = datetime.datetime.now().timestamp()
    STATUS= { }

    # JH version
    r = get('')
    #STATUS['jupyterhub_version'] = r['version']


    # List all users
    r = get('users')
    STATUS['users_active'] = sum([ 1 if user['server'] or user['pending'] else 0 for user in r ])
    STATUS['users_total'] = len(r)
    STATUS['servers_active'] = sum([ len(user['servers']) for user in r ])
    STATUS['servers_pending'] = sum([ 1 if user['pending'] else 0 for user in r ])
    active_pod_names = defaultdict(int)
    last_active = {'le_005':0, 'le_010':0, 'le_015':0, 'le_020':0, 'le_030':0, 'le_060':0, 'le_120':0,}
    user_last_active = copy.deepcopy(last_active)
    user_last_active.update({'le_360':0, 'le_1440':0, 'le_10080':0})
    server_age = copy.deepcopy(last_active)
    server_age.update({'le_180': 0, 'le_240': 0, 'le_300': 0})
    def increment_bins(data, value):
        """Go through dict 'data' and increment counters.

        Key format: 'NNNm' (number of minutes)."""
        for key in data:
            if secs_ago < int(key[3:])*60:
                data[key] += 1
    for user in r:
        log.debug(user['servers'])
        # Track user activity
        if user['last_activity']:
            last_ts = dateutil.parser.parse(user['last_activity']).timestamp()
            secs_ago = now - last_ts
            increment_bins(user_last_active, secs_ago)
        # Track server activity
        for name, server in user['servers'].items():
            components = server['state']['pod_name'].split('-', 2)
            if len(components) < 3:
                active_pod_names['generic'] += 1
            else:
                active_pod_names[components[-1]] += 1
            last_ts = dateutil.parser.parse(server['last_activity']).timestamp()
            secs_ago = now - last_ts
            increment_bins(last_active, secs_ago)
            if server['started']:
                start_ts = dateutil.parser.parse(server['started']).timestamp()
                secs_ago = now - start_ts
                increment_bins(server_age, secs_ago)

        # Track server start time
        # --> server['started']
    STATUS['pods_active'] = active_pod_names
    STATUS['servers_last_active'] = last_active
    STATUS['servers_age'] = server_age
    STATUS['users_last_active'] = user_last_active
    if LAST_SUCCESSFUL_SPAWN_TIME:
        STATUS['spawn_test_last_successful'] = now - LAST_SUCCESSFUL_SPAWN_TIME
        STATUS['spawn_test_last_successful_ts'] = LAST_SUCCESSFUL_SPAWN_TIME
        STATUS['spawn_test_successful'] = (now - LAST_SUCCESSFUL_SPAWN_TIME) < INTERVAL_SPAWN_LIMIT
    else:
        STATUS['spawn_test_last_successful'] = None
        STATUS['spawn_test_last_successful_ts'] = None
        STATUS['spawn_test_successful'] = 0
    STATUS['spawn_test_last_attempt_ts'] = LAST_SUCCESSFUL_SPAWN_ATTEMPT_TIME



    r = get('services')
    STATUS['services_active'] = len(r)


    r = get('proxy')
    log.debug(r)
    STATUS['proxy_routes_count'] = len(r)
    last_active = {'le_005':0, 'le_015':0, 'le_030':0, 'le_060':0, 'le_120':0}
    for prefix, route in r.items():
        last_ts = dateutil.parser.parse(route['data']['last_activity']).timestamp()
        secs_ago = now - last_ts
        increment_bins(last_active, secs_ago)
    STATUS['proxy_last_active'] = last_active

    return STATUS

async def test_spawn():
    global LAST_SUCCESSFUL_SPAWN_TIME, LAST_SUCCESSFUL_SPAWN_ATTEMPT_TIME
    LAST_SUCCESSFUL_SPAWN_ATTEMPT_TIME = datetime.datetime.now().timestamp()
    print("Testing spawn", file=sys.stdout)
    log.debug("Testing spawn")
    try:
        os.environ['SPAWN_TEST_USERNAME'] = 'cistudent1'
        p = await asyncio.create_subprocess_exec('python3', '/srv/jupyterhub/spawn_test.py',
                                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,)
        stdout, _not_stderr = await p.communicate()
        ret = p.returncode
        if ret != 0:
            log.error("Spawn test failed!")
            log.error(stdout)
            return
    except:
        import traceback
        log.error(traceback.format_exc().decode())
        return False
    LAST_SUCCESSFUL_SPAWN_TIME = datetime.datetime.now().timestamp()
    return True






def make_prom_line(key, val, labels={}):
    label_list = []
    for l_key, l in labels.items():
        if isinstance(l, str) and l.startswith('le_'):
            # corvert "le_30" to le="30" for use in histograms
            l_key = 'le'
            l = l[3:]
        label_list.append('{}="{}"'.format(l_key, l))

    label_list_str = ",".join(label_list)
    if val is True: val=1
    if val is False: val=0
    if val is None: val=0
    return "jhub_%s{%s} %s\n"%(key, label_list_str, val)

if __name__ == '__main__':
    if 'JUPYTERHUB_API_TOKEN' in os.environ:
        # Running as a service
        api_token = os.environ['JUPYTERHUB_API_TOKEN']
        auth_header = {'Authorization': 'token %s' % api_token}

        ##########
        from tornado.httpclient import AsyncHTTPClient, HTTPRequest
        # API = os.environ['JUPYTERHUB_API_URL']+'/'
        client = AsyncHTTPClient()
        def get(path):
            req = HTTPRequest(
                url=API+path,
                headers=auth_header,
            )
            return json.loads(client.fetch(API+req).body.decode('utf8', 'replace'))
        ##########
        auth = TokenAuth(api_token)
        get = get_requests


        from tornado.ioloop import IOLoop, PeriodicCallback
        from tornado.httpserver import HTTPServer
        from tornado.web import RequestHandler, Application, authenticated
        from jupyterhub.services.auth import HubAuthenticated
        class WhoAmIHandler(HubAuthenticated, RequestHandler):
            #@authenticated
            def get(self):
                # Test for admin if requested...
                #user_model = self.get_current_user()
                #if not user_model['admin']:
                #    self.write(json.dumps({'error':'Not authenticated'}))
                #    return

                STATUS = get_stats(get)
                if self.get_query_argument("type", default=None) == "prometheus":
                    self.set_header('content-type', 'text/plain')
                    output = ""
                    for key, val in STATUS.items():
                        if isinstance(val, dict):
                            for dict_key, dict_val in val.items():
                                output += make_prom_line(key, dict_val, labels={"sub_type": dict_key})
                        else:
                            output += make_prom_line(key, val)
                    self.write(output)

                else:
                    self.set_header('content-type', 'application/json')
                    self.write(json.dumps(STATUS, indent=1, sort_keys=True))

        app = Application([
                  (os.environ['JUPYTERHUB_SERVICE_PREFIX'] + '/?', WhoAmIHandler),
                  (r'.*', WhoAmIHandler),
              ])

        http_server = HTTPServer(app)
        #url = urlparse(os.environ['JUPYTERHUB_SERVICE_URL'])
        url = urlparse('http://0.0.0.0:36541')
        http_server.listen(url.port, url.hostname)

        # Background thread that tests spawning.
        pc = PeriodicCallback(test_spawn, 1e3 * INTERVAL_SPAWN_ATTEMPT)
        pc.start()
        # But do it right now, too...
        IOLoop.current().add_callback(test_spawn)

        IOLoop.current().start()



    else:
        auth_data = open(AUTH_DATA_FILE).readlines()
        token = auth_data[0].strip()
        auth = TokenAuth(token)


        STATUS = get_stats(get_requests)

        print(json.dumps(STATUS, indent=4, sort_keys=True), )
