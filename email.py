#!/usr/bin/env python3
from pyrage import decrypt, x25519  # 'age' password encryption

with open("creds/email.key", "r") as f:
    key = f.readlines()[-1].strip()
    ident = x25519.Identity.from_str(key)
with open("creds/email.age", "rb") as f:
    msg = decrypt(f.read(), [ident]).decode()
    (addr, pswd) = msg.split("\t")

# TODO: SMTP send
print(f"email:'{addr}' pass:'{pswd}'")
