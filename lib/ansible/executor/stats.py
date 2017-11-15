# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from collections import MutableMapping

from ansible.utils.vars import merge_hash


class AggregateStats:
    ''' holds stats about per-host activity during playbook runs '''

    def __init__(self):

        self.processed = {}
        self.failures = {}
        self.ok = {}
        self.dark = {}
        self.changed = {}
        self.skipped = {}

        # user defined stats, which can be per host or global
        self.custom = {}

    def increment(self, what, host):
        ''' helper function to bump a statistic '''

        self.processed[host] = 1
        prev = (getattr(self, what)).get(host, 0)
        getattr(self, what)[host] = prev + 1

    def summarize(self, host):
        ''' return information about a particular host '''

        return dict(
            ok=self.ok.get(host, 0),
            failures=self.failures.get(host, 0),
            unreachable=self.dark.get(host, 0),
            changed=self.changed.get(host, 0),
            skipped=self.skipped.get(host, 0)
        )

    def set_custom_stats(self, which, what, host=None):
        ''' allow setting of a custom stat'''

        if host is None:
            host = '_run'
        if host not in self.custom:
            self.custom[host] = {which: what}
        else:
            self.custom[host][which] = what

    def update_custom_stats(self, which, what, host=None):
        ''' allow aggregation of a custom stat'''

        if host is None:
            host = '_run'
        if host not in self.custom or which not in self.custom[host]:
            return self.set_custom_stats(which, what, host)

        # mismatching types
        if not isinstance(what, type(self.custom[host][which])):
            return None

        if isinstance(what, MutableMapping):
            self.custom[host][which] = merge_hash(self.custom[host][which], what)
        else:
            # let overloaded + take care of other types
            self.custom[host][which] += what


class DebugStats(AggregateStats):
    ''' Holds more advanced statistics about per-host activity, to drill down to a specific playbook and task failure/unreachable '''

    def __init__(self, options):
        self.failed_playbooks = {}
        self.processed = {}
        self.failures = {}
        self.ok = {}
        self.dark = {}
        self.changed = {}
        self.skipped = {}

        # user defined stats, which can be per host or global
        self.custom = {}

    def _get_playbook_name(self, playbook):
        key_name = ''
        with open(playbook, 'r') as the_file:
            for line in the_file.readlines():
                if 'name:' in line.strip():
                    # This is the name you will find in stats.
                    key_name = line.replace('name:', '').replace('- ', '').strip()
        if not key_name:
            raise Exception(
                "Unnamed playbooks will not allow CustomSubspaceStats to work properly.")
        return key_name

    def summarize_playbooks(self, host):
        ''' return information about a particular host '''

        return self.failed_playbooks.get(host, {})

    def increment(self, what, host, play=None, task=None):
        """
        In addition to the 'normal' statistics, keep track of 'failed_playbooks' which will have a different interpretation.
        """
        super(DebugStats, self).increment(what, host)
        # Special case for failed playbooks.. record more information!
        if what in ['ok', 'skipped', 'changed']:
            return
        if not play and not task:
            return
        play_name = play.get_name()
        task_path = task.get_path()
        if task._role:
            role = task._role._role_name
            tuple_key = (
                "Play: %s" % play_name,
                "Task: %s" % task_path,
                "Role: %s" % role)
        else:
            tuple_key = (
                "Play: %s" % play_name,
                "Task: %s" % task_path
            )

        host_dict = self.failed_playbooks.get(host, {})
        # Keep track of status counts _per-task_
        status_dict = host_dict.get(tuple_key, {})

        status_count = status_dict.get(what, 0)
        status_dict[what] = status_count + 1

        host_dict[tuple_key] = status_dict
        # Separate results by host.
        self.failed_playbooks[host] = host_dict
