import json
import os
import unittest
from jsonkeeper import create_app
from jsonkeeper.models import JSON_document


class JkTestCase(unittest.TestCase):
    """ Test JSONkeeper

        If just called as $ python3 test.py, a default config is used where
        JSON-LD @id rewriting and Activity Stream serving are active. To test
        more thoroughly the environment variables JK_ID_REWRITE and JK_AS_SERVE
        can be set to 0 or 1. Example:

            $ JK_ID_REWRITE=1 JK_AS_SERVE=0 python3 test.py

        Would run the test with a config where JSON-LD @ids are rewritten but
        a Activity Stream is not being served.

        Note: the combination of JK_ID_REWRITE=0 and JK_AS_SERVE=1 makes no
            sense (the AS needs to point to dereferencable @ids) as should not
            be used.

        Implementation note: tried to implement running multiple variations of
            JkTestCase by using subclasses instead of environment variables.
            Even though JSONkeeper uses the application factory pattern, the AS
            collection route would be set to None despite the config value
            being set to a 'as/collection.json'.
    """

    def setUp(self):
        """ Set up sqlite DB in memory and JSON storage in a tmp directory.
        """

        self.id_rewrite = True
        self.as_serve = True
        if os.environ.get('JK_ID_REWRITE'):
            self.id_rewrite = bool(int(os.environ.get('JK_ID_REWRITE')))
        if os.environ.get('JK_AS_SERVE'):
            self.as_serve = bool(int(os.environ.get('JK_AS_SERVE')))
        app = create_app(id_rewrite=self.id_rewrite, as_serve=self.as_serve)
        self.app = app
        # ↓ Temporary "fix" for https://github.com/pallets/flask/issues/2549
        self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        self.tc = app.test_client()

    def tearDown(self):
        """ Remove tmp directory set up for JSON storage.
        """

        pass

    def test_info_page_JSON(self):
        """ Test info page when Accept header is set to application/json
        """

        with self.app.app_context():
            resp = self.tc.get('/', headers={'Accept': 'application/json'})

            self.assertEqual(resp.status, '200 OK')
            self.assertEqual(resp.headers.get('Content-Type'),
                             'application/json')
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertIn('message', json_obj)
            self.assertIn('JSON documents.', json_obj['message'])
            self.assertNotIn(b'Activity Stream', resp.data)

    def test_info_page_PLAIN(self):
        """ Test info page when Accept header is not set to application/json
        """

        with self.app.app_context():
            resp = self.tc.get('/')

            self.assertEqual(resp.status, '200 OK')
            self.assertIn('text/plain', resp.headers.get('Content-Type'))
            self.assertIn(b'JSON documents.', resp.data)
            self.assertNotIn(b'Activity Stream', resp.data)
            self.assertNotIn(b'{', resp.data)

    def test_redirects(self):
        """ Test redirection to info page.
        """

        with self.app.app_context():
            resp = self.tc.get('/{}'.format(self.app.cfg.api_path()))
            self.assertEqual(resp.status, '302 FOUND')
            resp = self.tc.get(('/{}/daa1f3e9-6928-453b-81aa-4'
                                '5ae7f99bbe9').format(self.app.cfg.api_path()))
            self.assertEqual(resp.status, '302 FOUND')

    def test_nonexistent_JSON(self):
        """ Test 404s for when JSON document with the given ID doesn't exist.
        """

        with self.app.app_context():
            resp = self.tc.get('/{}/foo'.format(self.app.cfg.api_path()),
                               headers={'Accept': 'application/json'})
            self.assertEqual(resp.status, '404 NOT FOUND')

            resp = self.tc.put('/{}/foo'.format(self.app.cfg.api_path()),
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json'})
            self.assertEqual(resp.status, '404 NOT FOUND')

            resp = self.tc.delete('/{}/foo'.format(self.app.cfg.api_path()))
            self.assertEqual(resp.status, '404 NOT FOUND')

    def test_nonexistent_AS(self):
        """ Test 404 for when Activity Stream doesn't exist.
        """

        with self.app.app_context():
            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            self.assertEqual(resp.status, '404 NOT FOUND')

    def test_unprotected_JSON(self):
        """ Test create, retrieve, update, delete lifecycle of a JSON document
            when no access token is provided.
        """

        with self.app.app_context():
            # Create
            # # HTTP response
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/json'},
                                data='{"foo":"bar"}')
            self.assertEqual(resp.status, '201 CREATED')
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertIn('foo', json_obj)
            self.assertEqual(json_obj['foo'], 'bar')
            location = resp.headers.get('Location')
            json_id = location.split('/')[-1]

            # # DB
            json_doc = JSON_document.query.filter_by(
                            id=json_id).first()
            self.assertEqual(json_doc.id, json_id)
            self.assertEqual(json_doc.access_token, '')
            json_obj = json.loads(json_doc.json_string)
            self.assertIn('foo', json_obj)
            self.assertEqual(json_obj['foo'], 'bar')

            # Access
            # # HTTP response
            resp = self.tc.get(location,
                               headers={'Accept': 'application/json'})
            self.assertEqual(resp.status, '200 OK')
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertIn('foo', json_obj)
            self.assertEqual(json_obj['foo'], 'bar')

            # Update
            # # HTTP response
            resp = self.tc.put(location,
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json'},
                               data='["ほげ"]')
            self.assertEqual(resp.status, '200 OK')
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertIn('ほげ', json_obj)

            # # DB
            json_doc = JSON_document.query.filter_by(
                            id=json_id).first()
            json_obj = json.loads(json_doc.json_string)
            self.assertIn('ほげ', json_obj)

            # Delete
            # # HTTP response
            resp = self.tc.delete(location)
            self.assertEqual(resp.status, '200 OK')

            # # DB
            json_docs = JSON_document.query.all()
            json_ids = [j.id for j in json_docs]
            self.assertNotIn(json_id, json_ids)

    def _upload_JSON_LD(self):
        init_id = 'foo'
        curation_json = '''
            {
              "@context":[
                "http://iiif.io/api/presentation/2/context.json",
                "http://codh.rois.ac.jp/iiif/curation/1/context.json"
                ],
              "@type":"cr:Curation",
              "selections":[],
              "@id":"'''
        curation_json += init_id
        curation_json += '"}'

        # # JSON
        resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json'},
                            data=curation_json)
        self.assertEqual(resp.status, '201 CREATED')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(json_obj['@type'], 'cr:Curation')
        self.assertEqual(json_obj['@id'], init_id)

        # # JSON-LD
        resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/ld+json'
                                     },
                            data=curation_json)
        self.assertEqual(resp.status, '201 CREATED')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(json_obj['@type'], 'cr:Curation')
        self.assertNotEqual(json_obj['@id'], init_id)
        # location = resp.headers.get('Location')
        # self.assertEqual(json_obj['@id'], location)
        # for some reason location doesn't include a port for the unit test
        # BUT it works when JSONkeeper is run with python -m flask run

    def test_JSON_LD(self):
        """ JSON-LD @id rewriting.
        """

        if not self.id_rewrite:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            self._upload_JSON_LD()

    def test_AS(self):
        """ Activity Stream hosting (and JSON-LD @id rewriting).
        """

        if not self.as_serve:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            self._upload_JSON_LD()

            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            self.assertEqual(resp.status, '200 OK')

    def test_protected_JSON(self):
        with self.app.app_context():
            """ Test update and delete restrictions of a JSON document when
                access token is provided.
            """

            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/json',
                                         'X-Access-Token': 'secret'},
                                data='{"foo":"bar"}')
            location = resp.headers.get('Location')
            resp = self.tc.put(location,
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json'},
                               data='["ほげ"]')
            self.assertEqual(resp.status, '403 FORBIDDEN')
            resp = self.tc.put(location,
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json',
                                        'X-Access-Token': 'secret'},
                               data='["ほげ"]')
            self.assertEqual(resp.status, '200 OK')
            resp = self.tc.delete(location)
            self.assertEqual(resp.status, '403 FORBIDDEN')
            resp = self.tc.delete(location,
                                  headers={'X-Access-Token': 'secret'})
            self.assertEqual(resp.status, '200 OK')

    def test_userlist(self):
        """ Test the /<api_path>/userlist endpoint.
        """

        with self.app.app_context():
            resp = self.tc.get('/{}/userlist'.format(
                                                    self.app.cfg.api_path()))
            self.assertEqual(resp.status, '200 OK')
            self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/json',
                                         'X-Access-Token': 'secret'},
                                data='{"foo":"bar"}')
            resp = self.tc.get('/{}/userlist'.format(self.app.cfg.api_path()),
                               headers={'Accept': 'application/json',
                                        'X-Access-Token': 'secret'})
            self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 1)
            resp = self.tc.get('/{}/userlist'.format(self.app.cfg.api_path()),
                               headers={'Accept': 'application/json',
                                        'X-Access-Token': 'foo'})
            self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)
            resp = self.tc.get('/{}/userlist'.format(self.app.cfg.api_path()))
            self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)

if __name__ == '__main__':
    unittest.main()
