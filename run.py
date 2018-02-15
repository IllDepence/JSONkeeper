import sys
from jsonkeeper import create_app

app = create_app()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        app.run(debug=True)
    else:
        app.run()
