"""
Load tests for the courseware student module.
"""

import os
import random
import sys
import time

from locust import Locust, TaskSet, task, events

from warnings import filterwarnings
import MySQLdb as Database

sys.path.append(os.path.dirname(__file__))

from opaque_keys.edx.locator import BlockUsageLocator

import locustsettings

os.environ["DJANGO_SETTINGS_MODULE"] = "locustsettings"

DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_PORT = os.environ.get('DB_PORT')
DB_NAME = os.environ.get('DB_NAME')

class QuestionResponse(TaskSet):
    "Respond to a question in the LMS."

    @task
    def set_many(self):
        "set many load test"

        usage = BlockUsageLocator.from_string('block-v1:HarvardX+SPU27x+2015_Q2+type@html+block@1a1866accf254461aa2df3e0b4238a5f')
        start_time = time.time()
        try:
            self.client.set_many(self.client.user.username, {usage: {"soup": "delicious"}})
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            events.request_failure.fire(request_type="", name="set_many", response_time=total_time, exception=e)
        else:
            total_time = int((time.time() - start_time) * 1000)
            events.request_success.fire(request_type="", name="set_many", response_time=total_time, response_length=0)

    @task
    def get_many(self):
        "get many load test"

        usage = BlockUsageLocator.from_string('block-v1:HarvardX+SPU27x+2015_Q2+type@html+block@1a1866accf254461aa2df3e0b4238a5f')
        start_time = time.time()
        try:
            response = [s for s in self.client.get_many(self.client.user.username, [usage])]
            response_length = sum([len(s.state) for s in response])
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            events.request_failure.fire(request_type="", name="get_many", response_time=total_time, exception=e)
        else:
            total_time = int((time.time() - start_time) * 1000)
            events.request_success.fire(request_type="", name="get_many", response_time=total_time, response_length=0)

class UserStateClientClient(Locust):
    "Locust class for the User State Client."

    task_set = QuestionResponse
    min_wait = 10
    max_wait = 50

    def __init__(self):
        super(UserStateClientClient, self).__init__()

        if self.host is None:
            raise LocustError("You must specify the base host. Either in the host attribute in the Locust class, or on the command line using the --host option.")

        from django.conf import settings
        settings.DATABASES['default']['HOST'] = self.host

        settings.DATABASES['default']['USER'] = DB_USER
        settings.DATABASES['default']['PASSWORD'] = DB_PASSWORD
        if DB_NAME:
            settings.DATABASES['default']['NAME'] = DB_NAME
        if DB_PORT:
            settings.DATABASES['default']['PORT'] = DB_PORT

        import courseware.user_state_client as user_state_client
        from student.tests.factories import UserFactory

        # Without this, the greenlets will halt for database warnings
        filterwarnings('ignore', category = Database.Warning)

        self.client = user_state_client.DjangoXBlockUserStateClient(user=UserFactory.create())
