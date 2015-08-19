"""
Load tests for the courseware student module.
"""

import os
import random
import sys
import time

from locust import Locust, TaskSet, task, events, web
from locust.exception import LocustError

from warnings import filterwarnings
import MySQLdb as Database

sys.path.append(os.path.dirname(__file__))

from opaque_keys.edx.locator import BlockUsageLocator

import locustsettings

os.environ["DJANGO_SETTINGS_MODULE"] = "locustsettings"

DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')
DB_NAME = os.environ.get('DB_NAME')

class QuestionResponse(TaskSet):
    "Respond to a question in the LMS."

    @task
    def set_many(self):
        "set many load test"
        usage = BlockUsageLocator.from_string('block-v1:HarvardX+SPU27x+2015_Q2+type@html+block@1a1866accf254461aa2df3e0b4238a5f')
        self.client.set_many(self.client.username(), {usage: {"soup": "delicious"}})

    @task
    def get_many(self):
        "get many load test"
        usage = BlockUsageLocator.from_string('block-v1:HarvardX+SPU27x+2015_Q2+type@html+block@1a1866accf254461aa2df3e0b4238a5f')
        response = [s for s in self.client.get_many(self.client.username(), [usage])]


class UserStateClientClient(Locust):
    "Locust class for the User State Client."

    task_set = QuestionResponse
    min_wait = 1000
    max_wait = 5000

    def __init__(self):
        super(UserStateClientClient, self).__init__()

        from django.conf import settings

        if DB_USER is None or DB_PASSWORD is None or DB_HOST is None:
            raise LocustError("You must specify the username, password and host for the database as environment variables DB_USER, DB_PASSWORD and DB_HOST, respectively.")

        settings.DATABASES['default']['HOST'] = DB_HOST
        settings.DATABASES['default']['USER'] = DB_USER
        settings.DATABASES['default']['PASSWORD'] = DB_PASSWORD
        if DB_NAME:
            settings.DATABASES['default']['NAME'] = DB_NAME
        if DB_PORT:
            settings.DATABASES['default']['PORT'] = DB_PORT

        import courseware.user_state_client as user_state_client
        from student.tests.factories import UserFactory

        class UserStateClient:
            def __init__(self, user):
                self._client = user_state_client.DjangoXBlockUserStateClient(user)

            def username(self):
                return self._client.user.username

            def __getattr__(self, name):
                func = getattr(self._client, name)
                def wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        total_time = int((time.time() - start_time) * 1000)
                        events.request_failure.fire(
                                request_type="DjangoXBlockUserStateClient",
                                name=name,
                                response_time=total_time,
                                exception=e)
                    else:
                        total_time = int((time.time() - start_time) * 1000)
                        events.request_success.fire(
                                request_type="DjangoXBlockUserStateClient",
                                name=name,
                                response_time=total_time,
                                response_length=0)
                        return result
                return wrapper


        # Without this, the greenlets will halt for database warnings
        filterwarnings('ignore', category = Database.Warning)

        self.client = UserStateClient(user=UserFactory.create())


@web.app.route("/set_params", methods=['GET', 'POST'])
def set_params():
    global DB_USER, DB_PASSWORD, DB_PORT, DB_HOST, DB_NAME
    if web.request.method == 'POST':
        DB_USER = web.request.form['username']
        if len(web.request.form['password']) > 0:
            DB_PASSWORD = web.request.form['password']
        DB_PORT = web.request.form['port']
        DB_NAME = web.request.form['name']
        DB_HOST = web.request.form['host']
    return '''
<html>
<form method=post>
<table>
<tr><td>Username</td><td><input type=text name=username value=%s></td></tr>
<tr><td>Password</td><td><input type=password name=password></td></tr>
<tr><td>Port</td><td><input type=text name=port value=%s></td></tr>
<tr><td>Database Name</td><td><input type=text name=name value=%s></td></tr>
<tr><td>Host</td><td><input type=text name=host value=%s></td></tr>
<tr><td colspan=2><input type=submit></td></tr>
</table>
</form>
</html>
''' % (DB_USER,
       DB_PORT or locustsettings.DATABASES['default']['PORT'],
       DB_NAME or locustsettings.DATABASES['default']['NAME'],
       DB_HOST)
