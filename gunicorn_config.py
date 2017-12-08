# server socket
bind = "localhost:8000"

# create pid file to avoid multiple instances
pidfile = "/tmp/gunicorn.pid"

# set script name to allow deployment in subdirectory
raw_env = "SCRIPT_NAME=/JSONkeeper"

# paths to logging files
accesslog = "/tmp/gunicorn.access.log"
errorlog = "/tmp/gunicorn.error.log"

# number of worker processes
# (positive integer generally in the 2-4 x $(NUM_CORES) range)
workers = 17
