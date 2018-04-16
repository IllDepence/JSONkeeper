#! /bin/sh

echo -n "\n[INFO] Testing config with JSON-LD @id rewrite off and Activity Str"
echo "eam\n       serving off. (Expect 4 tests to be skipped.)"
JK_ID_REWRITE=0 JK_AS_SERVE=0 $(which python3) ./test.py
echo -n "\n[INFO] Testing config with JSON-LD @id rewrite on and Activity Stre"
echo "am\n       serving off. (Expect 2 test to be skipped.)"
JK_ID_REWRITE=1 JK_AS_SERVE=0 $(which python3) ./test.py
echo -n "\n[INFO] Testing config with JSON-LD @id rewrite on and Activity Stre"
echo "am\n       serving on. (Expect no test to be skipped.)"
JK_ID_REWRITE=1 JK_AS_SERVE=1 $(which python3) ./test.py
