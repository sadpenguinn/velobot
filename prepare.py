#!/usr/bin/env python3

# Prepare environment for run application
import os
import errno
import argparse
from enum import IntEnum

import sensitive


DOCKER_COMPOSE_BOTNAME_PROD = 'velobot'
DOCKER_COMPOSE_BOTNAME_TEST = 'velobot_test'
DOCKER_COMPOSE_PATH = 'docker-compose.yml'
DOCKER_COMPOSE = '''version: '3'
services:
  database:
    image: postgres
    container_name: database
    environment:
      - node.name=database
      - cluster.name={0}-cluster
      - cluster.initial_master_nodes={0},database
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
      - cluster.initial_master_nodes={0},database
      - bootstrap.memory_lock=true
    networks:
      - fullstack
    depends_on:
      - database
volumes:
  datastore:
    driver: local
networks:
  fullstack:
    driver: bridge
'''

POSTGRES_ENV_PATH = 'postgres.env'
POSTGRES_ENV = '''POSTGRES_USER = '{0}'
POSTGRES_PASSWD = '{1}'
POSTGRES_DB = 'velobot'
'''

DOCKER_PATH = 'Dockerfile'
DOCKER = '''FROM python:3.7
ADD main.py /
ADD constants.py /
ADD requirements.txt /
RUN pip install -r /requirements.txt
CMD [ "python3.7", "/main.py" ]
'''

CONSTANTS_PATH = 'constants.py'
CONSTANTS_POSTGRES_TABLE_PROD = 'user_point_links'
CONSTANTS_POSTGRES_TABLE_TEST = 'user_point_links_test'
CONSTANTS_POSTGRES_REINSTALL = False
CONSTANTS_VELOBIKE_TIMEOUT = 60 * 5
CONSTANTS = '''
POSTGRES_DB = 'velobot'
POSTGRES_HOST = 'database'
POSTGRES_TABLE = '{0}'
POSTGRES_PREINSTALL = {1}
VELOBIKE_URL = 'https://velobike.ru/ajax/parkings/'
VELOBIKE_TIMEOUT = {2}
'''


class Environment(IntEnum):
    PROD = 1,
    TEST = 2


def trace(msg):
    print(msg, flush=True)


def force_remove(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise OSError(e)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--env', type=str.lower, choices=['prod', 'test'], default='test')
    parser.add_argument('-c', '--clear', action='store_true')
    args = parser.parse_args()
    assert args.env
    args.env = Environment.PROD if args.env == 'prod' else Environment.TEST
    return args


def prepare_docker(args):
    trace('Prepare docker files')
    force_remove(DOCKER_PATH)
    with open(DOCKER_PATH, 'tx') as file:
        file.write(DOCKER)
        trace('Prepare docker files is finished')

    trace('Prepare docker-compose file')
    force_remove(DOCKER_COMPOSE_PATH)
    with open(DOCKER_COMPOSE_PATH, 'tx') as file:
        docker_compose_out = DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_PROD) \
            if args.env is Environment.PROD \
            else DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_TEST)
        file.write(docker_compose_out)
        trace('Prepare docker-compose file is finished')

    trace('Prepare postgres env file')
    force_remove(POSTGRES_ENV_PATH)
    with open(POSTGRES_ENV_PATH, 'tx') as file:
        postgres_env = POSTGRES_ENV.format(sensitive.POSTGRES_USER, sensitive.POSTGRES_PASSWD)
        file.write(postgres_env)
        trace('Prepare postgres env file is finished')


def prepare_constants(args):
    trace('Prepare constants file')
    force_remove(CONSTANTS_PATH)
    with open(CONSTANTS_PATH, 'tx') as file:
        constants_out = CONSTANTS.format(CONSTANTS_POSTGRES_TABLE_PROD,
                                         CONSTANTS_POSTGRES_REINSTALL,
                                         CONSTANTS_VELOBIKE_TIMEOUT) \
            if args.env is Environment.PROD \
            else CONSTANTS.format(CONSTANTS_POSTGRES_TABLE_TEST,
                                  CONSTANTS_POSTGRES_REINSTALL,
                                  CONSTANTS_VELOBIKE_TIMEOUT)
        file.write(constants_out)
        trace('Prepare constants file is finished')


def clear():
    trace('Removing docker file')
    force_remove(DOCKER_PATH)
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
