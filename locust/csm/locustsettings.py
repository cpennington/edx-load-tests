import sys

from lms.envs.common import *

XQUEUE_INTERFACE = {}

# This isn't enough to actually connect to a database
# It's expected that you provide the 'HOST', 'USER', and
# 'PASSWORD' fields as well. 'NAME' and 'PORT' can be
# overridden, but these are good defaults.

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'wwc',
        'PORT': '3306',
    }
}
