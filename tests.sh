#! /bin/sh

if ping -q -c 1 -W 1 google.com 2>/dev/null; then
    echo -n ""
else
    echo -n "\n[WARN] You don't seem to have internet connectivity. \n       T"
    echo -n "esting JSONkeeper requires resolving JSON-LD contexts.\n\n       "
    echo -n "Continue anyway? (You might get a lot of failures due to HTTP\n  "
    echo -n "     400 responses.)\n\n(y/N)"
    read resp
fi

if [ "$resp" != "y" ]; then
    exit
fi

echo -n "\n[INFO] Testing config with JSON-LD @id rewrite off and Activity Str"
echo "eam\n       serving off. (Expect 4 tests to be skipped.)"
JK_ID_REWRITE=0 JK_AS_SERVE=0 $(which python3) ./test.py
echo -n "\n[INFO] Testing config with JSON-LD @id rewrite on and Activity Stre"
echo "am\n       serving off. (Expect 2 test to be skipped.)"
JK_ID_REWRITE=1 JK_AS_SERVE=0 $(which python3) ./test.py
echo -n "\n[INFO] Testing config with JSON-LD @id rewrite on and Activity Stre"
echo "am\n       serving on. (Expect no test to be skipped.)"
JK_ID_REWRITE=1 JK_AS_SERVE=1 $(which python3) ./test.py
