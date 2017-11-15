""" json_store

    Minimal web app made for API access to store and retrieve JSON.
"""

import configparser
import hashlib
import json
import os
import random
import sys
from flask import (abort, Flask, jsonify, redirect, render_template, request,
                   Response, url_for)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import default_exceptions, HTTPException

app = Flask(__name__)
random.seed()

config = configparser.ConfigParser()
config.read('config.ini')
if 'environment' not in config.sections():
    print('Config file needs a [environment] section.')
    sys.exit(1)
elif 'db_uri' not in config['environment'] or \
     'storage_folder' not in config['environment'] or \
     'server_url' not in config['environment']:
    print(('Config section [environment] needs parameters "db_uri", "storage_'
           'folder" and "server_url".'))
    sys.exit(1)

STORE_FOLDER = config['environment']['storage_folder']
BASE_URL = config['environment']['server_url']
API_PATH = 'api'
if 'api_path' in config['environment']:
    API_PATH = config['environment']['api_path']

app.config['SQLALCHEMY_DATABASE_URI'] = config['environment']['db_uri']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class JSON_document(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    access_token = db.Column(db.String(255))

db.create_all()


if not os.path.exists(STORE_FOLDER):
    """ Make sure the store folder exists.
    """

    os.makedirs(STORE_FOLDER)


for code in default_exceptions.keys():
    """ Make app return exceptions in JSON form. Also add CORS headers.

        Based on http://flask.pocoo.org/snippets/83/ but updated to use
        register_error_handler method.
        Note: this doesn't seem to work for 405 Method Not Allowed in an
              Apache + gnunicorn setup.
    """

    @app.errorhandler(code)
    def make_json_error(error):
        resp = jsonify(message=str(error))
        resp.status_code = (error.code
                            if isinstance(error, HTTPException)
                            else 500)
        return add_CORS_headers(resp)


def write_json(request, given_id=None):
    """ Write JSON contents from request to a file. Used for POST requests
        (new document) and PUT requests (update document). Dealing with access
        tokens (given or not in case of POST, correct or not in case of PUT)
        should happen *before* this method is called.
    """

    json_bytes = request.data
    json_string = json_bytes.decode('utf-8')
    json_obj = json.loads(json_string)  # TODO: mby react on invalid JSON?
    resp = Response(json_string)
    if given_id is not None:
        json_id = given_id
    else:
        # add randomness to allow for (initially) identical documents (could
        # be updated into distict documents later)
        json_id = hashlib.sha256(bytes(str(random.random()) + json_string,
                                       'utf-8')).hexdigest()
        resp.headers['Location'] = '/{}/{}'.format(API_PATH, json_id)

    with open('{}/{}'.format(STORE_FOLDER, json_id), 'w') as f:
        f.write(json_string)

    resp.headers['Content-Type'] = 'application/json'

    return resp


def CORS_preflight_response(request):
    """ Create a response for CORS preflight requests.
    """

    resp = Response('')
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = ('GET,POST,DELETE,OPTIONS,'
                                                    'PUT')
    # ↓ what will actually be available via Access-Control-Expose-Headers
    allowed_headers = 'Content-Type,Access-Control-Allow-Origin,Location'
    # ↓ if they ask for something specific we just "comply" to make CORS work
    if 'Access-Control-Request-Headers' in request.headers:
        allowed_headers = request.headers.get('Access-Control-Request-Headers')
    resp.headers['Access-Control-Allow-Headers'] = allowed_headers

    return resp, 200


def add_CORS_headers(resp):
    """ Add CORS headers to a response. This is done even for non CORS requests
        to keep the code simple and because it doesn't hurt non CORS requests).
        This method should, however, not be called for CORS preflight requests
        because they need special treatment.
    """

    if type(resp) is str:
        resp = Response(resp)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Max-Age'] = '600'
    resp.headers['Access-Control-Expose-Headers'] = ('Content-Type,Access-Cont'
                                                     'rol-Allow-Origin,Locatio'
                                                     'n')

    return resp


def handle_post_request(request):
    """ Handle request with the purpose of storing a new JSON document.
    """

    access_token = ''
    if 'X-Access-Token' in request.headers:
        access_token = request.headers.get('X-Access-Token')

    resp = write_json(request)
    json_id = resp.headers.get('Location').split('/')[-1]

    json_doc = JSON_document(id=json_id, access_token=access_token)
    db.session.add(json_doc)
    db.session.commit()

    return add_CORS_headers(resp), 201


def handle_get_request(request, json_id):
    """ Handle request with the purpose of retrieving a JSON document.
    """

    json_location = '{}/{}'.format(STORE_FOLDER, json_id)
    if os.path.isfile(json_location):
        with open(json_location, 'r') as f:
            json_string = f.read()
        resp = Response(json_string)
        resp.headers['Content-Type'] = 'application/json'

        return add_CORS_headers(resp), 200
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def handle_put_request(request, json_id):
    """ Handle request with the purpose of updating a JSON document.
    """

    json_location = '{}/{}'.format(STORE_FOLDER, json_id)
    if os.path.isfile(json_location):
        access_token = ''
        if 'X-Access-Token' in request.headers:
            access_token = request.headers.get('X-Access-Token')
        json_doc = JSON_document.query.filter_by(id=json_id).first()
        if json_doc.access_token == access_token:
            resp = write_json(request, given_id=json_id)
            return add_CORS_headers(resp), 200
        else:
            return abort(403, 'X-Access-Token header value not correct.')
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def handle_delete_request(request, json_id):
    """ Handle request with the purpose of deleting a JSON document.
    """

    json_location = '{}/{}'.format(STORE_FOLDER, json_id)
    if os.path.isfile(json_location):
        access_token = ''
        if 'X-Access-Token' in request.headers:
            access_token = request.headers.get('X-Access-Token')
        json_doc = JSON_document.query.filter_by(id=json_id).first()
        if json_doc.access_token == access_token:
            db.session.delete(json_doc)
            db.session.commit()
            os.remove(json_location)
            resp = Response('')
            return add_CORS_headers(resp), 200
        else:
            return abort(403, 'X-Access-Token header value not correct.')
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


@app.route('/')
def index():
    """ Info page. All requests that don't accept application/json are sent
        here.
    """

    json_files = [f.path for f in os.scandir(STORE_FOLDER) if f.is_file()]
    num_files = len(json_files)
    store_size = '{:,}'.format(sum(os.path.getsize(f) for f in json_files))
    status_msg = 'Storing {} files taking up {} byte.'.format(num_files,
                                                              store_size)

    if 'Accept' in request.headers and \
            'application/json' in request.headers.get('Accept'):
        resp = jsonify({'message': status_msg})
        return add_CORS_headers(resp), 200
    else:
        resp = render_template('index.html',
                               base_url=BASE_URL,
                               api_path=API_PATH,
                               status_msg=status_msg)
        return add_CORS_headers(resp), 200


@app.route('/{}'.format(API_PATH), methods=['GET', 'POST', 'OPTIONS'])
def api():
    """ API endpoint for posting new JSON documents.

        Allow GET access to send human visitors to the info page.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'POST' and \
            'Accept' in request.headers and \
            'Content-Type' in request.headers and \
            'application/json' in request.headers.get('Accept') and \
            'application/json' in request.headers.get('Content-Type'):
        return handle_post_request(request)
    else:
        resp = redirect(url_for('index'))
        return add_CORS_headers(resp)


@app.route('/{}/<json_id>'.format(API_PATH),
           methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
def api_json_id(json_id):
    """ API endpoint for retrieving, updating and deleting JSON documents
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'GET' and \
            'Accept' in request.headers and \
            'application/json' in request.headers.get('Accept'):
        return handle_get_request(request, json_id)
    elif request.method == 'PUT' and \
            'Accept' in request.headers and \
            'Content-Type' in request.headers and \
            'application/json' in request.headers.get('Accept') and \
            'application/json' in request.headers.get('Content-Type'):
        return handle_put_request(request, json_id)
    elif request.method == 'DELETE':
        return handle_delete_request(request, json_id)
    else:
        resp = redirect(url_for('index'))
        return add_CORS_headers(resp)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
