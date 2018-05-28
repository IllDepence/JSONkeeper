import json
from jsonkeeper.subroutines import (
    acceptable_accept_mime_type,
    acceptable_content_type,
    CORS_preflight_response,
    add_CORS_headers,
    get_access_token,
    get_JSON_string_by_ID,
    get_JSON_metadata_by_ID,
    get_document_IDs_by_access_token,
    get_actstr_collection_pages,
    get_actstr_collection,
    handle_post_request,
    handle_get_request,
    handle_put_request,
    handle_delete_request,
    handle_doc_status_request)
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for)
from util.iiif import Curation
from jsonkeeper.models import JSON_document

jk = Blueprint('jk', __name__)


@jk.route('/')
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

        coll_url = '{}{}'.format(current_app.cfg.serv_url(),
                                 url_for('jk.activity_stream_collection'))
        status_msg += (' Serving an Activity Stream OrderedCollection with {} '
                       'OrderedCollectionPages at {}'.format(num_col_pages,
                                                             coll_url))

    if request.accept_mimetypes.accept_json:
        resp = jsonify({'message': status_msg})
        return add_CORS_headers(resp), 200
    else:
        resp = Response(status_msg)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        return add_CORS_headers(resp), 200


@jk.route('/{}'.format(current_app.cfg.api_path()),
          methods=['GET', 'POST', 'OPTIONS'])
def api():
    """ API endpoint for posting new JSON documents.

        Allow GET access to send human visitors to the info page.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'POST' and \
            acceptable_accept_mime_type(request) and \
            acceptable_content_type(request):
        return handle_post_request(request)
    else:
        resp = redirect(url_for('jk.index'))
        return add_CORS_headers(resp)


@jk.route('/{}'.format(current_app.cfg.as_coll_url()),
          methods=['GET', 'OPTIONS'])
def activity_stream_collection():
    """ Special API endpoint for serving an Activity Stream in form of a
        as:Collection.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)

    coll_json = get_actstr_collection()

    if coll_json:
        resp = Response(coll_json)
        resp.headers['Content-Type'] = 'application/activity+json'
        return add_CORS_headers(resp), 200
    else:
        return abort(404, 'Activity Stream does not exist.')


@jk.route('/{}/userlist'.format(current_app.cfg.api_path()),
          methods=['GET', 'OPTIONS'])
def api_userlist():
    """ Return a list of URLs to all documents stored with the same access
        token as this request.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)

    token = get_access_token(request)
    ids = get_document_IDs_by_access_token(token)
    urls = []

    for aid in ids:
        urls.append('{}{}'.format(current_app.cfg.serv_url(),
                                  url_for('jk.api_json_id', json_id=aid)))
    resp = jsonify(urls)
    return add_CORS_headers(resp), 200


@jk.route('/{}/<regex("{}"):json_id>/range<r_num>'.format(
                                                current_app.cfg.api_path(),
                                                current_app.cfg.doc_id_patt()),
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


@jk.route('/{}/<regex("{}"):json_id>/status'.format(current_app.cfg.api_path(),
                                              current_app.cfg.doc_id_patt()),
          methods=['GET', 'PATCH', 'OPTIONS'])
def api_json_id_status(json_id):
    """ API endpoint for retrieving and changing JSON documents' metadata.
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method in ['GET', 'PATCH'] and \
            request.accept_mimetypes.accept_json:
        return handle_doc_status_request(request, json_id)
    else:
        resp = redirect(url_for('jk.index'))
        return add_CORS_headers(resp)


@jk.route('/{}/<regex("{}"):json_id>'.format(current_app.cfg.api_path(),
                                             current_app.cfg.doc_id_patt()),
          methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
def api_json_id(json_id):
    """ API endpoint for retrieving, updating and deleting JSON documents
    """

    if request.method == 'OPTIONS':
        return CORS_preflight_response(request)
    elif request.method == 'GET' and \
            acceptable_accept_mime_type(request):
        return handle_get_request(request, json_id)
    elif request.method == 'PUT' and \
            acceptable_accept_mime_type(request) and \
            acceptable_content_type(request):
        return handle_put_request(request, json_id)
    elif request.method == 'DELETE':
        return handle_delete_request(request, json_id)
    else:
        resp = redirect(url_for('jk.index'))
        return add_CORS_headers(resp)
