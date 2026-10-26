"""Conditional fresh-router package upload; never invokes publishing keys or SAS.
Actual Azure execution requires separately approved identity/container write scope.
"""
from pathlib import Path
import hashlib,re
ACCOUNT='whmcprv2f7076f8e38'
CONTAINER='router-packages'

def publish(client, path, digest):
    if not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('INVALID_DIGEST')
    path=Path(path)
    if not 0 < path.stat().st_size <= 262144000:raise ValueError('PACKAGE_SIZE')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('LOCAL_PACKAGE_HASH_MISMATCH')
    # Existing object is a hard stop. Never overwrite, even for a digest-shaped name.
    client.upload_blob(data,overwrite=False,if_none_match='*')
    downloaded=hashlib.sha256()
    size=0
    for chunk in client.download_blob().chunks():
        size+=len(chunk)
        if size>len(data):raise ValueError('REMOTE_PACKAGE_SIZE_MISMATCH')
        downloaded.update(chunk)
    if size!=len(data) or downloaded.hexdigest()!=digest:raise ValueError('REMOTE_PACKAGE_HASH_MISMATCH')
    return f'https://{ACCOUNT}.blob.core.windows.net/{CONTAINER}/{digest}.zip'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--file',required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobClient
    try:
        with BlobClient(account_url=f'https://{ACCOUNT}.blob.core.windows.net',container_name=CONTAINER,blob_name=a.sha256+'.zip',credential=AzureCliCredential(),connection_timeout=10,read_timeout=60) as client:
            publish(client,a.file,a.sha256)
        print('PASS conditional upload and downloaded package hash verification')
    except Exception:
        raise SystemExit('PACKAGE_UPLOAD_OR_VERIFICATION_FAILED; response details withheld')
