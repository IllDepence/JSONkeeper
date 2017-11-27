![](logo_500px.png)

A minimal flask web application made for API access to store and retrieve JSON documents.

## setup
* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## serve
### development
    $ source venv/bin/activate
    $ FLASK_APP=jsonkeeper.py FLASK_DEBUG=1 python -m flask run

### deploy
#### apache2 + gunicorn example

* configure server URL in `config.ini`:

        server_url = http://localhost/JSONkeeper

* add proxy rules to apache (e.g. in `/etc/apache2/sites-enabled/000-default.conf` within the `<VirtualHost *:80>` block):

        ProxyPreserveHost On
        ProxyPassMatch "^/JSONkeeper/(.*)" "http://127.0.0.1:8000/JSONkeeper/$1"
        ProxyPassReverse "^/JSONkeeper/(.*)" "http://127.0.0.1:8000/JSONkeeper/$1"

* restart apache, get and start gunicorn

        $ sudo a2enmod proxy_http
        $ sudo service apache2 reload
        $ source venv/bin/activate
        $ pip install gunicorn
        $ gunicorn --bind 127.0.0.1:8000 -e SCRIPT_NAME='/JSONkeeper' jsonkeeper:app

#### alternatives
* [Deployment Options](http://flask.pocoo.org/docs/0.12/deploying/)

## test
    $ flake8 *.py
    $ source venv/bin/activate
    $ python jsonkeeper_test.py

## usage examples
### POST
    $ curl -X POST -d '{"foo":"bar"}' -H 'Accept: application/json' -H 'Content-Type: application/json' http://example.com/api
### GET
    $ curl -X GET -H 'Accept: application/json' http://example.com/api/<id>
### PUT
    $ curl -X PUT -d '{"bar":"baz"}' -H 'Accept: application/json' -H 'Content-Type: application/json' http://example.com/api/<id>
### DELETE
    $ curl -X DELETE  http://example.com/api/<id>
### Restrict access to PUT and DELETE
* provide a header `X-Access-Token` when creating a JSON document
* subsequent `PUT` and `DELETE` requests are only executed when a `X-Access-Token` header with the same value is provided, otherwise a `403 FORBIDDEN` is returned
### jQuery example
    $.ajax({
        url: 'http://json.localhost/api',
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

## logo

The JSONkeeper logo uses image content from [十二類絵巻](http://codh.rois.ac.jp/pmjt/book/200015137/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The JSONkeeper logo itself is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier.
