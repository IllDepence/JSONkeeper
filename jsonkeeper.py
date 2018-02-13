""" JSONkeeper

    Minimal web app made for API access to store and retrieve JSON.
"""

import firebase_admin
import json
import re
import uuid
from collections import OrderedDict
from firebase_admin import auth as firebase_auth
from flask import abort, Flask, jsonify, redirect, request, Response, url_for
from flask_sqlalchemy import SQLAlchemy
from pyld import jsonld
from sqlalchemy.sql import func
from util.iiif import Curation
from util.activity_stream import (ASCollection, ASCollectionPage,
                                  ActivityBuilder)
from util.config import Cfg
from werkzeug.exceptions import default_exceptions, HTTPException


app = Flask(__name__)
app.cfg = Cfg()

if app.cfg.use_frbs():
    cred = firebase_admin.credentials.Certificate(app.cfg.frbs_conf())
    firebase_admin.initialize_app(cred)
app.config['SQLALCHEMY_DATABASE_URI'] = app.cfg.db_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class JSON_document(db.Model):
    id = db.Column(db.String(255), primary_key=True)
    access_token = db.Column(db.String(255))
    json_string = db.Column(db.UnicodeText())
    created_at = db.Column(db.DateTime(timezone=True),
                           server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True),
                           onupdate=func.now())

db.create_all()
jsonld.set_document_loader(jsonld.requests_document_loader(timeout=3))

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


def acceptable_content_type(request):
    """ Given a request, assess whether or not the content type is acceptable.

        We allow 'application/json' as well as any content type in the form of
        'application/<something>+json'.where <something> is a string of one or
        more characters that can be anything except for the forward slash "/".
    """

    patt = re.compile('^application/([^/]+\+)?json$')
    if patt.match(request.headers.get('Content-Type')):
        return True
    return False


def update_activity_stream(json_string, json_id, root_elem_types):
    """ If configured, generate Activities from the given JSON-LD document. If
        we generate Activities for the first time, we also create the
        Collection; otherwise we just update it.
    """

    if not app.cfg.serve_as() or \
       len(set(root_elem_types).intersection(set(app.cfg.as_types()))) == 0:
        return

    coll_json = get_actstr_collection()
    col_ld_id = '{}{}'.format(app.cfg.serv_url(),
                              url_for('activity_stream_collection'))
    if coll_json:
        page_docs = get_actstr_collection_pages()

        col = ASCollection(None, app.cfg.as_coll_store_id(), db,
                           JSON_document)  # BAD
        col.restore_from_json(coll_json, page_docs)
    else:
        col = ASCollection(col_ld_id, app.cfg.as_coll_store_id(), db,
                           JSON_document)  # BAD

    cur = Curation(None)
    cur.from_json(json_string)

    page_store_id = '{}{}'.format(app.cfg.as_pg_store_pref(), uuid.uuid4())
    page_ld_id = '{}{}'.format(app.cfg.serv_url(),
                               url_for('api_json_id', json_id=page_store_id))

    page = ASCollectionPage(page_ld_id, page_store_id, db,
                            JSON_document)  # BAD

    # Create
    create = ActivityBuilder.build_create(cur.get_id())
    page.add(create)
    # Reference
    for cid in cur.get_all_canvas_ids():
        ref = ActivityBuilder.build_reference(cur.get_id(), cid)
        page.add(ref)
    # Offerings
    for dic in cur.get_range_summary():
        range_id = dic.get('ran')
        manifest_id = dic.get('man')
        off = ActivityBuilder.build_offer(cur.get_id(), range_id, manifest_id)
        page.add(off)

    col.add(page)


def handle_incoming_json_ld(json_string, json_id):
    """ If configured, rewrite root level JSON-LD @ids.

        (Special treatment for sc:Range atm -- generalize later if possible.)
    """

    # check JSON-LD validity
    try:
        root_elem = json.loads(json_string, object_pairs_hook=OrderedDict)
        # https://json-ld.org/spec/latest/json-ld-api/#expansion-algorithms
        expanded = jsonld.expand(root_elem)
    except:
        return abort(400, 'No valid JSON-LD provided (this can be due to a con'
                          'text that can not be resolved).')

    # rewrite @ids
    id_change = False
    if app.cfg.id_rewr():
        root_elem_types = expanded[0]['@type']
        if len(set(root_elem_types).intersection(set(app.cfg.id_types()))) > 0:
            root_elem['@id'] = '{}{}'.format(app.cfg.serv_url(),
                                             url_for('api_json_id',
                                                     json_id=json_id))

            # Special hardcoded custom behaviour for Curations here :F
            new_ranges = []
            if 'http://codh.rois.ac.jp/iiif/curation/1#Curation' in \
               root_elem_types:
                for idx, ran in enumerate(root_elem['selections']):
                    ran['@id'] = '{}/range{}'.format(root_elem['@id'], idx+1)
                    new_ranges.append(ran)
            root_elem['selections'] = new_ranges

            json_string = json.dumps(root_elem)
            id_change = True

    return json_string, id_change, root_elem_types


def _write_json__request_wrapper(request, given_id, access_token):
    """ 1. do request specific things
        2. call _write_json__request_independent
        3. do response specific things
    """

    # 1. do request specific things
    json_bytes = request.data
    try:
        json_string = json_bytes.decode('utf-8')
        json.loads(json_string)
    except:
        return abort(400, 'No valid JSON provided.')

    if given_id is None:
        json_id = str(uuid.uuid4())
    else:
        json_id = given_id

    is_json_ld = False
    if request.headers.get('Content-Type') == 'application/ld+json':
        is_json_ld = True

    is_new_document = not bool(given_id)
    # 2. call _write_json__request_independent
    json_string = _write_json__request_independent(json_string, json_id,
                                                   access_token,
                                                   is_new_document, is_json_ld)

    # 3. do response specific things
    resp = Response(json_string)
    if given_id is None:
        resp.headers['Location'] = url_for('api_json_id', json_id=json_id)
    resp.headers['Content-Type'] = request.headers.get('Content-Type')

    return resp


def _write_json__request_independent(json_string, json_id, access_token,
                                     is_new_document, is_json_ld):
    """ Get JSON or JSON-LD and save it to DB.`
    """

    id_change = False
    # If we get JSON-LD, examine it and remember if any documents with
    # resolvable @id (for which we might want to generate new Activities in our
    # Activity Stream) will be saved. After saving update the AS.
    if is_json_ld:
        json_string, id_change, root_elem_types = \
                                  handle_incoming_json_ld(json_string, json_id)

    if is_new_document:
        # If this is a new JSON document we need to create a database record
        json_doc = JSON_document(id=json_id,
                                 access_token=access_token,
                                 json_string=json_string)
        db.session.add(json_doc)
        db.session.commit()
    else:
        # For existing documents we need to update the database record
        json_doc = JSON_document.query.filter_by(id=json_id).first()
        json_doc.json_string = json_string
        db.session.commit()

    if id_change:
        # We got JSON-LD and gave it a resolvable id. Depending on the config
        # we might want to add some Activities to our AS.
        update_activity_stream(json_string, json_id, root_elem_types)

    return json_string


def write_json(request, given_id, access_token):
    """ Write JSON contents from request to DB. Used for POST requests (new
        document) and PUT requests (update document). Dealing with access
        tokens (given or not in case of POST, correct or not in case of PUT)
        should happen *before* this method is called.

        If the parameter `given_id` is set the corresponding JSON document is
        expected to already exist.

        This function calls _write_json__request_wrapper which in turn calls
        _write_json__request_independent. If JSONkeeper performs internal JSON
        document writing it will just call _write_json__request_independent.
    """

    return _write_json__request_wrapper(request, given_id, access_token)


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


def get_access_token(request):
    """ Given a request object, return the resulting access token. This can be:
        - a Firebase uid
        - a freely chosen access token (managed by the client)
        - '' (empty string) in case no access token is provided
        - False in case a Firebase ID token could not be verified
    """

    if app.cfg.use_frbs() and 'X-Firebase-ID-Token' in request.headers:
        id_token = request.headers.get('X-Firebase-ID-Token')
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            access_token = uid
        except:
            access_token = False
    elif 'X-Access-Token' in request.headers:
        access_token = request.headers.get('X-Access-Token')
    else:
        access_token = ''
    return access_token


def get_JSON_string_by_ID(json_id):
    json_string = None

    json_doc = JSON_document.query.filter_by(id=json_id).first()
    if json_doc:
        json_string = json_doc.json_string

    return json_string


def get_actstr_collection_pages():
    query_patt = '{}%'.format(app.cfg.as_pg_store_pref())
    return JSON_document.query.filter(JSON_document.id.like(query_patt)).all()


def get_actstr_collection():
    return get_JSON_string_by_ID(app.cfg.as_coll_store_id())


def handle_post_request(request):
    """ Handle request with the purpose of storing a new JSON document.
    """

    access_token = get_access_token(request)
    if access_token is False:
        return abort(403, 'Firebase ID token could not be verified.')

    resp = write_json(request, None, access_token)

    return add_CORS_headers(resp), 201


def handle_get_request(request, json_id):
    """ Handle request with the purpose of retrieving a JSON document.
    """

    json_string = get_JSON_string_by_ID(json_id)

    if json_string:
        resp = Response(json_string)
        resp.headers['Content-Type'] = 'application/json'
        return add_CORS_headers(resp), 200
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def handle_put_request(request, json_id):
    """ Handle request with the purpose of updating a JSON document.
    """

    json_string = get_JSON_string_by_ID(json_id)

    if json_string:
        access_token = get_access_token(request)
        if access_token is False:
            return abort(403, 'Firebase ID token could not be verified.')
        json_doc = JSON_document.query.filter_by(id=json_id).first()
        if json_doc.access_token == access_token or \
                json_doc.access_token == '':
            resp = write_json(request, json_id, access_token)
            return add_CORS_headers(resp), 200
        else:
            return abort(403, 'X-Access-Token header value not correct.')
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def handle_delete_request(request, json_id):
    """ Handle request with the purpose of deleting a JSON document.
    """

    json_string = get_JSON_string_by_ID(json_id)

    if json_string:
        access_token = get_access_token(request)
        if access_token is False:
            return abort(403, 'Firebase ID token could not be verified.')
        json_doc = JSON_document.query.filter_by(id=json_id).first()
        if json_doc.access_token == access_token or \
                json_doc.access_token == '':
            db.session.delete(json_doc)
            db.session.commit()
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

    num_files = JSON_document.query.count()
    status_msg = 'Storing {} JSON documents.'.format(num_files)

    coll_json = get_actstr_collection()
    if coll_json:

        num_col_pages = 0
        page_docs = get_actstr_collection_pages()
        if page_docs:
            num_col_pages = len(page_docs)

        coll_url = '{}{}'.format(app.cfg.serv_url(),
                                 url_for('activity_stream_collection'))
        status_msg += (' Serving an Activity Stream Collection with {} Collect'
                       'ionPages at {}'.format(num_col_pages, coll_url))

    if request.accept_mimetypes.accept_json:
        resp = jsonify({'message': status_msg})
        return add_CORS_headers(resp), 200
    else:
        resp = Response(status_msg)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        return add_CORS_headers(resp), 200


@app.route('/{}'.format(app.cfg.api_path()),
           methods=['GET', 'POST', 'OPTIONS'])
def api():
    """ API endpoint for posting new JSON documents.

        Allow GET access to send human visitors to the info page.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'POST' and \
            request.accept_mimetypes.accept_json and \
            acceptable_content_type(request):
        return handle_post_request(request)
    else:
        resp = redirect(url_for('index'))
        return add_CORS_headers(resp)


@app.route('/{}'.format(app.cfg.as_coll_url()), methods=['GET', 'OPTIONS'])
def activity_stream_collection():
    """ Special API endpoint for serving an Activity Stream in form of a
        as:Collection.
    """

    coll_json = get_actstr_collection()

    if coll_json:
        resp = Response(coll_json)
        resp.headers['Content-Type'] = 'application/activity+json'
        return add_CORS_headers(resp), 200
    else:
        return abort(404, 'Activity Stream does not exist.')


@app.route('/{}/<json_id>/range<r_num>'.format(app.cfg.api_path()),
           methods=['GET', 'OPTIONS'])
def api_json_id_range(json_id, r_num):
    """ Special API endpoint for sc:Ranges in JSON-LD documents.
    """

    json_string = get_JSON_string_by_ID(json_id)
    if json_string:
        cur = Curation(None)
        cur.from_json(json_string)
        if 'selections' not in cur.cur:
            return abort(404, ('JSON document with ID {} does not contain any '
                               'Ranges.'.format(json_id)))

        range_dict = cur.get_nth_range(int(r_num))

        if range_dict:
            resp = Response(json.dumps(range_dict))
            resp.headers['Content-Type'] = 'application/json'
            return add_CORS_headers(resp), 200
        else:
            return abort(404, ('This JSON document does not contain {} ranges.'
                               '').format(r_num))
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


@app.route('/{}/<json_id>'.format(app.cfg.api_path()),
           methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
def api_json_id(json_id):
    """ API endpoint for retrieving, updating and deleting JSON documents
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'GET' and \
            request.accept_mimetypes.accept_json:
        return handle_get_request(request, json_id)
    elif request.method == 'PUT' and \
            request.accept_mimetypes.accept_json and \
            acceptable_content_type(request):
        return handle_put_request(request, json_id)
    elif request.method == 'DELETE':
        return handle_delete_request(request, json_id)
    else:
        resp = redirect(url_for('index'))
        return add_CORS_headers(resp)
