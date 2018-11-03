""" Class to comfortably get config values.
"""

import configparser
import datetime
import os
import re
import sys


class Cfg():

    def __init__(self, path='config.ini'):
        cp = configparser.ConfigParser()
        if os.path.exists(path):
            cp.read(path)
        else:
            msg = 'Config file "{}" not found. Using defaults.'.format(path)
            print(msg)
            self.log_cfg(None, msg)
        fail, cfg = self._parse_config(cp)
        if fail:
            msg = '{} Exiting.'.format(fail)
            print(msg)
            self.log_cfg(None, msg)
            sys.exit(1)
        self.cfg = cfg

    def log_cfg(self, cp, msg):
        """ Write a log message to the log file BEFORE the config has been
            parsed.
        """

        if cp is not None and \
                'environment' in cp.sections() and \
                cp['environment'].get('log_file'):
            log_file = cp['environment'].get('log_file')
        else:
            log_file = self._default_log_file()
        timestamp = str(datetime.datetime.now()).split('.')[0]
        # make /dev/stdout usable as log file
        # https://www.bugs.python.org/issue27805
        # side note: stat.S_ISCHR(os.stat(fn).st_mode) doesn't seem to work for
        #            in an alpine linux docker container running canvas indexer
        #            with gunicorn although manually executing it on a python
        #            shell in the container works
        if log_file == '/dev/stdout':
            mode = 'w'
        else:
            mode = 'a'
        with open(log_file, mode) as f:
            f.write('[{}]   {}\n'.format(timestamp, msg))

    def _default_log_file(self):
        return '/tmp/jk_log.txt'

    def db_uri(self):
        return self.cfg['db_uri']

    def serv_url(self):
        return self.cfg['server_url']

    def log_file(self):
        return self.cfg['log_file']

    def api_path(self):
        return self.cfg['api_path']

    def use_frbs(self):
        return self.cfg['use_firebase']

    def frbs_conf(self):
        return self.cfg['firebase_service_account_key_file']

    def id_rewr(self):
        return self.cfg['use_id_rewrite']

    def id_types(self):
        return self.cfg['id_rewrite_types']

    def as_coll_url(self):
        return self.cfg['as_collection_url']

    def serve_as(self):
        return bool(self.as_coll_url())

    def as_coll_store_id(self):
        if self.serve_as():
            return 'as_coll_{}'.format(re.sub(r'\W', '', self.as_coll_url()))
        else:
            return None

    def as_types(self):
        return self.cfg['activity_generating_types']

    def userdocs_extra(self):
        return self.cfg['userdocs_extra']

    def garbage_collection_interval(self):
        return self.cfg['garbage_collection_interval']

    def garbage_collection_age(self):
        return self.cfg['garbage_collection_age']

    def as_pg_store_pref(self):
        """ Prefix for storage IDs of Activity Stream pages.
        """

        return 'as_page_'

    def doc_id_patt(self):
        """ Pattern for storage IDs of documents.
        """

        current_pattern = ('(as_page_)?[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-'
                           '[a-z0-9]{4}-[a-z0-9]{12}')
        lecacy_pattern = '[a-z0-9]{64}'
        return ('({}|{})'.format(current_pattern, lecacy_pattern))

    def access_token_frbs_prefix(self):
        """ Prefix put it front of Firebase access tokens.
        """

        return 'frbs:'

    def access_token_free_prefix(self):
        """ Prefix put it front of self managed access tokens.
        """

        return 'free:'

    def _get_default_config(self):
        # later read from config file
        cfg = {}
        cfg['db_uri'] = 'sqlite:///keep.db'
        cfg['server_url'] = 'http://localhost:5000'
        cfg['log_file'] = self._default_log_file()
        cfg['api_path'] = 'api'
        cfg['use_firebase'] = False
        cfg['firebase_service_account_key_file'] = None
        cfg['use_id_rewrite'] = False
        cfg['id_rewrite_types'] = []
        cfg['as_collection_url'] = None
        cfg['activity_generating_types'] = []
        cfg['userdocs_extra'] = []
        cfg['garbage_collection_interval'] = -1
        cfg['garbage_collection_age'] = -1
        return cfg

    def set_debug_config(self, id_rewrite, as_serve):
        cfg = {}
        cfg['db_uri'] = 'sqlite://'
        cfg['server_url'] = 'http://localhost:5000'
        cfg['log_file'] = self._default_log_file()
        cfg['api_path'] = 'api'
        cfg['use_firebase'] = False                         # maybe change
        cfg['firebase_service_account_key_file'] = None     # at some point
        cfg['userdocs_extra'] = []
        cfg['garbage_collection_interval'] = -1
        cfg['garbage_collection_age'] = -1
        if id_rewrite:
            cfg['use_id_rewrite'] = True
            cfg['id_rewrite_types'] = [('http://codh.rois.ac.jp/iiif/curation/'
                                        '1#Curation')]
        else:
            cfg['use_id_rewrite'] = False
            cfg['id_rewrite_types'] = []
        if id_rewrite and as_serve:
            cfg['as_collection_url'] = 'as/collection.json'
            cfg['activity_generating_types'] = cfg['id_rewrite_types']
        else:
            cfg['as_collection_url'] = None
            cfg['activity_generating_types'] = []
        self.cfg = cfg

    def _parse_config(self, cp):
        """ Prase a configparser.ConfigParser instance and return
                - a fail message in case of an invalid config (False otherwise)
                - a config dict
        """

        cfg = self._get_default_config()
        fails = []

        # Environment
        if 'environment' in cp.sections():
            for (key, val) in cp.items('environment'):
                if key == 'db_uri':
                    cfg['db_uri'] = val
                elif key == 'server_url':
                    cfg['server_url'] = val
                elif key == 'log_file':
                    cfg['log_file'] = val
                else:
                    self.log_cfg(cp, ('WARNING: unexpected config entry "{}" i'
                                      'n section [environment]'.format(key)))

        # API
        if 'api' in cp.sections():
            if cp['api'].get('api_path'):
                cfg['api_path'] = cp['api'].get('api_path')
            if cp['api'].get('userdocs_added_properties'):
                uap = cp['api'].get('userdocs_added_properties')
                uap_list = [p.strip() for p in uap.split(',') if len(p) > 0]
                cfg['userdocs_extra'] = uap_list
            valid_garbage = True
            if cp['api'].get('garbage_collection_interval'):
                valid_garbage = not valid_garbage
                try:
                    str_val = cp['api'].get('garbage_collection_interval')
                    cfg['garbage_collection_interval'] = int(str_val)
                except ValueError:
                    fails.append(('garbage collection interval in api section '
                                  'must be an integer'))
            if cp['api'].get('garbage_collection_age'):
                valid_garbage = not valid_garbage
                try:
                    str_val = cp['api'].get('garbage_collection_age')
                    cfg['garbage_collection_age'] = int(str_val)
                except ValueError:
                    fails.append(('garbage collection age in api section must '
                                  'be an integer'))
            if not valid_garbage:
                fails.append(('garbage collection requires *both* interval and'
                              ' age to be set'))
            # check for unexpected entries seperately b/c calculation of
            # valid_garbage wouldn't work as nicely in a loop
            for (key, val) in cp.items('api'):
                if key not in ['api_path',
                               'userdocs_added_properties',
                               'garbage_collection_interval',
                               'garbage_collection_age']:
                    self.log_cfg(cp, ('WARNING: unexpected config entry "{}" i'
                                      'n section [api]'.format(key)))

        # Firebase
        if 'firebase' in cp.sections():
            for (key, val) in cp.items('firebase'):
                if key == 'service_account_key_file':
                    cfg['use_firebase'] = True
                    cfg['firebase_service_account_key_file'] = val
                else:
                    self.log_cfg(cp, ('WARNING: unexpected config entry "{}" i'
                                      'n section [firebase]'.format(key)))

        # JSON-LD
        if 'json-ld' in cp.sections():
            for (key, val) in cp.items('json-ld'):
                if key == 'rewrite_types':
                    rwt = cp['json-ld'].get('rewrite_types', '')
                    rwt_list = [t.strip() for t in rwt.split(',')
                                if len(t) > 0]
                    if len(rwt_list) > 0:
                        cfg['use_id_rewrite'] = True
                        cfg['id_rewrite_types'] = rwt_list
                else:
                    self.log_cfg(cp, ('WARNING: unexpected config entry "{}" i'
                                      'n section [json-ld]'.format(key)))

        # Activity stream prerequesites
        if 'activity_stream' in cp.sections() and \
           len(cp['activity_stream'].get('collection_endpoint', '')) > 0:
            as_fail = None

            # Need to define types
            agt = cp['activity_stream'].get('activity_generating_types', '')
            if len(agt) == 0:
                as_fail = ('Serving an Activity Stream requires activity_gener'
                           'ating_types in config section [activity_stream] to'
                           ' be set.')
            # Defined types need to be rewritten
            agt_list = [t.strip() for t in agt.split(',') if len(t) > 0]
            valid = True
            for gen_type in agt_list:
                if gen_type not in cfg['id_rewrite_types']:
                    valid = False
            if not valid:
                as_fail = ('Serving an Activity Stream requires all types set '
                           'for Activity generation also to be set for JSON-LD'
                           ' @id rewriting.')

            if not as_fail:
                cfg['as_collection_url'] = cp['activity_stream'
                                              ].get('collection_endpoint')
                cfg['activity_generating_types'] = agt_list
            else:
                fails.append(as_fail)
            # check for unexpected entries seperately b/c above section is non
            # trivial
            for (key, val) in cp.items('activity_stream'):
                if key not in ['collection_endpoint',
                               'activity_generating_types']:
                    self.log_cfg(cp,
                                 ('WARNING: unexpected config entry "{}" i'
                                  'n section [activity_stream]'.format(key)))

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
