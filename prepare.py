#!/usr/bin/env python3

# Prepare environment for run application
import os
import errno
import argparse
from enum import IntEnum

import sensitive


POSTGRES_ENV_PATH = 'postgres.env'
POSTGRES_ENV = '''POSTGRES_USER = '{0}'
POSTGRES_PASSWD = '{1}'
POSTGRES_DB = 'velobot'
'''

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
    args = parser.parse_args()
    assert args.env
    args.env = Environment.PROD if args.env == 'prod' else Environment.TEST
    return args


def prepare_docker(args):
    trace('Prepare docker files')
    force_remove(DOCKER_COMPOSE_PATH)
    with open(DOCKER_COMPOSE_PATH, 'tx') as file:
        docker_compose_out = DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_PROD) \
            if args.env is Environment.PROD \
            else DOCKER_COMPOSE.format(DOCKER_COMPOSE_BOTNAME_TEST)
        file.write(docker_compose_out)
        trace('Prepare docker files is finished')

    trace('Prepare postgres env file')
    force_remove(POSTGRES_ENV_PATH)
    with open(POSTGRES_ENV_PATH, 'tx') as file:
        postgres_env = POSTGRES_ENV.format(sensitive.POSTGRES_USER, sensitive.POSTGRES_PASSWD)
        file.write(postgres_env)
        trace('Prepare postgres env file is finished')



def start():
    args = parse_args()
    prepare_docker(args)


if __name__ == "__main__":
    start()
