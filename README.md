![JSONkeeper](logo_500px.png)

A minimal flask web application made for API access to store and retrieve JSON documents.

## Setup
* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## Configure
* edit `config.ini`
* mandatory
    * `db_uri` is a [SQLAlchemy database URI](http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls)
    * `server_url` is supposed to be set to the URL that is used to access your JSONkeeper instance (e.g. `http://ikeepjson.com` or `http://sirtetris.com/jsonkeeper`)
    * `api_path` specifies the endpoint for API access (e.g. `api` → <pre>http://ikeepjson.com/<b>api</b></pre> or <pre>http://sirtetris.com/jsonkeeper/<b>api</b></pre>)
* optional
    * `storage_folder` can be set so that JSON documents are not stored in the database but as files in a folder
    * `service_account_key_file` can be set for Google Firebase integration ([details below](#restrict-access-to-put-and-delete))

## Serve
### Development
    $ source venv/bin/activate
    $ FLASK_APP=jsonkeeper.py FLASK_DEBUG=1 python -m flask run

### Deploy
#### Apache2 + gunicorn example
* configure server URL in `config.ini`:

        server_url = http://127.0.0.1/JSONkeeper

* add proxy rules to apache (e.g. in `/etc/apache2/sites-enabled/000-default.conf` within the `<VirtualHost *:80>` block):

        ProxyPassMatch "^/JSONkeeper/(.*)" "http://127.0.0.1:8000/JSONkeeper/$1"
        ProxyPassReverse "^/JSONkeeper/(.*)" "http://127.0.0.1:8000/JSONkeeper/$1"

* restart apache, get and start gunicorn

        $ sudo a2enmod proxy_http
        $ sudo service apache2 reload
        $ source venv/bin/activate
        $ pip install gunicorn
        $ gunicorn --bind 127.0.0.1:8000 -e SCRIPT_NAME='/JSONkeeper' jsonkeeper:app

#### Alternatives
* [Deployment Options](http://flask.pocoo.org/docs/0.12/deploying/)

## Test
* if you make changes to the code, basic testing can be done with

        $ flake8 *.py
        $ source venv/bin/activate
        $ python jsonkeeper_test.py

## Usage examples
### Create
    $ curl -X POST \
           -d '{"foo":"bar"}' \
           -H 'Accept: application/json' \
           -H 'Content-Type: application/json' \
           http://127.0.0.1/JSONkeeper/api
### Retrieve
    $ curl -X GET \
           -H 'Accept: application/json' \
           http://127.0.0.1/JSONkeeper/api/<id>
### Update
    $ curl -X PUT \
           -d '{"bar":"baz"}' \
           -H 'Accept: application/json' \
           -H 'Content-Type: application/json' \
           http://127.0.0.1/JSONkeeper/api/<id>
### Delete
    $ curl -X DELETE  \
           http://127.0.0.1/JSONkeeper/api/<id>

### Restrict access to PUT and DELETE
* **Firebase** (if the [configuration](Configure) points to a valid [Firebase service account key file](https://firebase.google.com/docs/admin/setup#add_firebase_to_your_app))
    * provide a header `X-Firebase-ID-Token` when creating a JSON document
    * the document will only be created if the ID token can be verified, otherwise a `403 FORBIDDEN` is returned; if the document is created, the application stores the authenticated user's UID
    * subsequent `PUT` and `DELETE` requests are only executed when a `X-Firebase-ID-Token` header is provided that, when decoded, results in the same UID, otherwise a `403 FORBIDDEN` is returned
* **Self managed**
    * provide a header `X-Access-Token` when creating a JSON document
    * subsequent `PUT` and `DELETE` requests are only executed when a `X-Access-Token` header with the same value is provided, otherwise a `403 FORBIDDEN` is returned

### jQuery example
    $.ajax({
        url: 'http://127.0.0.1/JSONkeeper/api',
        type: 'post',
        data: '{"foo":"bar"}',
        headers: {
            'Accept': 'application/json',
            'Content-Type':'application/json'
            },
        dataType: 'json',
        success: function (data, status, xhr) {
            console.info(xhr.getResponseHeader('Location'));
            }
        });

## Logo
The JSONkeeper logo uses image content from [十二類絵巻](http://codh.rois.ac.jp/pmjt/book/200015137/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The JSONkeeper logo itself is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier.

## Support
Sponsored by the National Institute of Informatics.  
Supported by the Center for Open Data in the Humanities, Joint Support-Center for Data Science Research, Research Organization of Information and Systems.
