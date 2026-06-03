from curl_cffi import requests
from src.core.logger import log_operation

@log_operation()
def create_session(impersonate: str = "safari15_5", timeout: int = 30) -> requests.Session:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }
    session = requests.Session(impersonate=impersonate, headers=headers, timeout=timeout)

    # Advanced TLS/Curve/Sign settings used in dlc_gen (can be applied to any session if needed)
    try:
        session.cipher = ("TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:TLS_RSA_WITH_AES_256_GCM_SHA384:TLS_RSA_WITH_AES_128_GCM_SHA256:TLS_RSA_WITH_AES_256_CBC_SHA:TLS_RSA_WITH_AES_128_CBC_SHA:TLS_ECDHE_ECDSA_WITH_3DES_EDE_CBC_SHA:TLS_ECDHE_RSA_WITH_3DES_EDE_CBC_SHA:TLS_RSA_WITH_3DES_EDE_CBC_SHA")
        session.curve = "X25519:P-256:P-384:P-521"
        session.sign_algo = ("ecdsa_secp256r1_sha256,rsa_pss_rsae_sha256,rsa_pkcs1_sha256,ecdsa_secp384r1_sha384,ecdsa_sha1,rsa_pss_rsae_sha384,rsa_pss_rsae_sha384,rsa_pkcs1_sha384,rsa_pss_rsae_sha512,rsa_pkcs1_sha512,rsa_pkcs1_sha1")
    except Exception:
        pass

    return session

@log_operation()
def download_file(url: str, dest_path: str, session: requests.Session = None) -> bool:
    """Download a file from a URL to a destination path."""
    close_session = False
    if session is None:
        session = create_session()
        close_session = True

    try:
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception:
        pass
    finally:
        if close_session:
            session.close()
    return False
