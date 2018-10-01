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
* depending on the type of database you are going to use, you might need to install an additional Python database driver (see [SQLAlchemy supported databases](http://docs.sqlalchemy.org/en/latest/core/engines.html#supported-databases))

## Config
section | key | default | explanation
------- | --- | ------- | -----------
environment | db\_uri | sqlite:///keep.db | a [SQLAlchemy database URI](http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls)
&zwnj;      | server\_url | http://localhost:5000 | server URL beginning with the schema and ending with the TLD or port, without any path<br>(e.g. `http://ikeepjson.com` but not `http://sirtetris.com/jsonkeeper`)
api         | api\_path | api | specifies the endpoint for API access<br>(e.g. `json` →  `http://ikeepjson.com/json` or `http://sirtetris.com/jsonkeeper/json`)
&zwnj;      | userdocs\_added\_properties | `[]` | list of additional attributes that are returned by the /userdocs endpoint, if they are contained in a document
&zwnj;      | garbage\_collection\_interval | -1 | garbage collection interval in seconds (value <=0 deactivates gargabe collection)
&zwnj;      | garbage\_collection\_age | -1 | time in seconds that has to pass after the creation or last update of a document *without access restriction* in order for it to be considered garbage<br>documents with access restriction are never automatically deleted
firebase | service\_account\_key\_file | `None` | can be set for Google Firebase integration ([details below](#access-tokens))
json-ld | rewrite\_types | `[]` | comma seperated list of [JSON-LD](https://json-ld.org/spec/latest/json-ld/) types for which [@id](https://json-ld.org/spec/latest/json-ld/#node-identifiers) should be set to a dereferencable URL ([details below](#json-ld))
activity\_stream | collection\_endpoint | `None` | path under which an [Activity Stream](https://www.w3.org/TR/activitystreams-core/) Collection should be served (e.g. `as/collection.json` →  `http://ikeepjson.com/as/collection.json`) ([details below](#activity-stream))
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

        ProxyPassMatch "^/JSONkeeper/(.*)" "http://localhost:5000/JSONkeeper/$1"
        ProxyPassReverse "^/JSONkeeper/(.*)" "http://localhost:5000/JSONkeeper/$1"

* restart apache, get and start gunicorn

        $ sudo a2enmod proxy_http
        $ sudo service apache2 reload
        $ source venv/bin/activate
        $ pip install gunicorn
        $ gunicorn --bind localhost:5000 -e SCRIPT_NAME='/JSONkeeper' 'jsonkeeper:create_app()'

#### Alternatives
* [Deployment Options](http://flask.pocoo.org/docs/0.12/deploying/) (be aware that JSONkeeper uses the [Application Factories](http://flask.pocoo.org/docs/0.12/patterns/appfactories/) pattern, some adjustments to the deployment options listed may be necessary)

## Test
* if you make changes to the code, basic testing can be done with

        $ flake8 *.py jsonkeeper/*.py util/*.py
        $ source venv/bin/activate
        $ ./tests.sh

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
    * **NOTE:** client software that self manages access tokens should be written with the possibility of collisions (distinct clients assigning the same token for non identical users) in mind (using UUIDs as tokens would be a way to make collisions unlikely)

#### List of documents for a given token
Accessing `/<api_path>/userdocs` will return a list of all hosted documents with a matching access token. This means

* no access token → no documents (documents posted without access token will not be listed)
* X-Access-Token → all documents created with this token
* X-Firebase-ID-Token → all documents created by this user

## JSON-LD
JSON­keeper can be configured to host JSON-LD documents in a sensible manner.

#### Example:
If the [configuration](#config) contains a section

    [json-ld]
    rewrite_types = http://codh.rois.ac.jp/iiif/curation/1#Curation,
                    http://iiif.io/api/presentation/2#Range

and a [POST](https://github.com/IllDepence/JSONkeeper/blob/master/README.md#create) request is issued with `Content-Type` set to `application/ld+json` *and* the request's content is a valid JSON-LD document whose [expanded](https://json-ld.org/spec/latest/json-ld-api/#expansion-algorithms) `@type` is listed in the configuration, *then* the document's [@id](https://json-ld.org/spec/latest/json-ld/#node-identifiers) is set to the URL where JSON­keeper will serve the document.

Special behaviour is defined for `http://codh.rois.ac.jp/iiif/curation/1#Curation`. `http://iiif.io/api/presentation/2#Range` nodes within the Curation also are assigned a dereferencable `@id`.

## Activity Stream
JSON­keeper can be configured to serve an [Activity Stream](https://www.w3.org/TR/activitystreams-core/) that implements the [IIIF Change Discovery API 0.1](https://iiif.io/api/discovery/0.1/) at [conformance level 2](https://iiif.io/api/discovery/0.1/#level-2-complete-change-list). This means a complete change list for respective JSON-LD documents is generated, allowing other applications to stay in sync with JSON­keeper in an effective manner.

Special behaviour is defined for `http://codh.rois.ac.jp/iiif/curation/1#Curation`, for which additional Reference and Offer Activities are generated.

**NOTE:** For JSON-LD documents that are posted without any access restriction (X-Access-Token or X-Firebase-ID-Token) no Activities will be generated.

#### Unlisted JSON documents
To prevent access restricted JSON documents to appear in the Activity Stream, a header `X-Unlisted` with the value `true` can be provided when creating, but not changed when updating.

To manage a document's `unlisted` setting use `/<api_path>/<json_id>/status`. A GET requests will yield metadata associated with the JSON document. A value update is possible through a PATCH request with a payload in the form of `{"unlisted": <value>}`, where `<value>` can be `true` or `false`.

- - -

## Logo
The JSON­keeper logo uses image content from [十二類絵巻](http://codh.rois.ac.jp/pmjt/book/200015137/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The JSON­keeper logo itself is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier. A high resolution version (3052×2488 px) can be downloaded [here](http://moc.sirtetris.com/jsonkeeper_logo_full.png).

## Support
Sponsored by the National Institute of Informatics.  
Supported by the Center for Open Data in the Humanities, Joint Support-Center for Data Science Research, Research Organization of Information and Systems.
