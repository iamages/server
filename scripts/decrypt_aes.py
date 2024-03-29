from passlib.hash import argon2
from Crypto.Cipher import AES
from sys import argv
from base64 import b64decode

print(argv)
print("")

hasher = argon2.using(
    salt=b64decode(argv[3]),
    hash_len=16,
    time_cost=3,
    memory_cost=65536,
    parallelism=4
)
key = hasher.hash(argv[2]).split("$")
cipher = AES.new(b64decode(key[-1] + "=="), AES.MODE_GCM, nonce=b64decode(argv[4]))

with open(argv[1], "rb") as blob, open(argv[3], "wb") as out:
    blob_data = blob.read()
    out.write(cipher.decrypt_and_verify(blob_data, b64decode(argv[5])))
