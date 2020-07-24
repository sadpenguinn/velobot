<<<<<<< HEAD
import subprocess
import sys
import time

import pytest
import asyncio
import http.server
import json
import socketserver
from threading import Thread
from typing import Optional, Tuple, Union

from pyrogram import Client

import sensitive
import constants


# Описание тестов
# 1. Добавление точки, получение по ней несколько раз через промежутки времени стистики
# 2. Добавление нескольких точек, получение статистики
# 3. Удаление точек

Content = 'null'
BotId = None
FakeClient = None


class MockedHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = f'<html><head></head><body>{Content}</body></html>'
        self.wfile.write(bytes(html, 'utf8'))


class ApiMock:
    @staticmethod
    def create_response(items):
        return {
            "Items": items
        }

    @staticmethod
    def create_response_item(point_id, point, total_ordinary, avail_ordinary, total_electric, avail_electric, address):
        assert total_ordinary >= avail_ordinary
        assert total_electric >= avail_electric
        return {
            "Position": {
                "Lat": point[0],
                "Lon": point[1]
            },
            "TotalOrdinaryPlaces": total_ordinary,
            "AvailableOrdinaryBikes": avail_ordinary,
            "FreeOrdinaryPlaces": total_ordinary - avail_ordinary,
            "TotalElectricPlaces": total_electric,
            "AvailableElectricBikes": avail_electric,
            "FreeElectricPlaces": total_electric - avail_electric,
            "HasTerminal": False,
            "Id": point_id,
            "IsLocked": False,
            "Address": address,
            "StationTypes": [
                "ordinary",
                "electric"
            ],
            "FreePlaces": (total_ordinary - avail_ordinary) + (total_electric - avail_electric),
            "TotalPlaces": total_ordinary + total_electric,
            "IconsSet": 1,
            "Name": "",
            "TemplateId": 6,
            "IsFavourite": False
        }

    @staticmethod
    def set_response(response):
        global Content
        Content = response

    @staticmethod
    def run():
        with socketserver.TCPServer(("", 9797), MockedHandler) as httpd:
            httpd.serve_forever()

    # TODO add check true api no changes


# def start():
#     item = ApiMock.create_response_item("0001", (6.3245345346, 7.3453464), 10, 5, 2, 1, "Улица Пушкина дом Калатушкина")
#     response = ApiMock.create_response([item])
#     ApiMock.set_response(json.dumps(response))
#
#     api_thread = Thread(target=ApiMock.run)
#     api_thread.start()
#     # api_thread.join()
#
#     Client.start()
#     # for dialog in Client.iter_dialogs():
#     #     print(dialog.name, 'has ID', dialog.id)
#     # Client.send_message(1387002151, 'Шампунь жумайсынба скажи печени кУРБЫК КУРДЫКцфп')


def trace(*args):
    print(*args, flush=True)


def set_bot_id():
    global BotId
    global FakeClient
    assert FakeClient is not None
    for dialog in FakeClient.iter_dialogs():
        if dialog.chat.username == 'integration_velooobot':
            BotId = dialog.chat.id
    assert BotId is not None
    trace('BotId is:', BotId)


@pytest.fixture(scope='module')
def setup_module():
    trace('Setup module')
    global FakeClient
    FakeClient = Client('FakeSession', sensitive.API_ID, sensitive.API_HASH)
    FakeClient.start()
    set_bot_id()
    api_thread = Thread(target=ApiMock.run)
    api_thread.Daemon = True
    api_thread.start()
    yield setup_module
    trace('Destruct module')


@pytest.fixture(scope='function')
def setup_test():
    trace('Setup test')
    ret = subprocess.run(['docker-compose', 'up', '-d'])
    assert ret.returncode == 0
    yield setup_test
    trace('Destruct test')
    ret = subprocess.run(['docker-compose', 'down'])
    assert ret.returncode == 0


def test_add_single_point(setup_module, setup_test):
    trace(test_add_single_point.__name__)

    item = ApiMock.create_response_item("0001", (6.11111, 7.11111), 10, 5, 2, 1, "Улица Пушкина дом Калатушкина")
    response = ApiMock.create_response([item])
    ApiMock.set_response(json.dumps(response))

    trace('Sleep start')
    time.sleep(10 * 3)
    trace('Sleep end')

    global FakeClient
    global BotId
    FakeClient.send_location(BotId, 6.11112, 7.11112)
=======
from telethon import TelegramClient, events, sync

import sensitive


Client = TelegramClient('FakeSession', sensitive.API_ID, sensitive.API_HASH)


def start():
    Client.start()
    # for dialog in Client.iter_dialogs():
    #     print(dialog.name, 'has ID', dialog.id)
    Client.send_message(-1001416229183, 'Шампунь жумайсынба скажи печени кУРБЫК КУРДЫКцфп')


if __name__ == "__main__":
    start()
>>>>>>> 352ced50185f008da7570300b1d4f6b389f09334
