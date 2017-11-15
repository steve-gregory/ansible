import json
import logging
import optparse

from ansible.cli import InvalidOptsParser
from ansible.cli.playbook import CLI, PlaybookCLI


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()

default_logger = logging.getLogger(__name__)


class PythonPlaybookRunner(PlaybookCLI):
    """
    Overwrite key methods from 'ansible.cli.playbook.PlaybookCLI'
    - Remove all reliance on the actual _cli_ portion.
      - Use parser_kwargs to pass arguments and flags to the InvalidOptsParser
    """

    inventory = None
    loader = None
    options = None
    extra_vars = None
    variable_manager = None
    # These values filled out after playbook_execution_completed_hook
    results = {}
    stats = None

    def __init__(self, args, callback=None, extra_vars={}, **parser_kwargs):
        """
        This custom method drops the requirement for interacting
        with the CLI. Instead, pass in options and arguments
        directly to the PythonPlaybookRunner().
        """
        self.args = args
        self.action = None
        self.callback = callback

        if type(extra_vars) == dict:
            extra_vars = PythonPlaybookRunner._convert_extra_vars_to_option(extra_vars)
        parser_kwargs['extra_vars'] = extra_vars
        self.parse(args, parser_kwargs)

    def parse(self, args, parser_kwargs):
        # create parser for CLI options
        parser = CLI.base_parser(
            usage="%prog [options] playbook.yml [playbook2 ...]",
            connect_opts=True,
            meta_opts=True,
            runas_opts=True,
            subset_opts=True,
            check_opts=True,
            inventory_opts=True,
            runtask_opts=True,
            vault_opts=True,
            fork_opts=True,
            module_opts=True,
            desc="Runs Ansible playbooks, executing the defined tasks on the targeted hosts.",
        )

        # ansible playbook specific opts
        parser.add_option('--list-tasks', dest='listtasks', action='store_true',
                          help="list all tasks that would be executed")
        parser.add_option('--list-tags', dest='listtags', action='store_true',
                          help="list all available tags")
        parser.add_option('--step', dest='step', action='store_true',
                          help="one-step-at-a-time: confirm each task before running")
        parser.add_option('--start-at-task', dest='start_at_task',
                          help="start the playbook at the task matching this name")

        self.parser = parser
        values = self._parser_kwargs_to_values(parser_kwargs)
        super(PlaybookCLI, self).parse(args, values)
        display.verbosity = self.options.verbosity
        self.validate_conflicts(runas_opts=True, vault_opts=True, fork_opts=True)

    def _parser_kwargs_to_values(self, parser_kwargs):
        values = self.parser.get_default_values()
        for (key, value) in parser_kwargs.iteritems():
            if hasattr(values, key):
                setattr(values, key, value)
        return values

    @classmethod
    def _convert_extra_vars_to_option(cls, extra_vars_dict={}):
        """
        Because we are 'mocking a CLI', we need to convert:
        {...} --> ['{...}']

        This will allow `_play_prereqs` to handle the code
        as it would if passed from the command-line.
        After `_play_prereqs` has parsed the JSON/YAML option,
        `variable_manager.extra_args` will again return the {...} structure.
        """
        extra_vars_option = [json.dumps(extra_vars_dict)]
        return extra_vars_option

    def _select_register_vars(self, temporary_fact_cache):
        """
        Ignore fact caching and other non-register vars when creating self.results
        """
        temporary_facts_dict = dict(temporary_fact_cache)
        ignore_keywords = ['module_setup', 'gather_subset']
        ignore_keyword_prefix = 'ansible_'
        sanitized_vars = {}
        for host, facts in temporary_facts_dict.iteritems():
            sanitized_fact_keys = [k for k in facts.keys() if not (k in ignore_keywords) and not k.startswith(ignore_keyword_prefix)]
            if sanitized_fact_keys:
                sanitized_facts = {k: v for (k, v) in facts.iteritems() if k in sanitized_fact_keys}
                sanitized_vars[host] = sanitized_facts
        return sanitized_vars

    def _playbook_execution_complete_hook(self, playbook_executor):
        """
        Store a copy of the statistics in self.stats
        Store a copy of 'register' variables in self.results
        """
        self.stats = playbook_executor._tqm._stats
        ansible_playbook_register_vars = self._select_register_vars(playbook_executor._variable_manager._nonpersistent_fact_cache)
        self.results.update(ansible_playbook_register_vars)
