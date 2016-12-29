from io import BytesIO
import sys
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

 
def lambda_handler(event, context):
    """Main entry point for the lambda function.

    This function builds a request using API Gateway's proxy integration
    event, and invokes the WSGI application with it. The response is then
    formatted according to the proxy integration requirements.
    """
    query_string = None
    if event.get('queryStringParameters') is not None:
        query_string = '&'.join(
            [quote(k) + '=' + quote(v)
             for k, v in event['queryStringParameters'].items()])
    headers = event.get('headers') or {}
    body = event.get('body').encode('utf-8') \
        if event.get('body') is not None else None
    environ = {
        'REQUEST_METHOD': event.get('httpMethod', 'GET'),
        'SCRIPT_NAME': '',
        'PATH_INFO': event.get('path', '/'),
        'QUERY_STRING': query_string,
        'SERVER_NAME': '',
        'SERVER_PORT': 80,
        'HTTP_HOST': '',
        'SERVER_PROTOCOL': 'https',
        'CONTENT_TYPE': headers.get('Content-Type', ''),
        'CONTENT_LENGTH': headers.get('Content-Length',
                                      str(len(body)) if body is not None
                                          else '0'),
        'wsgi.version': '',
        'wsgi.url_scheme': '',
        'wsgi.input': BytesIO(body) if body is not None else None,
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': True,
        'lambda.event': event,
        'lambda.context': context,
    }

    status_headers = [None, None]
    body = []
 
    def write(item):
        body.append(item)
 
    def start_response(status, headers):
        status_headers[:] = [status, headers]
        return write
 
    app_iter = lambda_handler.app(environ, start_response)
    try:
        for item in app_iter:
            body.append(item)
    finally:
        if hasattr(app_iter, 'close'):
            app_iter.close()

    status = status_headers[0].split()
    headers = status_headers[1]
    return {
        'statusCode': int(status[0]),
        'headers': {h[0]: h[1] for h in headers},
        'body': b''.join(body)
    }
