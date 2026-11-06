"""
Build a KoboCollect "Configure via QR code" image.

KoboCollect / ODK Collect reads a QR whose payload is
    base64( zlib.compress( settings_json ) )
On scan, the app auto-configures the server, account and project, then the
field worker just pulls the blank forms.

Usage:
  python make_collect_qr.py --username ciprb_field --out ciprb_collect_qr.png
  # optionally bake the password so field staff never type it:
  python make_collect_qr.py --username ciprb_field --password "..." --out qr.png

Password is OPTIONAL. If omitted, the QR still sets the server + username and
the worker enters the password once on first sync. Prefer omitting it unless
the account password is meant to be shared with every field phone.
"""
import argparse
import base64
import json
import zlib

import qrcode


def build_payload(server_url, username, password, project_name, project_icon,
                  project_color):
    general = {'server_url': server_url, 'username': username}
    if password:
        general['password'] = password
    settings = {
        'general': general,
        'admin': {},
        'project': {'name': project_name, 'icon': project_icon,
                    'color': project_color},
    }
    raw = json.dumps(settings, separators=(',', ':')).encode('utf-8')
    return base64.b64encode(zlib.compress(raw)).decode('ascii')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--server', default='https://kf.kobotoolbox.org')
    ap.add_argument('--username', required=True)
    ap.add_argument('--password', default='')
    ap.add_argument('--project-name', default='CIPRB')
    ap.add_argument('--project-icon', default='C')
    ap.add_argument('--project-color', default='#1976d2')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    payload = build_payload(a.server, a.username, a.password, a.project_name,
                            a.project_icon, a.project_color)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    img.save(a.out)
    print('server   :', a.server)
    print('username :', a.username)
    print('password :', 'baked in' if a.password else 'NOT baked (worker enters once)')
    print('payload  :', len(payload), 'chars')
    print('saved    :', a.out)


if __name__ == '__main__':
    main()
