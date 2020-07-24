import http.server
import socketserver
import json

URL = ''
PORT = 9797

Content = {
    "Items": []
}


class FakeHandler(http.server.CGIHTTPRequestHandler):
    def _log(self, *args):
        print(*args, flush=True)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def _check_input_data(self, data):
        if not isinstance(data, dict):
            return False
        return True

    def do_GET(self):
        converted = json.dumps(Content)
        self._log('do_GET', converted)
        self._set_response()
        html = f'<html><head></head><body>{converted}</body></html>'
        self.wfile.write(bytes(html, 'utf8'))

    def do_POST(self):
        self._log('do_POST')
        length = int(self.headers['Content-Length'])
        data = self.rfile.read(length)
        self._set_response()
        decoded = data.decode('utf-8')
        self._log(decoded)
        parsed = json.loads('{"Items":' + decoded + '}')
        ret = self._check_input_data(parsed)
        if not ret:
            self._log('Invalid data')
            return
        global Content
        Content = parsed


class FakeVeloApi:
    @staticmethod
    def run():
        with socketserver.TCPServer((URL, PORT), FakeHandler) as httpd:
            httpd.serve_forever()


if __name__ == '__main__':
    FakeVeloApi.run()
