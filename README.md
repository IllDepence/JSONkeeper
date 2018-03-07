![JSONkeeper](logo_500px.png)

A flask web application for storing JSON documents; with some special functions for JSON-LD.

[Setup](#setup)  
[Config](#config)  
[Serve](#serve)  
[Test](#test)  
[Usage](#usage)  
&nbsp;&nbsp;[Access tokens](#access-tokens)  
&nbsp;&nbsp;[JSON-LD](#json-ld)  
&nbsp;&nbsp;[Activity Stream](#activity-stream)  
[Logo](#logo)  
[Support](#support)

## Setup
* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## Config
section | key | default | explanation
------- | --- | ------- | -----------
environment | db\_uri | sqlite:///keep.db | a [SQLAlchemy database URI](http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls)
&zwnj;      | server\_uri | http://localhost:5000 | server URL up to the TLD or port, without any path<br>(e.g. `http://ikeepjson.com` but not `http://sirtetris.com/jsonkeeper`)
&zwnj;      | custom\_api\_path | api | specifies the endpoint for API access<br>(e.g. `api` →  `http://ikeepjson.com/api` or `http://sirtetris.com/jsonkeeper/api`)
firebase | service\_account\_key\_file | `None` | can be set for Google Firebase integration ([details below](#access-tokens))
json-ld | rewrite\_types | `[]` | comma seperated list of [JSON-LD](https://json-ld.org/spec/latest/json-ld/) types for which [@id](https://json-ld.org/spec/latest/json-ld/#node-identifiers) should be set to a dereferencable URL ([details below](#json-ld))
activity\_stream | collection\_url | `None` | path under which an [Activity Stream](https://www.w3.org/TR/activitystreams-core/) Collection should be served (e.g. `as/collection.json` →  `http://ikeepjson.com/as/collection.json`) ([details below](#activity-stream))
&zwnj;           | activity\_generating\_types | `[]` | comma seperated list of JSON-LD types for which Activites (`Create`, `Reference`, `Offer`) should be created

## Serve
### Development
    $ source venv/bin/activate
    $ python3 run.py debug

### Deploy
#### Apache2 + gunicorn example
* configure server URL in `config.ini`:

        server_url = http://localhost

* add proxy rules to apache (e.g. in `/etc/apache2/sites-enabled/000-default.conf` within the `<VirtualHost *:80>` block):

        ProxyPassMatch "^/JSONkeeper/(.*)" "http://localhost:8000/JSONkeeper/$1"
        ProxyPassReverse "^/JSONkeeper/(.*)" "http://localhost:8000/JSONkeeper/$1"

* restart apache, get and start gunicorn

        $ sudo a2enmod proxy_http
        $ sudo service apache2 reload
        $ source venv/bin/activate
        $ pip install gunicorn
        $ gunicorn --bind localhost:8000 -e SCRIPT_NAME='/JSONkeeper' 'jsonkeeper:create_app()'

#### Alternatives
* [Deployment Options](http://flask.pocoo.org/docs/0.12/deploying/) (be aware that JSONkeeper uses the [Application Factories](http://flask.pocoo.org/docs/0.12/patterns/appfactories/) pattern, some adjustments to the deployment options listed may be necessary)

## Test
* if you make changes to the code, basic testing can be done with

        $ flake8 *.py jsonkeeper/*.py util/*.py
        $ source venv/bin/activate
        $ python3 test.py

## Usage examples
### Create
    $ curl -X POST \
           -d '{"foo":"bar"}' \
           -H 'Accept: application/json' \
           -H 'Content-Type: application/json' \
           http://127.0.0.1/JSONkeeper/api
&zwnj;

    HTTP/1.0 201 CREATED
    Location: http://127.0.0.1/JSONkeeper/api/e14f58b0-d0ec-4f35-a83b-49c613daa7a3
    
    {"foo":"bar"}
### Retrieve
    $ curl -X GET \
           -H 'Accept: application/json' \
           http://127.0.0.1/JSONkeeper/api/e14f58b0-d0ec-4f35-a83b-49c613daa7a3
&zwnj;

    HTTP/1.0 200 OK
    
    {"foo":"bar"}
### Update
    $ curl -X PUT \
           -d '{"bar":"baz"}' \
           -H 'Accept: application/json' \
           -H 'Content-Type: application/json' \
           http://127.0.0.1/JSONkeeper/api/e14f58b0-d0ec-4f35-a83b-49c613daa7a3
&zwnj;

    HTTP/1.0 200 OK
    
    {"bar":"baz"}
### Delete
    $ curl -X DELETE  \
           http://127.0.0.1/JSONkeeper/api/e14f58b0-d0ec-4f35-a83b-49c613daa7a3
&zwnj;

    HTTP/1.0 200 OK

### Access tokens

#### Restricting access
* **Firebase** (if the [configuration](#config) points to a valid [Firebase service account key file](https://firebase.google.com/docs/admin/setup#add_firebase_to_your_app))
    * provide a header `X-Firebase-ID-Token` when creating a JSON document
    * the document will only be created if the ID token can be verified, otherwise a `403 FORBIDDEN` is returned; if the document is created, the application stores the authenticated user's UID
    * subsequent `PUT` and `DELETE` requests are only executed when a `X-Firebase-ID-Token` header is provided that, when decoded, results in the same UID, otherwise a `403 FORBIDDEN` is returned
* **Self managed**
    * provide a header `X-Access-Token` when creating a JSON document
    * subsequent `PUT` and `DELETE` requests are only executed when a `X-Access-Token` header with the same value is provided, otherwise a `403 FORBIDDEN` is returned

#### List of documents for a given token
Accessing `/<api_path>/userlist` will return a list of all hosted documents with a matching access token. This means

* no access token → all unrestricted access documents
* X-Access-Token → all documents created with this token
* X-Firebase-ID-Token → all documents created by this user

## JSON-LD
JSONkeeper can be configured to host JSON-LD documents in a sensible manner.

#### Example:
If the [configuration](#config) contains a section

    [json-ld]
    rewrite_types = http://codh.rois.ac.jp/iiif/curation/1#Curation,
                    http://iiif.io/api/presentation/2#Range

and a [POST](https://github.com/IllDepence/JSONkeeper/blob/master/README.md#create) request is issued with `Content-Type` set to `application/ld+json` *and* the request's content is a valid JSON-LD document whose [expanded](https://json-ld.org/spec/latest/json-ld-api/#expansion-algorithms) `@type` is listed in the configuration, *then* the document's [@id](https://json-ld.org/spec/latest/json-ld/#node-identifiers) is set to the URL where JSONkeeper will serve the document.

Special behaviour is defined for `http://codh.rois.ac.jp/iiif/curation/1#Curation`. `http://iiif.io/api/presentation/2#Range` nodes within the Curation also are assigned a dereferencable `@id`.

## Activity Stream
JSONkeeper can be configured to serve an [Activity Stream](https://www.w3.org/TR/activitystreams-core/) in form of a Collection. The only type of Activity that is generated right now for all types of JSON-LD documents is [Create](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-create).

Special behaviour is defined for `http://codh.rois.ac.jp/iiif/curation/1#Curation`. Create, Reference and Offer Activities are generated.

- - -

## Logo
The JSONkeeper logo uses image content from [十二類絵巻](http://codh.rois.ac.jp/pmjt/book/200015137/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The JSONkeeper logo itself is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier.

## Support
Sponsored by the National Institute of Informatics.  
Supported by the Center for Open Data in the Humanities, Joint Support-Center for Data Science Research, Research Organization of Information and Systems.
