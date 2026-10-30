#!/bin/sh
# A server certificate for the iPhone, from the local mkcert root CA (mkcert -install, its
# root trusted on the phone). Writes .certs/phone.pem and .certs/phone-key.pem, git-ignored,
# for this Mac's LAN address and Bonjour name. Run again when the LAN address changes.
set -eu
cd "$(dirname "$0")/.."
ip=$(ipconfig getifaddr en0 || ipconfig getifaddr en1)
host="$(scutil --get LocalHostName).local"
mkdir -p .certs
mkcert -cert-file .certs/phone.pem -key-file .certs/phone-key.pem "$ip" "$host" localhost 127.0.0.1 ::1
echo "On the iPhone: https://$ip:5173/explore?check=1 (or https://$host:5173/explore?check=1)"
