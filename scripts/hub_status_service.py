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
import os
import sys
import time
from urllib.parse import urlparse

import requests

now = datetime.datetime.now().timestamp()

if '-v' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)
logging.getLogger('requests').setLevel(logging.WARN)
log = logging.getLogger(__name__)
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
    STATUS= { }

    # JH version
    r = get('')
    STATUS['jupyterhub_version'] = r['version']


    # List all users
    r = get('users')
    STATUS['users_active'] = sum([ 1 if user['server'] or user['pending'] else 0 for user in r ])
    STATUS['users_total'] = len(r)
    STATUS['servers_active'] = sum([ len(user['servers']) for user in r ])
    active_pod_names = defaultdict(int)
    last_active = defaultdict(int)
    for user in r:
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


    r = get('services')
    STATUS['services_active'] = len(r)


    r = get('proxy')
    log.debug(r)
    STATUS['proxy_routes_count'] = len(r)
    last_active = defaultdict(int)
    for prefix, route in r.items():
        last_ts = dateutil.parser.parse(route['data']['last_activity']).timestamp()
        secs_ago = now - last_ts
        if secs_ago <  300: last_active['5m'] += 1
        if secs_ago < 1800: last_active['30m'] += 1
        if secs_ago < 3600: last_active['1h'] += 1
        if secs_ago < 7200: last_active['2h'] += 1
    STATUS['proxy_last_active'] = last_active

    return STATUS





if __name__ == '__main__':
    if 'JUPYTERHUB_API_TOKEN' in os.environ:
        # Running as a service
        api_token = os.environ['JUPYTERHUB_API_TOKEN']
        auth_header = {'Authorization': 'token %s' % api_token}

        print(os.environ)
        ##########
        from tornado.httpclient import AsyncHTTPClient, HTTPRequest
        API = os.environ['JUPYTERHUB_API_URL']+'/'
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


        from tornado.ioloop import IOLoop
        from tornado.httpserver import HTTPServer
        from tornado.web import RequestHandler, Application, authenticated
        from jupyterhub.services.auth import HubAuthenticated
        class WhoAmIHandler(HubAuthenticated, RequestHandler):
            #@authenticated
            def get(self):
                self.set_header('content-type', 'application/json')
                # Test for admin if requested...
                #user_model = self.get_current_user()
                #if not user_model['admin']:
                #    self.write(json.dumps({'error':'Not authenticated'}))
                #    return
                STATUS = get_stats(get)
                self.write(json.dumps(STATUS, indent=1, sort_keys=True))

        app = Application([
                  (os.environ['JUPYTERHUB_SERVICE_PREFIX'] + '/?', WhoAmIHandler),
                  (r'.*', WhoAmIHandler),
              ])

        http_server = HTTPServer(app)
        #url = urlparse(os.environ['JUPYTERHUB_SERVICE_URL'])
        url = urlparse('http://0.0.0.0:36541')
        http_server.listen(url.port, url.hostname)
        IOLoop.current().start()



    else:
        auth_data = open(AUTH_DATA_FILE).readlines()
        token = auth_data[0].strip()
        auth = TokenAuth(token)


        STATUS = get_stats(get_requests)

        print(json.dumps(STATUS, indent=4, sort_keys=True), )
