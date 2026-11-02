#!/usr/bin/env python3
"""Small, SDK-free Alibaba Cloud DNS client using ACS3-HMAC-SHA256."""

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "alidns.aliyuncs.com"
ACTIONS = {"DescribeDomainRecords", "DescribeDomainRecordInfo", "AddDomainRecord", "UpdateDomainRecord"}


def signed_headers(method, host, action, version, params, key_id, secret, timestamp, nonce):
    query = "&".join(f"{quote(str(k), safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in sorted(params.items()))
    payload_hash = hashlib.sha256(b"").hexdigest()
    headers = {"host": host, "x-acs-action": action, "x-acs-version": version,
               "x-acs-date": timestamp, "x-acs-signature-nonce": nonce,
               "x-acs-content-sha256": payload_hash}
    signed_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in sorted(headers))
    canonical = f"{method}\n/\n{query}\n{canonical_headers}\n{signed_names}\n{payload_hash}"
    to_sign = "ACS3-HMAC-SHA256\n" + hashlib.sha256(canonical.encode()).hexdigest()
    signature = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = f"ACS3-HMAC-SHA256 Credential={key_id},SignedHeaders={signed_names},Signature={signature}"
    headers["Accept"] = "application/json"
    return query, headers


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Authorization and signed headers must never follow an endpoint redirect.
        return None


def request(action, params, key_id, secret, timeout, opener=None):
    if action not in ACTIONS:
        raise ValueError("unsupported DNS operation")
    query, headers = signed_headers("GET", ENDPOINT, action, "2015-01-09", params, key_id, secret,
                                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), uuid.uuid4().hex)
    req = Request("https://" + ENDPOINT + "/?" + query, headers=headers, method="GET")
    opener = opener or build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        try:
            error = json.load(exc)
        except (ValueError, OSError):
            raise RuntimeError(f"Alibaba Cloud DNS HTTP {exc.code}") from None
        # Do not dump the response, signed headers or request URL.
        detail = error.get("AccessDeniedDetail") or {}
        diagnosis = "; ".join(f"{key}={detail[key]}" for key in ("AuthAction", "PolicyType", "NoPermissionType") if key in detail)
        raise RuntimeError(f"Alibaba Cloud DNS HTTP {exc.code}: {error.get('Code', 'unknown')} "
                           f"{error.get('Message', '')}; request_id={error.get('RequestId', 'unknown')}; {diagnosis}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Alibaba Cloud DNS connection failed ({type(exc).__name__})") from None
    if not isinstance(payload, dict) or payload.get("Code"):
        raise RuntimeError("Alibaba Cloud DNS returned an unexpected response")
    return payload


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or args[0] not in ACTIONS or len(args) % 2 != 1:
            raise ValueError("usage: aliyun_api.py <DNS operation> [--Parameter value ...]")
        params = {}
        for key, value in zip(args[1::2], args[2::2]):
            if not key.startswith("--") or key[2:] in params:
                raise ValueError("invalid or duplicate DNS API parameter")
            params[key[2:]] = value
        key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        if not key_id or not secret:
            raise ValueError("missing Alibaba Cloud AccessKey environment variables")
        payload = request(args[0], params, key_id, secret, int(os.environ.get("DDNS_API_TIMEOUT_SECONDS", "30")))
        print(json.dumps(payload))
    except (ValueError, RuntimeError) as exc:
        message = str(exc)
        for name in ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET"):
            value = os.environ.get(name)
            if value:
                message = message.replace(value, "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
