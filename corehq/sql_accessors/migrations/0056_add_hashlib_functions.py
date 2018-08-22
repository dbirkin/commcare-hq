# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-12-04 08:36
from __future__ import absolute_import, unicode_literals

from django.db import migrations
from corehq.sql_db.operations import noop_migration


class Migration(migrations.Migration):

    dependencies = [
        ('sql_accessors', '0055_set_form_modified_on'),
    ]

    operations = [
        # this originally installed the hashlib extension
        # but commcare-cloud does that where possible already
        # and Amazon RDS doesn't allow it
        noop_migration()
    ]
