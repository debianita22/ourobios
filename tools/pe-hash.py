#!/usr/bin/env python3
# pe-hash.py - the Authenticode SHA-256 of a PE image (what Secure Boot puts
# in db and dbx as an EFI_CERT_SHA256 entry, and what the firmware computes
# of a boot loader to look it up): the file without the checksum field, the
# security data directory entry and the certificate table.
#
#   python3 tools/pe-hash.py IMAGE.efi        the hash in hex on stdout
#   python3 tools/pe-hash.py --raw IMAGE.efi  the 32 bytes on stdout
#
# When the image carries a signature, the digest in its
# SpcIndirectDataContent must be the same: a different one is an error, so
# a wrong parse here cannot go unnoticed. Only the standard library.
import struct
import sys
import hashlib
import re


def authenticode_sha256(data):
    e_lfanew = struct.unpack_from("<I", data, 0x3c)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise ValueError("not a PE image")
    coff = e_lfanew + 4
    sections, opt_size = struct.unpack_from("<H", data, coff + 2)[0], struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20b:      # PE32+
        dirs = opt + 112
    elif magic == 0x10b:    # PE32
        dirs = opt + 96
    else:
        raise ValueError("unknown optional header magic 0x%x" % magic)
    checksum = opt + 64
    security = dirs + 4 * 8
    cert_off, cert_size = struct.unpack_from("<II", data, security)
    headers_size = struct.unpack_from("<I", data, opt + 60)[0]
    h = hashlib.sha256()
    h.update(data[:checksum])
    h.update(data[checksum + 4:security])
    h.update(data[security + 8:headers_size])
    done = headers_size
    table = opt + opt_size
    secs = []
    for i in range(sections):
        size, ptr = struct.unpack_from("<II", data, table + 40 * i + 16)
        if size:
            secs.append((ptr, size))
    for ptr, size in sorted(secs):
        h.update(data[ptr:ptr + size])
        done += size
    if len(data) > done:
        extra = len(data) - done - (cert_size if cert_off else 0)
        if extra > 0:
            h.update(data[done:done + extra])
    return h.digest(), (data[cert_off + 8:cert_off + cert_size] if cert_off else None)


def signed_digest(pkcs7):
    """The SHA-256 digest in the SpcIndirectDataContent of the signature:
    the 32 byte OCTET STRING that follows the sha256 OID in the DER."""
    m = re.search(b"\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20(.{32})", pkcs7, re.S)
    return m.group(1) if m else None


def main():
    raw = "--raw" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--raw"]
    if len(args) != 1:
        sys.exit(__doc__ or "usage: pe-hash.py [--raw] IMAGE.efi")
    data = open(args[0], "rb").read()
    digest, pkcs7 = authenticode_sha256(data)
    if pkcs7 is not None:
        signed = signed_digest(pkcs7)
        if signed is not None and signed != digest:
            sys.exit("%s: the digest in the signature is %s, computed %s" % (args[0], signed.hex(), digest.hex()))
    if raw:
        sys.stdout.buffer.write(digest)
    else:
        print(digest.hex())


if __name__ == "__main__":
    main()
