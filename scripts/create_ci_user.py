#!/usr/bin/env python3
"""Script to create a CI user in the database

Can be run as a standalone script or as a service in JupyterHub."""

import json
import os
from typing import Any, Optional, Union

from tornado.httpclient import (
    HTTPClient,
    HTTPClientError,
    HTTPRequest,
    HTTPResponse,
)
from tornado.ioloop import IOLoop
from tornado.log import app_log
from tornado.options import define, options, parse_command_line


class UserCreator:
    def __init__(self, api_url: str, api_token: str, token_note: Optional[str] = None):
        self.api_url = api_url
        self.api_token = api_token

        self._create_user(options.username)
        if token_note:
            # This is not actually needed after all, but left here for reference
            self._create_token(options.username, token_note)

    def _request(
        self,
        path: str,
        method: str = "GET",
        body: Optional[Union[bytes, str]] = None,
        expect_code: Optional[int] = None,
    ) -> HTTPResponse:
        """Make a request to the JupyterHub API"""
        auth_header = {"Authorization": f"token {self.api_token}"}
        req = HTTPRequest(
            method=method,
            url=f"{self.api_url}/{path}",
            headers=auth_header,
            body=body,
        )

        client = HTTPClient()
        try:
            response = client.fetch(req)
        except HTTPClientError as e:
            if e.response:
                if expect_code and e.response.code == expect_code:
                    return e.response
                if e.response.code == 403:
                    app_log.error("Invalid JupyterHub API token.")
                else:
                    app_log.error(f"HTTP error for {path}: {e}")
                    app_log.error(f"Response: {e.response.body.decode()}")
                # Raise the response's exception
                e.response.rethrow()
            else:
                app_log.error(f"HTTP error for {path}: {e}")
            raise
        except Exception as e:
            app_log.error(f"Generic error {path}: {e}")
            raise
        client.close()

        return response

    def _create_user(self, username: str):
        """Create a user in the database"""
        response = self._request(
            f"users/{options.username}",
            method="GET",
            expect_code=404,
        )
        if response.code == 200:
            # User already exists
            return

        app_log.info(f"User {options.username} does not exist, creating")

        response = self._request(
            f"users/{username}",
            method="POST",
            body="",
        )
        app_log.info(f"User {options.username} created")

    def _create_token(self, username: str, token_note: str):
        """Create a token for the user"""
        response = self._request(
            f"users/{options.username}/tokens",
            method="GET",
        )
        data: dict[str, Any] = json.loads(response.body.decode())

        if any([x["note"] == token_note for x in data["api_tokens"]]):
            # Token already exists
            return

        app_log.info(f"Token {token_note} does not exist, creating")

        body = json.dumps(
            {
                "note": token_note,
            }
        )
        response = self._request(f"users/{username}/tokens", method="POST", body=body)
        app_log.info(f"Token {token_note} created")


def main():
    define(
        "url",
        help="JupyterHub API URL",
        type=str,
        default=os.environ["JUPYTERHUB_API_URL"],
    )
    define(
        "username",
        help="Username to create",
        type=str,
    )
    define(
        "note",
        help="Note for the API token. If left undefined, no token is created",
        type=str,
    )
    define(
        "keep",
        help="Keep the service alive",
        type=bool,
    )
    parse_command_line()
    if not options.username:
        raise ValueError("Username must be specified")

    UserCreator(options.url, os.environ["JUPYTERHUB_API_TOKEN"], options.note)

    if options.keep:
        # Start an endless loop so that JupyterHub doesn't keep restarting the script
        loop = IOLoop.current()
        loop.start()


if __name__ == "__main__":
    main()
