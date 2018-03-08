""" JSONkeeper

    A flask web application for storing JSON documents; with some special
    functions for JSON-LD.
"""

import firebase_admin
from flask import Flask, jsonify
from pyld import jsonld
from werkzeug.exceptions import default_exceptions, HTTPException
from werkzeug.routing import BaseConverter
from jsonkeeper.config import Cfg
from jsonkeeper.subroutines import add_CORS_headers


def create_app(**kwargs):
    app = Flask(__name__)
    with app.app_context():
        app.cfg = Cfg()
        if kwargs:
            app.testing = True
            app.cfg.set_debug_config(**kwargs)

        class RegexConverter(BaseConverter):
            """ Make it possible to distinguish routes by <regex("[exampl]"):>.

                https://stackoverflow.com/a/5872904
            """

            def __init__(self, url_map, *items):
                super(RegexConverter, self).__init__(url_map)
                self.regex = items[0]

        app.url_map.converters['regex'] = RegexConverter

        if app.cfg.use_frbs():
            cred = firebase_admin.credentials.Certificate(app.cfg.frbs_conf())
            firebase_admin.initialize_app(cred)
        app.config['SQLALCHEMY_DATABASE_URI'] = app.cfg.db_uri()
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        from jsonkeeper.models import db
        db.init_app(app)
        db.create_all()

        jsonld.set_document_loader(jsonld.requests_document_loader(timeout=7))

        for code in default_exceptions.keys():
            """ Make app return exceptions in JSON form. Also add CORS headers.

                Based on http://flask.pocoo.org/snippets/83/ but updated to use
                register_error_handler method.
                Note: this doesn't seem to work for 405 Method Not Allowed in
                      an Apache + gnunicorn setup.
            """

            @app.errorhandler(code)
            def make_json_error(error):
                resp = jsonify(message=str(error))
                resp.status_code = (error.code
                                    if isinstance(error, HTTPException)
                                    else 500)
                return add_CORS_headers(resp)

        from jsonkeeper.views import jk
        app.register_blueprint(jk)

        return app
