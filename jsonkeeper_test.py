import configparser
import json
import jsonkeeper
import os
import shutil
import tempfile
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
        self.app = jsonkeeper.app.test_client()

        # ↓ not really nice since it's duplicate code from the app iself
        config = configparser.ConfigParser()
        config.read('config.ini')
        self.API_PATH = 'api'
        if 'api_path' in config['environment']:
            self.API_PATH = config['environment']['api_path']

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

    def test_info_page_HTML(self):
        """ Test info page when Accept header is not set to application/json
        """

        resp = self.app.get('/')

        self.assertEqual(resp.status, '200 OK')
        self.assertIn('text/html', resp.headers.get('Content-Type'))
        self.assertIn(b'<!doctype html>', resp.data)
        self.assertIn(b'JSON documents.', resp.data)

    def test_redirects(self):
        """ Test redirection to info page.
        """

        resp = self.app.get('/{}'.format(self.API_PATH))
        self.assertEqual(resp.status, '302 FOUND')
        resp = self.app.get('/{}/foo'.format(self.API_PATH))
        self.assertEqual(resp.status, '302 FOUND')

    def test_nonexistent_JSON(self):
        """ Test 404s for when JSON document with the given ID doesn't exist.
        """

        resp = self.app.get('/{}/foo'.format(self.API_PATH),
                            headers={'Accept': 'application/json'})
        self.assertEqual(resp.status, '404 NOT FOUND')

        resp = self.app.put('/{}/foo'.format(self.API_PATH),
                            headers={'Accept': 'application/json',
                                     'Content-Type': 'application/json'})
        self.assertEqual(resp.status, '404 NOT FOUND')

        resp = self.app.delete('/{}/foo'.format(self.API_PATH))
        self.assertEqual(resp.status, '404 NOT FOUND')

    def test_unprotected_JSON(self):
        """ Test create, retrieve, update, delete lifecycle of a JSON document
            when no access token is provided.
        """

        # Create
        # # HTTP response
        resp = self.app.post('/{}'.format(self.API_PATH),
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

    def test_protected_JSON(self):
        """ Test update and delete restrictions of a JSON document when access
            token is provided.
        """

        resp = self.app.post('/{}'.format(self.API_PATH),
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

if __name__ == '__main__':
    unittest.main()
