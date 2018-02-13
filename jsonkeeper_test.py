import json
import jsonkeeper
import unittest
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func


class JsonStoreTestCase(unittest.TestCase):

    def setUp(self):
        """ Set up sqlite DB in memory and JSON storage in a tmp directory.
        """

        jsonkeeper.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        db = SQLAlchemy(jsonkeeper.app)

        # ↓ not really nice since it's duplicate code from the app iself
        class JSON_document(db.Model):
            id = db.Column(db.String(64), primary_key=True)
            access_token = db.Column(db.String(255))
            json_string = db.Column(db.UnicodeText())
            created_at = db.Column(db.DateTime(timezone=True),
                                   server_default=func.now())
            updated_at = db.Column(db.DateTime(timezone=True),
                                   onupdate=func.now())
        db.create_all()

        jsonkeeper.app.testing = True
        jsonkeeper.app.cfg.set_debug_config()
        self.app = jsonkeeper.app.test_client()

    def tearDown(self):
        """ Remove tmp directory set up for JSON storage.
        """

        pass

    def test_info_page_JSON(self):
        """ Test info page when Accept header is set to application/json
        """

        resp = self.app.get('/', headers={'Accept': 'application/json'})

        self.assertEqual(resp.status, '200 OK')
        self.assertEqual(resp.headers.get('Content-Type'), 'application/json')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertIn('message', json_obj)
        self.assertIn('JSON documents.', json_obj['message'])
        self.assertNotIn(b'Activity Stream', resp.data)

    def test_info_page_PLAIN(self):
        """ Test info page when Accept header is not set to application/json
        """

        resp = self.app.get('/')

        self.assertEqual(resp.status, '200 OK')
        self.assertIn('text/plain', resp.headers.get('Content-Type'))
        self.assertIn(b'JSON documents.', resp.data)
        self.assertNotIn(b'Activity Stream', resp.data)
        self.assertNotIn(b'{', resp.data)

    def test_redirects(self):
        """ Test redirection to info page.
        """

        resp = self.app.get('/{}'.format(jsonkeeper.app.cfg.api_path()))
        self.assertEqual(resp.status, '302 FOUND')
        resp = self.app.get('/{}/daa1f3e9-6928-453b-81aa-45ae7f99bbe9'.format(
                                                jsonkeeper.app.cfg.api_path()))
        self.assertEqual(resp.status, '302 FOUND')

    def test_nonexistent_JSON(self):
        """ Test 404s for when JSON document with the given ID doesn't exist.
        """

        resp = self.app.get('/{}/foo'.format(jsonkeeper.app.cfg.api_path()),
                            headers={'Accept': 'application/json'})
        self.assertEqual(resp.status, '404 NOT FOUND')

        resp = self.app.put('/{}/foo'.format(jsonkeeper.app.cfg.api_path()),
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json'})
        self.assertEqual(resp.status, '404 NOT FOUND')

        resp = self.app.delete('/{}/foo'.format(jsonkeeper.app.cfg.api_path()))
        self.assertEqual(resp.status, '404 NOT FOUND')

    def test_nonexistent_AS(self):
        """ Test 404 for when Activity Stream doesn't exist.
        """

        resp = self.app.get('/{}'.format(jsonkeeper.app.cfg.as_coll_url()))
        self.assertEqual(resp.status, '404 NOT FOUND')

    def test_unprotected_JSON(self):
        """ Test create, retrieve, update, delete lifecycle of a JSON document
            when no access token is provided.
        """

        # Create
        # # HTTP response
        resp = self.app.post('/{}'.format(jsonkeeper.app.cfg.api_path()),
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
        json_doc = jsonkeeper.JSON_document.query.filter_by(
                        id=json_id).first()
        self.assertEqual(json_doc.id, json_id)
        self.assertEqual(json_doc.access_token, '')
        json_obj = json.loads(json_doc.json_string)
        self.assertIn('foo', json_obj)
        self.assertEqual(json_obj['foo'], 'bar')

        # Access
        # # HTTP response
        resp = self.app.get(location,
                            headers={'Accept': 'application/json'})
        self.assertEqual(resp.status, '200 OK')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertIn('foo', json_obj)
        self.assertEqual(json_obj['foo'], 'bar')

        # Update
        # # HTTP response
        resp = self.app.put(location,
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json'},
                            data='["ほげ"]')
        self.assertEqual(resp.status, '200 OK')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertIn('ほげ', json_obj)

        # # DB
        json_doc = jsonkeeper.JSON_document.query.filter_by(
                        id=json_id).first()
        json_obj = json.loads(json_doc.json_string)
        self.assertIn('ほげ', json_obj)

        # Delete
        # # HTTP response
        resp = self.app.delete(location)
        self.assertEqual(resp.status, '200 OK')

        # # DB
        json_docs = jsonkeeper.JSON_document.query.all()
        json_ids = [j.id for j in json_docs]
        self.assertNotIn(json_id, json_ids)

    def test_AS(self):
        """ Activity Stream.
        """

        # FIXME: expected outcomes are dependent on config values. This test
        #        only makes sense if documents of the @type
        #        http://codh.rois.ac.jp/iiif/curation/1#Curation
        #        are configured as Activity generating.

        print('''
              @test_AS()

              # FIXME: expected outcomes are dependent on config values. This
              #        test only makes sense if documents of the @type
              #        http://codh.rois.ac.jp/iiif/curation/1#Curation
              #        are configured as Activity generating.
              ''')

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
        resp = self.app.post('/{}'.format(jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'Content-Type': 'application/json'},
                             data=curation_json)
        self.assertEqual(resp.status, '201 CREATED')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(json_obj['@type'], 'cr:Curation')
        self.assertEqual(json_obj['@id'], init_id)

        # # JSON-LD
        resp = self.app.post('/{}'.format(jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'Content-Type': 'application/ld+json'},
                             data=curation_json)
        self.assertEqual(resp.status, '201 CREATED')
        json_obj = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(json_obj['@type'], 'cr:Curation')
        self.assertNotEqual(json_obj['@id'], init_id)
        # location = resp.headers.get('Location')
        # self.assertEqual(json_obj['@id'], location)
        # for some reason location doesn't include a port for the unit test
        # BUT it works when JSONkeeper is run with python -m flask run

        resp = self.app.get('/{}'.format(jsonkeeper.app.cfg.as_coll_url()))
        self.assertEqual(resp.status, '200 OK')

    def test_protected_JSON(self):
        """ Test update and delete restrictions of a JSON document when access
            token is provided.
        """

        resp = self.app.post('/{}'.format(jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'Content-Type': 'application/json',
                                      'X-Access-Token': 'secret'},
                             data='{"foo":"bar"}')
        location = resp.headers.get('Location')
        resp = self.app.put(location,
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json'},
                            data='["ほげ"]')
        self.assertEqual(resp.status, '403 FORBIDDEN')
        resp = self.app.put(location,
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json',
                                     'X-Access-Token': 'secret'},
                            data='["ほげ"]')
        self.assertEqual(resp.status, '200 OK')
        resp = self.app.delete(location)
        self.assertEqual(resp.status, '403 FORBIDDEN')
        resp = self.app.delete(location,
                               headers={'X-Access-Token': 'secret'})
        self.assertEqual(resp.status, '200 OK')

    def test_userlist(self):
        """ Test the /<api_path>/userlist endpoint.
        """

        resp = self.app.get('/{}/userlist'.format(
                                                jsonkeeper.app.cfg.api_path()))
        self.assertEqual(resp.status, '200 OK')
        self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)
        resp = self.app.post('/{}'.format(jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'Content-Type': 'application/json',
                                      'X-Access-Token': 'secret'},
                             data='{"foo":"bar"}')
        resp = self.app.get('/{}/userlist'.format(
                                                jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'X-Access-Token': 'secret'})
        self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 1)
        resp = self.app.get('/{}/userlist'.format(
                                                jsonkeeper.app.cfg.api_path()),
                             headers={'Accept': 'application/json',
                                      'X-Access-Token': 'foo'})
        self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)
        resp = self.app.get('/{}/userlist'.format(
                                                jsonkeeper.app.cfg.api_path()))
        self.assertEqual(len(json.loads(resp.data.decode('utf-8'))), 0)

if __name__ == '__main__':
    unittest.main()
