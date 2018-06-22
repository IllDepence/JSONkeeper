""" Class to comfortably get config values.
"""

import configparser
import os
import re
import sys


class Cfg():

    def __init__(self, path='config.ini'):
        cp = configparser.ConfigParser()
        if not os.path.exists(path):
            print('Config file "{}" not found.\nExiting.'.format(path))
            sys.exit(1)
        cp.read(path)
        fail, cfg = self._parse_config(cp)
        if fail:
            print(fail)
            print('Exiting.')
            sys.exit(1)
        self.cfg = cfg

    def db_uri(self):
        return self.cfg['db_uri']

    def serv_url(self):
        return self.cfg['server_url']

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

    def as_pg_store_pref(self):
        """ Prefix for storage IDs of Activity Stream pages.
        """

        return 'as_page_'

    def doc_id_patt(self):
        """ Pattern for storage IDs of documents.
        """

        return ('(as_page_)?[a-z0-9]{8}-[a-z0-9]{4}-'
                '[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}')

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
        cfg['api_path'] = 'api'
        cfg['use_firebase'] = False
        cfg['firebase_service_account_key_file'] = None
        cfg['use_id_rewrite'] = False
        cfg['id_rewrite_types'] = []
        cfg['as_collection_url'] = None
        cfg['activity_generating_types'] = []
        return cfg

    def set_debug_config(self, id_rewrite, as_serve):
        cfg = {}
        cfg['db_uri'] = 'sqlite://'
        cfg['server_url'] = 'http://localhost:5000'
        cfg['api_path'] = 'api'
        cfg['use_firebase'] = False                         # maybe change
        cfg['firebase_service_account_key_file'] = None     # at some point
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
            if cp['environment'].get('db_uri'):
                cfg['db_uri'] = cp['environment'].get('db_uri')
            if cp['environment'].get('server_url'):
                cfg['server_url'] = cp['environment'].get('server_url')
            if cp['environment'].get('custom_api_path'):
                cfg['api_path'] = cp['environment'].get('custom_api_path')

        # Firebase
        if 'firebase' in cp.sections():
            if cp['firebase'].get('service_account_key_file'):
                cfg['use_firebase'] = True
                cfg['firebase_service_account_key_file'
                    ] = cp['firebase'].get('service_account_key_file')

        # JSON-LD
        if 'json-ld' in cp.sections():
            rwt = cp['json-ld'].get('rewrite_types', '')
            rwt_list = [t.strip() for t in rwt.split(',') if len(t) > 0]
            if len(rwt_list) > 0:
                cfg['use_id_rewrite'] = True
                cfg['id_rewrite_types'] = rwt_list

        # Activity stream prerequesites
        if 'activity_stream' in cp.sections() and \
           len(cp['activity_stream'].get('collection_url', '')) > 0:
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
                cfg['as_collection_url'] = cp['activity_stream'].get('collecti'
                                                                     'on_url')
                cfg['activity_generating_types'] = agt_list
            else:
                fails.append(as_fail)

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
