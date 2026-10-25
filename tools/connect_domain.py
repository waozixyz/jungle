"""Connect only Jungle's approved hostname after a successful Pages upload."""
import json
import os
import urllib.error
import urllib.request

ACCOUNT = '244fef03abd1e471baed2ec35c59e9e7'
ZONE = '8f056fe0a1b9e4b7ad4893d7638a320a'
HOST = 'jungle.waozi.xyz'
TARGET = 'jungle-f4r.pages.dev'


def api(method, path, value=None):
    request = urllib.request.Request('https://api.cloudflare.com/client/v4' + path,
        data=None if value is None else json.dumps(value).encode(), method=method,
        headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        result = json.load(error)
    if not result.get('success'):
        raise SystemExit('Cloudflare rejected ' + method + ' ' + path + ': ' + json.dumps(result.get('errors')))
    return result['result']


def main():
    project = f'/accounts/{ACCOUNT}/pages/projects/jungle'
    domains = api('GET', project + '/domains')
    if not any(row['name'] == HOST for row in domains):
        api('POST', project + '/domains', {'name': HOST})
    path = f'/zones/{ZONE}/dns_records'
    records = api('GET', path + '?name=' + HOST)
    if records:
        if len(records) != 1 or records[0]['type'] != 'CNAME' or records[0]['content'] != TARGET:
            raise SystemExit('Existing DNS differs from the approved Jungle target; left unchanged')
    else:
        api('POST', path, {'name': HOST, 'type': 'CNAME', 'content': TARGET, 'proxied': True, 'ttl': 1})
    domain = api('GET', project + '/domains/' + HOST)
    print(HOST + ': ' + domain['status'])


if __name__ == '__main__':
    main()
