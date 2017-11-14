## setup
* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## serve
### development
    $ source venv/bin/activate
    $ FLASK_APP=json_store.py FLASK_DEBUG=1 python -m flask run

### deploy
#### *local* apache2 + gunicorn example
    $ source venv/bin/activate
    $ pip install gunicorn
    $ gunicorn --bind 0.0.0.0:8000 json_store:app
    $ sudo a2enmod proxy_http

* add subdomain to /etc/hosts:

        127.0.0.1   json.localhost

* add VirtualHost to Apache (e.g. `/etc/apache2/sites-enabled/000-default.conf`):

        <VirtualHost *:80>
            ServerName json.localhost
            <Proxy *>
                Order deny,allow
                Allow from all
            </Proxy>
            ProxyPreserveHost On
            ProxyPass / "http://127.0.0.1:8000/"
            ProxyPassReverse / "http://127.0.0.1:8000/"
        </VirtualHost>

* configure server URL in `config.ini`:

        server_url = json.localhost

#### alternatives
* [Deployment Options](http://flask.pocoo.org/docs/0.12/deploying/)

## test
    $ flake8 *.py
    $ source venv/bin/activate
    $ python json_store_test.py

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
