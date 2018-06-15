import json
import os
import unittest
import uuid
from jsonkeeper import create_app
from jsonkeeper.models import JSON_document


class JkTestCase(unittest.TestCase):
    """ Test JSONkeeper

        If just called as $ python3 test.py, a default config is used where
        JSON-LD @id rewriting and Activity Stream serving are active. To test
        more thoroughly the environment variables JK_ID_REWRITE and JK_AS_SERVE
        can be set to 0 or 1. Example:

            $ JK_ID_REWRITE=1 JK_AS_SERVE=0 python3 test.py

        would run the test with a config where JSON-LD @ids are rewritten but
        a Activity Stream is not being served.

        Note: the combination of JK_ID_REWRITE=0 and JK_AS_SERVE=1 makes no
            sense (the AS needs to point to dereferencable @ids) and should not
            be used.

        Implementation note: tried to implement running multiple variations of
            JkTestCase by using subclasses instead of environment variables.
            Even though JSONkeeper uses the application factory pattern, the AS
            collection route would be set to None despite the config value
            being set to a 'as/collection.json'.
    """

    def setUp(self):
        """ Set up sqlite DB in memory and JSON storage in a tmp directory.
            Read environment variables if set.
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
        """ Test info page when client accepts application/json.
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
        """ Test info page when client does not accept application/json.
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

    def _get_curation_json(self, init_id):
        can_id = ('http://iiif.bodleian.ox.ac.uk/iiif/canvas/03818fac-9ba6-438'
                  '2-b339-e27a0a075f31.json#xywh=986,4209,538,880')
        man_id = ('http://iiif.bodleian.ox.ac.uk/iiif/manifest/60834383-7146-4'
                  '1ab-bfe1-48ee97bc04be.json')
        curation_json = '''
            {{
              "@context":[
                "http://iiif.io/api/presentation/2/context.json",
                "http://codh.rois.ac.jp/iiif/curation/1/context.json"
                ],
              "@id":"{}",
              "@type":"cr:Curation",
              "selections":[
                  {{
                    "@id":"{}",
                    "@type":"sc:Range",
                    "label":"",
                    "canvases": [
                                    {{
                                        "@id":"{}",
                                        "label":"Marine exploration"
                                    }}
                                ],
                    "within": [
                                {{
                                "@id": "{}",
                                "@type": "sc:Manifest",
                                "label": "MS. Bodl. 264"
                                }}
                              ]
                  }}
                ]
            }}'''.format(init_id, init_id, can_id, man_id)
        return curation_json

    def _upload_JSON_LD(self):
        init_id = str(uuid.uuid4())
        curation_json = self._get_curation_json(init_id)

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
        # BUT it works when JSONkeeper is normally run
        location = resp.headers.get('Location')
        return location

    def test_restrictive_accpet_header(self):
        """ Test uploading a JSON-LD document with the 'Accept' header set to
            only 'application/ld+json'.
        """

        with self.app.app_context():
            init_id = 'foo'
            curation_json = self._get_curation_json(init_id)
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/ld+json',
                                         'Content-Type': 'application/ld+json'
                                         },
                                data=curation_json)
            self.assertEqual(resp.status, '201 CREATED')

            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/foo+json',
                                         'Content-Type': 'application/ld+json'
                                         },
                                data=curation_json)
            self.assertNotEqual(resp.status, '201 CREATED')

    def test_JSON_LD(self):
        """ JSON-LD @id rewriting.
        """

        if not self.id_rewrite:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            self._upload_JSON_LD()

    def _get_activities_of_last_as_page(self):
        """ Access the AS and return the orderedItems of the last (i.e. most
            recently added) page.
        """

        resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
        coll = json.loads(resp.data.decode('utf-8'))
        last_page_url = coll['last']['id']
        resp = self.tc.get('{}'.format(last_page_url),
                                headers={'Accept': 'application/json'})
        last_page = json.loads(resp.data.decode('utf-8'))
        return last_page['orderedItems']

    def test_AS(self):
        """ Activity Stream hosting (and JSON-LD @id rewriting).
        """

        if not self.as_serve:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            location = self._upload_JSON_LD()

            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            self.assertEqual(resp.status, '200 OK')

            curation_json = self._get_curation_json('foo')
            curation_json_changed = curation_json.replace('exploration',
                                                          'adventure')
            resp = self.tc.put('{}'.format(location),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/ld+json'
                                        },
                                data=curation_json_changed)
            most_recent_actions = self._get_activities_of_last_as_page()
            self.assertEqual(most_recent_actions[0]['type'], 'Update')
            resp = self.tc.delete(location)
            most_recent_actions = self._get_activities_of_last_as_page()
            self.assertEqual(most_recent_actions[0]['type'], 'Delete')

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

    def test_Curation_Range_access(self):
        """ Test special behavior for cr:Curations where contained sc:Range
            objects can be retrieved separately.
        """

        if not self.id_rewrite:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            location = self._upload_JSON_LD()
            resp = self.tc.get('{}/range1'.format(location),
                               headers={'Accept': 'application/json'})
            self.assertEqual(resp.status, '200 OK')
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertEqual(json_obj['@type'], 'sc:Range')

    def test_status_endpoint(self):
        """ Test status endpoint.
        """

        with self.app.app_context():
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/json',
                                         'X-Access-Token': 'foo',
                                         'X-Private':'true'},
                                data='{"baz":"bam"}')
            location = resp.headers.get('Location')
            resp = self.tc.get('{}/status'.format(location),
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json'})
            self.assertEqual(resp.status, '403 FORBIDDEN')

            resp = self.tc.get('{}/status'.format(location),
                               headers={'Accept': 'application/json',
                                        'Content-Type': 'application/json',
                                         'X-Access-Token': 'foo'})
            json_obj = json.loads(resp.data.decode('utf-8'))
            self.assertEqual(json_obj['access_token'], 'foo')
            self.assertEqual(json_obj['private'], True)

    def test_private_AS(self):
        """ Test if X-Private header.
        """

        if not self.as_serve:
            raise unittest.SkipTest('Test not applicable for current config.')

        with self.app.app_context():
            init_id = 'foo'
            curation_json = self._get_curation_json(init_id)
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/ld+json',
                                         'X-Private':'true'},
                                data=curation_json)

            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            self.assertEqual(resp.status, '404 NOT FOUND')

            curation_json = self._get_curation_json(init_id)
            resp = self.tc.post('/{}'.format(self.app.cfg.api_path()),
                                headers={'Accept': 'application/json',
                                         'Content-Type': 'application/ld+json',
                                         'X-Private':'false'},
                                data=curation_json)
            location = resp.headers.get('Location')

            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            self.assertEqual(resp.status, '200 OK')
            json_obj = json.loads(resp.data.decode('utf-8'))
            # a Create Action should have been added
            self.assertEqual(json_obj.get('totalItems'), 1)

            resp = self.tc.patch('{}/status'.format(location),
                                 headers={'Accept': 'application/json',
                                          'Content-Type': 'application/json'},
                                 data='{"private": "true"}')
            resp = self.tc.get('/{}'.format(self.app.cfg.as_coll_url()))
            json_obj = json.loads(resp.data.decode('utf-8'))
            # a Delete Action should have been added
            self.assertEqual(json_obj.get('totalItems'), 2)

if __name__ == '__main__':
    unittest.main()
