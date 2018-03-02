import json
import re
import uuid
from collections import OrderedDict
from flask import abort, current_app, Response, url_for
from firebase_admin import auth as firebase_auth
from util.iiif import Curation
from util.activity_stream import (ASCollection, ASCollectionPage,
                                  ActivityBuilder)
from jsonkeeper.models import db, JSON_document
from pyld import jsonld


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

    if not current_app.cfg.serve_as() or \
       len(set(root_elem_types).intersection(set(current_app.cfg.as_types())
                                             )) == 0:
        return

    coll_json = get_actstr_collection()
    col_ld_id = '{}{}'.format(current_app.cfg.serv_url(),
                              url_for('jk.activity_stream_collection'))
    if coll_json:
        page_docs = get_actstr_collection_pages()

        col = ASCollection(None, current_app.cfg.as_coll_store_id())
        col.restore_from_json(coll_json, page_docs)
    else:
        col = ASCollection(col_ld_id, current_app.cfg.as_coll_store_id())

    page_store_id = '{}{}'.format(current_app.cfg.as_pg_store_pref(),
                                  uuid.uuid4())
    page_ld_id = '{}{}'.format(current_app.cfg.serv_url(),
                               url_for('jk.api_json_id', json_id=page_store_id))

    page = ASCollectionPage(page_ld_id, page_store_id)

    cur_type = 'http://codh.rois.ac.jp/iiif/curation/1#Curation'
    if cur_type not in root_elem_types:
        # Create
        json_dict = json.loads(json_string)
        create = ActivityBuilder.build_create(json_dict['@id'])
        page.add(create)
    else:
        # Special hardcoded custom behaviour for Curations here :F
        # ↓ FIXME: @context assumptions (prefixes)
        cur = Curation(None)
        cur.from_json(json_string)
        typed_cur = {'@type': 'cr:Curation', '@id': cur.get_id()}
        # Create
        create = ActivityBuilder.build_create(typed_cur)
        page.add(create)
        # Reference
        for cid in cur.get_all_canvas_ids():
            typed_canvas = {'@type': 'sc:Canvas', '@id': cid}
            ref = ActivityBuilder.build_reference(typed_cur, typed_canvas)
            page.add(ref)
        # Offerings
        for dic in cur.get_range_summary():
            ran_id = dic.get('ran')
            man_id = dic.get('man')
            typed_ran = {'@type': 'sc:Range', '@id': ran_id}
            typed_man = {'@type': 'sc:Manifest', '@id': man_id}
            off = ActivityBuilder.build_offer(typed_cur, typed_ran, typed_man)
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
    root_elem_types = []
    id_change = False
    if current_app.cfg.id_rewr():
        root_elem_types = expanded[0]['@type']
        if len(set(root_elem_types
                   ).intersection(set(current_app.cfg.id_types()))) > 0:
            root_elem['@id'] = '{}{}'.format(current_app.cfg.serv_url(),
                                             url_for('jk.api_json_id',
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
        resp.headers['Location'] = url_for('jk.api_json_id', json_id=json_id)
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

    if current_app.cfg.use_frbs() and 'X-Firebase-ID-Token' in request.headers:
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


def get_document_IDs_by_access_token(token):
    docs = JSON_document.query.filter_by(access_token=token).all()
    if docs:
        return [d.id for d in docs]
    else:
        return []


def get_actstr_collection_pages():
    query_patt = '{}%'.format(current_app.cfg.as_pg_store_pref())
    return JSON_document.query.filter(JSON_document.id.like(query_patt)).all()


def get_actstr_collection():
    return get_JSON_string_by_ID(current_app.cfg.as_coll_store_id())


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
