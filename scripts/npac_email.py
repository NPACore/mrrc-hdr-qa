#!/usr/bin/env python3
from pyrage import decrypt, x25519  # 'age' password encryption


def decrypt_creds():
    with open("creds/email.key", "r") as f:
        key = f.readlines()[-1].strip()
        ident = x25519.Identity.from_str(key)
    with open("creds/email.age", "rb") as f:
        msg = decrypt(f.read(), [ident]).decode()
        (addr, pswd) = msg.split("\t")

    print(f"email:'{addr}' pass:'{pswd}'")
    return (addr, pswd)


# TODO: SMTP send
