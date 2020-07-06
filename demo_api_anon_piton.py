import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import json
import urllib.parse
from queue import SimpleQueue
from cgi import parse_header, parse_multipart
from io import BytesIO
# To get this import, launch command line: pip3 install requests
import requests

# These are the settings of our services
api_addr = 'http://apiserp.com:88'
api_parse = f'{api_addr}/parse'
api_download = f'{api_addr}/download'

# These are the settings of your services
# TODO: put your actual settings into these variables
my_api_key = 'Put your API key here'
my_host = 'Put your domain or IP address here'
my_port = 8003 # Put your actual port here
my_callback_path = '/do-callback/' # Put your actual callback path here
my_callback_addr = f'http://{my_host}:{my_port}'
my_callback_url = f'{my_callback_addr}{my_callback_path}' # Check that this URL is what you actually serve
my_blocks_dir = 'Blocks'


# The normal variables of the program follow
ready_blocks = SimpleQueue()


class CallbackRequestHandler(BaseHTTPRequestHandler):
    def parse_POST(self):
        ctype, pdict = parse_header(self.headers['content-type'])
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = urllib.parse.parse_qs(
                bytes.decode(self.rfile.read(length)),
                keep_blank_values=1)
        else:
            postvars = {}
        return postvars

    def write_response(self, message: str):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        response = BytesIO()
        response.write(message.encode('ASCII'))
        self.wfile.write(response.getvalue())

    def do_POST(self):
        postvars = self.parse_POST()
        bt_list = postvars.get('BlockToken')
        if bt_list is None:
            print('Got a request without a block token in it.')
            self.write_response('ERROR: no block token')
            return
        if len(bt_list) == 0:
            print('Got an empty block token.')
            self.write_response('ERROR: empty block token')
            return
        block_token = bt_list[0]
        self.write_response('OK')
        print('Delivered block: ', block_token)
        ready_blocks.put(block_token)


def serve_async(httpd: HTTPServer):
    httpd.serve_forever()


g_httpd = HTTPServer(('0.0.0.0', my_port), CallbackRequestHandler)
thr_httpd = Thread(target=serve_async, args=(g_httpd,))
thr_httpd.start()

# Compose a request
pages = []

page0 = {'Src': 'https://www.google.com/search?q=game+recommendation',
         'FileName': 'game_recommendation.html',
         'UserAgent': 'Mozilla',
         'Cookies': 'test0=a; test1=b;',
         'Locale': 'en-GB'}
pages.append(page0)

page1 = {'Src': 'https://www.google.com/search?q=game+suggester',
         'FileName': 'game_suggester.html',
         'UserAgent': 'Chrome',
         'Cookies': 'testA=0; testB=1',
         'Locale': 'fr-CH'}
pages.append(page1)

obj_request = {'ApiKey': my_api_key, 'CallbackUrl': my_callback_url, 'Pages': pages}

parser_response = requests.post(api_parse, json=obj_request)
if parser_response.status_code != 200:
    raise Exception('Unexpected status code received from the parser: ' + parser_response.status_code)
obj_response = json.loads(parser_response.content)
g_block_token = obj_response.get('BlockToken')
if g_block_token is None:
    raise Exception(f'Didn\'t receive a block token from the parser, but got: {parser_response.content}')
print(f'Got block token: {g_block_token}')

while True:
    bt_ready = ready_blocks.get()
    if bt_ready == g_block_token:
        break
    print('Unexpected block token:', bt_ready)

download_url = f'{api_download}?BlockToken={urllib.parse.quote(g_block_token)}'
download_resp = requests.get(download_url)
if download_resp.status_code != 200:
    raise Exception('Download status Code is ' + str(download_resp.status_code))
os.makedirs(my_blocks_dir, exist_ok=True)
file_name = f'{my_blocks_dir}/{g_block_token}.zip'
with open(file_name, 'wb') as out_file:
    out_file.write(download_resp.content)
print('Downloaded block: ', file_name)
g_httpd.shutdown()
