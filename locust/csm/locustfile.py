"""
Load tests for the courseware student module.
"""

import logging
import numpy
import os
import random
import string
import sys
import time

from locust import Locust, TaskSet, task, events, web
from locust.exception import LocustError

from warnings import filterwarnings
import MySQLdb as Database

sys.path.append(os.path.dirname(__file__))

import locustsettings

os.environ["DJANGO_SETTINGS_MODULE"] = "locustsettings"

import courseware.user_state_client as user_state_client
from student.tests.factories import UserFactory
from opaque_keys.edx.locator import BlockUsageLocator, CourseLocator


LOG = logging.getLogger(__file__)
RANDOM_CHARACTERS = [random.choice(string.printable) for __ in xrange(1000)]


class UserStateClient(object):
    '''A wrapper class around DjangoXBlockUserStateClient. This does
    two things that the original class does not do:
    * It reports statistics meaningfully to Locust.
    * It provides convenience methods for load-testing (at the moment,
      this is only a method "username" which returns the username
      associated with the client instance).
    '''

    def __init__(self, user):
        '''Constructor. The argument 'user' is passed to the
        DjangoXBlockUserStateClient constructor.'''
        self._client = user_state_client.DjangoXBlockUserStateClient(user)

    @property
    def username(self):
        "Convenience method. Returns the username associated with the client."
        return self._client.user.username

    def __getattr__(self, name):
        "Wraps around client methods and reports stats to locust."
        func = getattr(self._client, name)

        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                end_time = time.time()
                total_time = (end_time - start_time) * 1000
                LOG.warning("Request Failed", exc_info=True)
                events.request_failure.fire(
                    request_type="DjangoXBlockUserStateClient",
                    name=name,
                    response_time=total_time,
                    start_time=start_time,
                    end_time=end_time,
                    exception=e
                )
            else:
                end_time = time.time()
                total_time = (end_time - start_time) * 1000
                events.request_success.fire(
                    request_type="DjangoXBlockUserStateClient",
                    name=name,
                    response_time=total_time,
                    start_time=start_time,
                    end_time=time.time(),
                    response_length=0
                )
                return result
        return wrapper


class CSMLoadModel(TaskSet):
    """
    Generate load for courseware.StudentModule using the model defined here:
    https://openedx.atlassian.net/wiki/display/PLAT/CSM+Loadtest+Request+Modelling
    """

    def __init__(self, *args, **kwargs):
        super(CSMLoadModel, self).__init__(*args, **kwargs)
        self.course_key = CourseLocator('org', 'course', 'run')
        self.usages_with_data = set()

    def _gen_field_count(self):
        choice = numpy.random.random_sample()
        if choice <= .45:
            return 1
        elif choice <= .9:
            return 2
        elif choice <= .99:
            return 3
        elif choice <= .999:
            return 4
        else:
            return 5

    def _gen_block_type(self):
        return random.choice(['problem', 'html', 'sequence', 'vertical'])

    def _gen_block_data(self):
        target_serialized_size = int(numpy.random.pareto(a=0.262) + 2)
        num_fields = self._gen_field_count()

        if target_serialized_size == 2:
            return {}
        else:
            # A serialized field looks like: `"key": "value",`.
            # We'll use a standard set of single characters for keys (so that
            # our data overlaps). So, we need 1 char for the key, 6 for the syntax,
            # and the rest goes to the value.
            data_per_field = max(target_serialized_size // num_fields - 6, 0)
            return {
                str(field): (RANDOM_CHARACTERS * (data_per_field // 1000 + 1))[:data_per_field]
                for field in range(num_fields)
            }

    def _gen_num_blocks(self):
        return int(numpy.random.pareto(a=2.21) + 1)

    def _gen_usage_key(self):
        return BlockUsageLocator(
            self.course_key,
            self._gen_block_type(),
            # We've seen at most 1000 blocks requested in a course, so we'll
            # generate at most that many different indexes.
            str(numpy.random.randint(0, 1000)),
        )

    @task(2)
    def get_many(self):
        block_count = self._gen_num_blocks()
        if block_count > len(self.usages_with_data):
            self.set_many()
        else:
            # TODO: This doesn't accurately represent queries which would retrieve
            # data from StudentModules with no state, or usages with no StudentModules
            self.client.get_many(
                self.client.username,
                random.sample(self.usages_with_data, block_count)
            )

    @task(1)
    def set_many(self):
        usage_key = self._gen_usage_key()
        self.client.set_many(self.client.username, {usage_key: self._gen_block_data()})
        self.usages_with_data.add(usage_key)


class UserStateClientClient(Locust):
    "Locust class for the User State Client."

    task_set = CSMLoadModel
    min_wait = 1000
    max_wait = 5000

    def __init__(self):
        '''Constructor. DATABASE environment variables must be set
        (via locustsetting.py) prior to constructing this object.'''
        super(UserStateClientClient, self).__init__()

        # Without this, the greenlets will halt for database warnings
        filterwarnings('ignore', category=Database.Warning)

        self.client = UserStateClient(user=UserFactory.create())


# Help the template loader find our template.
web.app.jinja_loader.searchpath.append(
    os.path.join(os.path.dirname(__file__), 'templates'))


@web.app.route("/set_params", methods=['GET', 'POST'])
def set_params():
    '''Convenience method; creates a page (via flask) for setting
    database parameters when locust's web interface is enabled.'''
    if web.request.method == 'POST':
        if len(web.request.form['PASSWORD']) > 0:
            locustsettings.DATABASES['default']['PASSWORD'] \
                = web.request.form['PASSWORD']
        for key in ['USER', 'PORT', 'NAME', 'HOST']:
            locustsettings.DATABASES['default'][key] = web.request.form[key]
    return web.render_template('set_params.html',
                               **locustsettings.DATABASES['default'])
