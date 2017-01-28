import climax


@climax.command()
@climax.argument('--no-api-gateway', action='store_true',
                 help=('Do not deploy API Gateway.'))
@climax.argument('--wsgi', action='store_true',
                 help=('Treat the given function as a WSGI app.'))
def init(config, wsgi, no_api_gateway):
    if not wsgi:
        return
    return '', {'deploy_api_gateway': not no_api_gateway,
                'log_stages': [config['devstage']]}

    # def test_outputs(self):
    #     outputs = cfn._get_cfn_outputs(config)
    #     for output in ['FunctionArn', 'DevEndpoint', 'StagingEndpoint',
    #                    'ProdEndpoint']:
    #         self.assertIn('FunctionArn', outputs)


def _get_wsgi_resources(config):
    res = {}
    res['API'] = {
        'Type': 'AWS::ApiGateway::RestApi',
        'Properties': {
            'Body': {
                'swagger': '2.0',
                'info': {
                    'title': config['name'],
                    'description': config.get('description', '')
                },
                'schemes': ['https'],
                'paths': {
                    '/': {
                        'x-amazon-apigateway-any-method': {
                            'responses': {},
                            'x-amazon-apigateway-integration': {
                                'responses': {
                                    'default': {
                                        'statusCode': '200'
                                    }
                                },
                                'uri': {
                                    'Fn::Join': [
                                        '',
                                        [
                                            'arn:aws:apigateway:',
                                            {'Ref': 'AWS::Region'},
                                            (':lambda:path/2015-03-31/'
                                             'functions/'),
                                            {'Fn::GetAtt': ['Function',
                                                            'Arn']},
                                            (':${stageVariables.STAGE}/'
                                             'invocations')
                                        ]
                                    ]
                                },
                                'passthroughBehavior': 'when_no_match',
                                'httpMethod': 'POST',
                                'type': 'aws_proxy'
                            }
                        }
                    },
                    '/{proxy+}': {
                        'x-amazon-apigateway-any-method': {
                            'parameters': [
                                {
                                    'name': 'proxy',
                                    'in': 'path',
                                    'required': True,
                                    'type': 'string'
                                }
                            ],
                            'responses': {},
                            'x-amazon-apigateway-integration': {
                                'responses': {
                                    'default': {
                                        'statusCode': '200'
                                    }
                                },
                                'uri': {
                                    'Fn::Join': [
                                        '',
                                        [
                                            'arn:aws:apigateway:',
                                            {'Ref': 'AWS::Region'},
                                            (':lambda:path/2015-03-31/'
                                             'functions/'),
                                            {'Fn::GetAtt': ['Function',
                                                            'Arn']},
                                            (':${stageVariables.STAGE}/'
                                             'invocations')
                                        ]
                                    ]
                                },
                                'passthroughBehavior': 'when_no_match',
                                'httpMethod': 'POST',
                                'type': 'aws_proxy'
                            }
                        }
                    }
                }
            }
        }
    }
    res['APICloudWatchRole'] = {
        'Type': 'AWS::IAM::Role',
        'Properties': {
            'AssumeRolePolicyDocument': {
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Effect': 'Allow',
                        'Principal': {
                            'Service': ['apigateway.amazonaws.com']
                        },
                        'Action': 'sts:AssumeRole'
                    }
                ]
            },
            'Path': '/',
            'ManagedPolicyArns': ['arn:aws:iam::aws:policy/service-role/'
                                  'AmazonAPIGatewayPushToCloudWatchLogs']
        }
    }
    res['APIAccount'] = {
        'Type': 'AWS::ApiGateway::Account',
        'DependsOn': 'API',
        'Properties': {
            'CloudWatchRoleArn': {
                'Fn::GetAtt': ['APICloudWatchRole', 'Arn']
            }
        }
    }
    for stage in config['stage_environments'].keys():
        log = stage in (config['wsgi'].get('log_stages') or [])
        res[stage.title() + 'APIDeployment'] = {
            'Type': 'AWS::ApiGateway::Deployment',
            'Properties': {
                'RestApiId': {'Ref': 'API'},
                'StageName': stage,
                'StageDescription': {
                    'MethodSettings': [
                        {
                            'ResourcePath': '/*',
                            'HttpMethod': '*',
                            'LoggingLevel': 'INFO' if log else 'ERROR',
                        }
                    ],
                    'Variables': {'STAGE': stage}
                }
            }
        }
        res[stage.title() + 'APILambdaPermission'] = {
            'Type': 'AWS::Lambda::Permission',
            'DependsOn': stage.title() + 'FunctionAlias',
            'Properties': {
                'Action': 'lambda:InvokeFunction',
                'FunctionName': {'Ref': stage.title() + 'FunctionAlias'},
                'Principal': 'apigateway.amazonaws.com',
                'SourceArn': {
                    'Fn::Join': [
                        '',
                        [
                            'arn:aws:execute-api:',
                            {'Ref': 'AWS::Region'},
                            ':',
                            {'Ref': 'AWS::AccountId'},
                            ':',
                            {'Ref': 'API'},
                            '/*/*/*'
                        ]
                    ]
                }
            }
        }
    return res


def _get_wsgi_outputs(config):
    outputs = {'ApiId': {'Value': {'Ref': 'API'}}}
    for stage in config['stage_environments'].keys():
        outputs[stage.title() + 'Endpoint'] = {
            'Value': {
                'Fn::Join': [
                    '',
                    [
                        'https://',
                        {'Ref': 'API'},
                        '.execute-api.',
                        {'Ref': 'AWS::Region'},
                        '.amazonaws.com/' + stage
                    ]
                ]
            }
        }
    return outputs


def cfn_template(config, template):
    if config['wsgi']['deploy_api_gateway']:
        template['Resources'].update(_get_wsgi_resources(config))
        template['Outputs'].update(_get_wsgi_outputs(config))
    return template


def run_lambda_function(event, context, app, config):  # pragma: no cover
    from io import BytesIO
    import sys
    try:
        from urllib import quote
    except ImportError:  # pragma: no cover
        from urllib.parse import quote

    query_string = None
    if event.get('queryStringParameters') is not None:
        query_string = '&'.join(
            [quote(k) + '=' + quote(v)
             for k, v in event['queryStringParameters'].items()])
    headers = event.get('headers') or {}
    body = event.get('body').encode('utf-8') \
        if event.get('body') is not None else b''

    # create a WSGI environment for this request
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
        'CONTENT_LENGTH': headers.get('Content-Length', str(len(body))),
        'wsgi.version': '',
        'wsgi.url_scheme': '',
        'wsgi.input': BytesIO(body),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': True,
        'lambda.event': event,
        'lambda.context': context,
    }

    # add any headers that came with the request
    for h, v in headers.items():
        environ['HTTP_' + h.upper().replace('-', '_')] = v

    status_headers = [None, None]
    body = []

    def write(item):
        body.append(item)

    def start_response(status, headers):
        status_headers[:] = [status, headers]
        return write

    # invoke the WSGI app
    app_iter = app(environ, start_response)
    try:
        for item in app_iter:
            body.append(item)
    finally:
        if hasattr(app_iter, 'close'):
            app_iter.close()

    # format the response as required by the api gateway proxy integration
    status = status_headers[0].split()
    headers = status_headers[1]
    return {
        'statusCode': int(status[0]),
        'headers': {h[0]: h[1] for h in headers},
        'body': b''.join(body)
    }
