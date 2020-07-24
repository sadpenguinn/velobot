#!/usr/bin/env python3

# Prepare environment for run application
import os
import errno
import argparse
import shutil
from enum import IntEnum

import sensitive


DOCKER_COMPOSE_DATABASE_PROD = 'database'
DOCKER_COMPOSE_DATABASE_TEST = 'database_test'
DOCKER_COMPOSE_DATABASE_INTEGRATION = 'database_integration'
DOCKER_COMPOSE_BOTNAME_PROD = 'velobot'
DOCKER_COMPOSE_BOTNAME_TEST = 'velobot_test'
DOCKER_COMPOSE_BOTNAME_INTEGRATION = 'velobot_integration'
DOCKER_COMPOSE_PATH = 'docker-compose.yml'
DOCKER_COMPOSE = '''version: '3'
services:
  {1}:
    image: postgres
    container_name: {1}
    environment:
      - node.name={1}
      - cluster.name={0}-cluster
      - cluster.initial_master_nodes={0},{1}
      - bootstrap.memory_lock=true
    networks:
      - fullstack
    env_file:
      - postgres.env
    volumes:
      - datastore:/var/lib/postgresql/data/
  {0}:
    image: {0}
    container_name: {0}
    environment:
      - node.name={0}
      - cluster.name={0}-cluster
      - cluster.initial_master_nodes={0},{1}
      - bootstrap.memory_lock=true
    networks:
      - fullstack
    depends_on:
      - {1}
volumes:
  datastore:
    driver: local
networks:
  fullstack:
    driver: bridge
'''

POSTGRES_ENV_PATH = 'postgres.env'
POSTGRES_ENV = '''POSTGRES_USER={0}
POSTGRES_PASSWD={1}
POSTGRES_DB=velobot
POSTGRES_HOST_AUTH_METHOD=trust
'''

DOCKER_PATH = 'bot/Dockerfile'
DOCKER = '''FROM python:3.7
ADD bot.py /
ADD constants.py /
ADD sensitive.py /
ADD requirements.txt /
RUN pip install -r /requirements.txt
CMD [ "python3.7", "/bot.py" ]
'''

DOCKER_FAKEAPI_PATH = 'fakeveloapi/Dockerfile'
DOCKER_FAKEAPI = '''FROM python:3.7
ADD FakeVeloApi.py /
CMD [ "python3.7", "/FakeVeloApi.py" ]
'''

CONSTANTS_PATH = 'constants.py'
CONSTANTS_POSTGRES_TABLE_PROD = 'user_point_links'
CONSTANTS_POSTGRES_TABLE_TEST = 'user_point_links_test'
CONSTANTS_POSTGRES_TABLE_INTEGRATION = 'user_point_links_integration'
CONSTANTS_POSTGRES_REINSTALL_PROD = False
CONSTANTS_POSTGRES_REINSTALL_TEST = False
CONSTANTS_POSTGRES_REINSTALL_INTEGRATION = True
CONSTANTS_VELOBIKE_URL_PROD = 'https://velobike.ru/ajax/parkings/'
CONSTANTS_VELOBIKE_URL_TEST = 'https://velobike.ru/ajax/parkings/'
CONSTANTS_VELOBIKE_URL_INTEGRATION = 'localhost:9797'
CONSTANTS_VELOBIKE_TIMEOUT_PROD = 60 * 5
CONSTANTS_VELOBIKE_TIMEOUT_TEST = 60 * 5
CONSTANTS_VELOBIKE_TIMEOUT_INTEGRATION = 10 * 1
CONSTANTS = '''POSTGRES_DB = 'velobot'
POSTGRES_HOST = '{3}'
POSTGRES_TABLE = '{0}'
POSTGRES_PREINSTALL = {1}
VELOBIKE_URL = '{4}'
VELOBIKE_TIMEOUT = {2}
TOKEN = '{5}'
NAME = '{6}'
'''


class Environment(IntEnum):
    PROD = 1,
    TEST = 2,
    INTEGRATION = 3


def trace(*args):
    print(*args, flush=True)


def force_remove(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise OSError(e)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--env', type=str.lower, choices=['prod', 'test', 'integration'], default='test')
    parser.add_argument('-c', '--clear', action='store_true')
    args = parser.parse_args()
    assert args.env

    def str_to_env(s):
        return {
            'prod': Environment.PROD,
            'test': Environment.TEST,
            'integration': Environment.INTEGRATION
        }[s]
    args.env = str_to_env(args.env)
    return args


def prepare_docker(args):
    trace('Prepare docker files')
    force_remove(DOCKER_PATH)
    os.mkdir(DOCKER_PATH.split('/')[0])
    with open(DOCKER_PATH, 'tx') as file:
        file.write(DOCKER)
    trace('Prepare docker files is finished')

    def prepare(env):
        return {
            Environment.PROD: DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_PROD, DOCKER_COMPOSE_DATABASE_PROD),
            Environment.TEST: DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_TEST, DOCKER_COMPOSE_DATABASE_TEST),
            Environment.INTEGRATION: DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_INTEGRATION, DOCKER_COMPOSE_DATABASE_INTEGRATION),
        }[env]
    trace('Prepare docker-compose file')
    force_remove(DOCKER_COMPOSE_PATH)
    with open(DOCKER_COMPOSE_PATH, 'tx') as file:
        file.write(prepare(args.env))
        trace('Prepare docker-compose file is finished')

    trace('Prepare postgres env file')
    force_remove(POSTGRES_ENV_PATH)
    with open(POSTGRES_ENV_PATH, 'tx') as file:
        postgres_env = POSTGRES_ENV.format(sensitive.POSTGRES_USER, sensitive.POSTGRES_PASSWD)
        file.write(postgres_env)
        trace('Prepare postgres env file is finished')


def prepare_constants(args):
    def prepare(env):
        return {
            Environment.PROD: CONSTANTS.format(CONSTANTS_POSTGRES_TABLE_PROD,
                                               CONSTANTS_POSTGRES_REINSTALL_PROD,
                                               CONSTANTS_VELOBIKE_TIMEOUT_PROD,
                                               DOCKER_COMPOSE_DATABASE_PROD,
                                               CONSTANTS_VELOBIKE_URL_PROD,
                                               sensitive.BOT_TOKEN_PROD,
                                               sensitive.BOT_NAME_PROD),
            Environment.TEST: CONSTANTS.format(CONSTANTS_POSTGRES_TABLE_TEST,
                                               CONSTANTS_POSTGRES_REINSTALL_TEST,
                                               CONSTANTS_VELOBIKE_TIMEOUT_TEST,
                                               DOCKER_COMPOSE_DATABASE_TEST,
                                               CONSTANTS_VELOBIKE_URL_TEST,
                                               sensitive.BOT_TOKEN_TEST,
                                               sensitive.BOT_NAME_TEST),
            Environment.INTEGRATION: CONSTANTS.format(CONSTANTS_POSTGRES_TABLE_INTEGRATION,
                                                      CONSTANTS_POSTGRES_REINSTALL_INTEGRATION,
                                                      CONSTANTS_VELOBIKE_TIMEOUT_INTEGRATION,
                                                      DOCKER_COMPOSE_DATABASE_INTEGRATION,
                                                      CONSTANTS_VELOBIKE_URL_INTEGRATION,
                                                      sensitive.BOT_TOKEN_INTEGRATION,
                                                      sensitive.BOT_NAME_INTEGRATION),
        }[env]
    trace('Prepare constants file')
    force_remove(CONSTANTS_PATH)
    with open(CONSTANTS_PATH, 'tx') as file:
        file.write(prepare(args.env))
        trace('Prepare constants file is finished')


def clear():
    trace('Removing docker files')
    shutil.rmtree(DOCKER_PATH.split('/')[0])
    shutil.rmtree(DOCKER_FAKEAPI_PATH.split('/')[0])
    trace('Removing docker-compose file')
    force_remove(DOCKER_COMPOSE_PATH)
    trace('Removing postgres env file')
    force_remove(POSTGRES_ENV_PATH)
    trace('Removing constants file')
    force_remove(CONSTANTS_PATH)


def start():
    args = parse_args()
    if args.clear is True:
        clear()
        return
    prepare_docker(args)
    prepare_constants(args)


if __name__ == "__main__":
    start()
