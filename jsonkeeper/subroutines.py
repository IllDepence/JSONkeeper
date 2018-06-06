import json
import re
import uuid
from collections import OrderedDict
from flask import abort, current_app, Response, url_for
from firebase_admin import auth as firebase_auth
from util.iiif import Curation
from util.activity_stream import (ASOrderedCollection, ASOrderedCollectionPage,
                                  ActivityBuilder)
from jsonkeeper.models import db, JSON_document
from pyld import jsonld


def acceptable_accept_mime_type(request):
    """ Given a request, assess whether or not a mime type that is accepted by
        the client can be returned.

        For most requests, Werkzeug's request.accept_mimetypes.accept_json is
        sufficient. But in case of POST and PUT requests we also need to allow
        clients that only accept 'application/ld+json' when the request's
        content is 'application/ld+json'.
    """

    if request.method in ['POST', 'PUT'] and \
            request.headers.get('Content-Type') == 'application/ld+json':
        return ('application/ld+json' in request.accept_mimetypes or
                'application/json' in request.accept_mimetypes)
    else:
        return request.accept_mimetypes.accept_json


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


def get_new_as_ordered_collection_page():
    """ Return a Activity Stream OrderedCollectionPage.
    """

    page_store_id = '{}{}'.format(current_app.cfg.as_pg_store_pref(),
                                  uuid.uuid4())
    page_ld_id = '{}{}'.format(current_app.cfg.serv_url(),
                               url_for('jk.api_json_id',
                                       json_id=page_store_id))
    page = ASOrderedCollectionPage(page_ld_id, page_store_id)
    return page


def get_as_ordered_collection():
    """ Return the Activity Stream OrderedCollection. If it doesn't exist yet,
        create it.
    """

    coll_json = get_actstr_collection()
    col_ld_id = '{}{}'.format(current_app.cfg.serv_url(),
                              url_for('jk.activity_stream_collection'))
    if coll_json:
        page_docs = get_actstr_collection_pages()

        col = ASOrderedCollection(None, current_app.cfg.as_coll_store_id())
        col.restore_from_json(coll_json, page_docs)
    else:
        col = ASOrderedCollection(col_ld_id,
                                  current_app.cfg.as_coll_store_id())
    return col


def update_activity_stream_create(json_string, json_id, root_elem_types):
    """ If configured, generate Activities for the creation of the given
        JSON-LD document.
    """

    if not current_app.cfg.serve_as() or \
       len(set(root_elem_types).intersection(set(current_app.cfg.as_types())
                                             )) == 0:
        return

    col = get_as_ordered_collection()
    page = get_new_as_ordered_collection_page()

    cur_type = 'http://codh.rois.ac.jp/iiif/curation/1#Curation'
    if cur_type not in root_elem_types:
        # Create
        json_dict = json.loads(json_string)
        create = ActivityBuilder.build_create({'@id': json_dict['@id'],
                                               '@type': json_dict['@type']})
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
        ran_lst, ran_dic = cur.get_range_summary()
        for mid, cid in cur.get_all_canvases(ran_dic):
            typed_canvas = {'@type': 'sc:Canvas',
                            '@id': cid,
                            'within': {'@type': 'sc:Manifest',
                                       '@id': mid
                                      }
                           }
            ref = ActivityBuilder.build_reference(typed_cur, typed_canvas)
            page.add(ref)
        # Offerings
        for dic in ran_lst:
            ran_id = dic.get('ran')
            man_id = dic.get('man')
            typed_ran = {'@type': 'sc:Range', '@id': ran_id}
            typed_man = {'@type': 'sc:Manifest', '@id': man_id}
            off = ActivityBuilder.build_offer(typed_cur, typed_ran, typed_man)
            page.add(off)

    col.add(page)
    db.session.commit()


def update_activity_stream_update(json_string, json_id, root_elem_types):
    """ If configured, generate Activities for the update of the given JSON-LD
        document.
    """

    if not current_app.cfg.serve_as() or \
       len(set(root_elem_types).intersection(set(current_app.cfg.as_types())
                                             )) == 0:
        return

    col = get_as_ordered_collection()
    page = get_new_as_ordered_collection_page()

    # Update
    json_dict = json.loads(json_string)
    update = ActivityBuilder.build_update({'@id': json_dict['@id'],
                                           '@type': json_dict['@type']})
    page.add(update)

    col.add(page)
    db.session.commit()


def update_activity_stream_delete(json_string, json_id):
    """ If configured, generate Activities for the update of the given JSON-LD
        document.
    """

    if not current_app.cfg.serve_as():
        return

    col = get_as_ordered_collection()
    page = get_new_as_ordered_collection_page()

    # Delete
    json_dict = json.loads(json_string)
    update = ActivityBuilder.build_delete({'@id': json_dict['@id'],
                                           '@type': json_dict['@type']})
    page.add(update)

    col.add(page)
    db.session.commit()


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


def _write_json__request_wrapper(request, given_id, access_token, private):
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
                                                   access_token, private,
                                                   is_new_document, is_json_ld)

    # 3. do response specific things
    resp = Response(json_string)
    if given_id is None:
        resp.headers['Location'] = url_for('jk.api_json_id', json_id=json_id)
    resp.headers['Content-Type'] = request.headers.get('Content-Type')

    return resp


def _write_json__request_independent(json_string, json_id, access_token,
                                     private, is_new_document, is_json_ld):
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
                                 private=private,
                                 json_string=json_string)
        db.session.add(json_doc)
        db.session.commit()
    else:
        # For existing documents we need to update the database record
        json_doc = get_JSON_doc_by_ID(json_id)
        json_doc.json_string = json_string
        db.session.commit()

    if is_json_ld and is_new_document and id_change and not private:
        # We got JSON-LD and gave it a resolvable id. Depending on the config
        # we might want to add some Activities to our AS.
        update_activity_stream_create(json_string, json_id, root_elem_types)
    elif is_json_ld and not is_new_document and not private:
        # We got JSON-LD with a PUT request (not a new document), so we might
        # want to add an Update activity to our AS.
        update_activity_stream_update(json_string, json_id, root_elem_types)

    return json_string


def write_json(request, given_id, access_token, private):
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

    return _write_json__request_wrapper(request, given_id, access_token,
                                        private)


def patch_metadata(request, json_id):
    """ Partially update the metadata associated with a JSON document.
    """

    json_bytes = request.data
    try:
        json_string = json_bytes.decode('utf-8')
        json_dict = json.loads(json_string)
    except:
        return abort(400, 'No valid JSON provided.')

    if 'private' in json_dict and json_dict['private'] in ['true', 'false']:
        json_doc = get_JSON_doc_by_ID(json_id)
        if json_dict['private'] == 'false':
            if json_doc.private == True:
                # retrospectively set to public, need to create a Create
                # Activity to make the document visible to crawlers
                update_activity_stream_create(json_doc.json_string,
                                              json_doc.id,
                                              current_app.cfg.as_types())
                # NOTE: the thrid argument in above function call is a bit of a
                #       hack. nice the document was already accepted into
                #       JSONkeeper, instead of expanding the JSON-LD again and
                #       checking it in update_activity_stream_create, we just
                #       pass the list of JSON-LD types that the function checks
                #       against
            json_doc.private = False
        elif json_dict['private'] == 'true':
            if json_doc.private == False:
                # retrospectively set to private, need to create a Delete
                # Activity and hope that crawlers believe us
                update_activity_stream_delete(json_doc.json_string,
                                              json_doc.id)
            json_doc.private = True
        db.session.commit()
        return Response(json.dumps(get_JSON_metadata_by_ID(json_id)))
    else:
        return abort(400, 'No appropriate update values provided.')


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


def get_private_setting(request):
    """ Given a request object, return the resulting `private` setting.
        - True if set to "true"
        - False if set to false nor not set at all
    """

    if 'X-Private' in request.headers and \
            request.headers.get('X-Private') == 'true':
        return True
    return False


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


def get_JSON_doc_by_ID(json_id):
    return JSON_document.query.filter_by(id=json_id).first()


def get_JSON_string_by_ID(json_id):
    json_string = None

    json_doc = get_JSON_doc_by_ID(json_id)
    if json_doc:
        json_string = json_doc.json_string

    return json_string


def get_JSON_metadata_by_ID(json_id):
    metadata = None

    json_doc = get_JSON_doc_by_ID(json_id)
    if json_doc:
        metadata = OrderedDict()
        metadata['id'] = json_doc.id
        metadata['access_token'] = json_doc.access_token
        metadata['private'] = bool(json_doc.private)
        metadata['created_at'] = json_doc.created_at.isoformat()
        if json_doc.updated_at:
            metadata['updated_at'] = json_doc.updated_at.isoformat()
        else:
            metadata['updated_at'] = json_doc.updated_at

    return metadata


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
    private = get_private_setting(request)
    if access_token is False:
        return abort(403, 'Firebase ID token could not be verified.')

    resp = write_json(request, None, access_token, private)

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
        private = get_private_setting(request)
        if access_token is False:
            return abort(403, 'Firebase ID token could not be verified.')
        json_doc = get_JSON_doc_by_ID(json_id)
        if json_doc.access_token == access_token or \
                json_doc.access_token == '':
            resp = write_json(request, json_id, access_token, private)
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
        json_doc = get_JSON_doc_by_ID(json_id)
        if json_doc.access_token == access_token or \
                json_doc.access_token == '':
            # DB
            db.session.delete(json_doc)
            db.session.commit()
            # Activity Stream
            sth = json.loads(json_string)
            if current_app.cfg.serve_as() and \
                   type(sth) == dict and \
                   is_in_actstr(sth.get('@id')):
                update_activity_stream_delete(json_string, json_id)
            # Response
            resp = Response('')
            return add_CORS_headers(resp), 200
        else:
            return abort(403, 'X-Access-Token header value not correct.')
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def handle_doc_status_request(request, json_id):
    """ Handle requests with the purpose of retrieving or partually updating
        metadata about a JSON document.
    """

    metadata = get_JSON_metadata_by_ID(json_id)
    if metadata:
        access_token = get_access_token(request)
        if access_token is False:
            return abort(403, 'Firebase ID token could not be verified.')
        if metadata['access_token'] == access_token or \
                metadata['access_token'] == '':
            if request.method == 'GET':
                resp = Response(json.dumps(metadata))
                resp.headers['Content-Type'] = 'application/json'
                return add_CORS_headers(resp), 200
            if request.method == 'PATCH':
                resp = patch_metadata(request, json_id)
                return add_CORS_headers(resp), 200
        else:
            return abort(403, 'X-Access-Token header value not correct.')
    else:
        return abort(404, 'JSON document with ID {} not found'.format(json_id))


def is_in_actstr(doc_id):
    """ Return true if a document with doc)id is in the Activity Stream.
    """

    coll_json = get_actstr_collection()
    if coll_json:
        page_docs = get_actstr_collection_pages()

        col = ASOrderedCollection(None, current_app.cfg.as_coll_store_id())
        col.restore_from_json(coll_json, page_docs)

        for page in page_docs:
            json_obj = json.loads(page.json_string)
            for activity in json_obj.get('orderedItems', []):
                if activity.get('type') == 'Create':
                    doc_id = activity.get('object').get('@id').split('/')[-1]
                elif activity.get('type') in ['Reference', 'Offer']:
                    doc_id = activity.get('origin').get('@id').split('/')[-1]
                if doc_id == doc_id:
                    return True
    return False


def remove_document_from_actstr(to_rem_id):
    """ Given a JSON ID, remove all activities referencing the document with
        that ID from the Activity Stream.

        When this was implemented there was exactly one CollectionPage that
        contains all Activities referencing a given document. As a result
        only the first AS page with a matching activity is deleted.
    """

    return # currently not used because Delete Activities were introduced

    coll_json = get_actstr_collection()
    if coll_json:
        page_docs = get_actstr_collection_pages()

        col = ASOrderedCollection(None, current_app.cfg.as_coll_store_id())
        col.restore_from_json(coll_json, page_docs)

        found = None
        for page in page_docs:
            json_obj = json.loads(page.json_string)
            for activity in json_obj.get('orderedItems', []):
                if activity.get('type') == 'Create':
                    doc_id = activity.get('object').get('@id').split('/')[-1]
                elif activity.get('type') in ['Reference', 'Offer']:
                    doc_id = activity.get('origin').get('@id').split('/')[-1]
                if doc_id == to_rem_id:
                    found = json_obj['id']
                    break
            if found:
                break
        if found:
            # Note: this assumes that all Activities on one CollectionPage
            #       reference the same JSON-LD document.
            page = col.get_page_by_id(found)
            col.remove(page)
            db.session.commit()
            return True
    return False
