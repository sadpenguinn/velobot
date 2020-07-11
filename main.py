import sys
import logging
import json
import time
import urllib.request
from threading import Thread, Lock

import telebot
import psycopg2
from haversine import haversine, Unit

import constants

Logger = logging.getLogger()
Bot = telebot.TeleBot(constants.TOKEN)
Database = psycopg2.connect(dbname=constants.POSTGRES_DB,
                            user=constants.POSTGRES_USER,
                            password=constants.POSTGRES_PASSWD,
                            host=constants.POSTGRES_HOST)


# Points Cache
# 568349: {
#  "location": "",
#  "address": "",
#  "total_ordinary": "",
#  "available_ordinary": "",
#  "total_electric": "",
#  "available_electric": ""
# }
# Users Cache
# 596048: {
#   "points": [
#     568349,
#     568352,
#   ]
# }
PointsCache = {}
UsersCache = {}
CacheLock = Lock()


class BotThread(Thread):
    def run(self):
        Logger.debug(BotThread.__name__ + ': Start')
        Bot.polling()


class ScraperThread(Thread):
    def run(self):
        Logger.debug(ScraperThread.__name__ + ': Start')
        while True:
            with urllib.request.urlopen(constants.VELOBIKE_URL) as url:
                Logger.debug(ScraperThread.__name__ + ': Fetching...')
                CacheLock.acquire()
                data = json.loads(url.read().decode())
                for item in data['Items']:
                    PointsCache[item['Id']] = dict(
                        location=(item['Position']['Lat'], item['Position']['Lon']),
                        address=item['Address'],
                        total_ordinary=item['TotalOrdinaryPlaces'],
                        available_ordinary=item['AvailableOrdinaryBikes'],
                        total_electric=item['TotalElectricPlaces'],
                        available_electric=item['AvailableElectricBikes'])
                CacheLock.release()
                assert len(PointsCache) > 0
                Logger.debug(ScraperThread.__name__ + ': Fetched')
            time.sleep(constants.VELOBIKE_TIMEOUT)


def preinstall_logger(logging_level):
    global Logger
    Logger = logging.getLogger("velobot")
    Logger.setLevel(logging_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging_level)
    Logger.addHandler(handler)


def preinstall_database(force):
    if force:
        global Database
        cursor = Database.cursor()
        cursor.execute('DROP TABLE IF EXISTS users;')
        cursor.execute('CREATE TABLE IF NOT EXISTS users ('
                       'chat_id INTEGER NOT NULL,'
                       'point_id VARCHAR NOT NULL,'
                       'PRIMARY KEY (chat_id, point_id)'
                       ');')
        try:
            Database.commit()
            cursor.close()
        except psycopg2.DatabaseError as error:
            print(error)

    cursor = Database.cursor()
    cursor.execute('SELECT * FROM users')
    records = cursor.fetchall()
    for record in records:
        if record[0] in UsersCache:
            UsersCache[record[0]].append(record[1])
        else:
            UsersCache[record[0]] = [record[1]]
    Logger.debug("YE")
    Logger.debug(records)
    Logger.debug(UsersCache)
    cursor.close()


def bind_handlers():
    @Bot.message_handler(commands=['start'])
    def handle_start(message):
        Logger.debug(handle_start.__name__)

        Bot.send_message(message.chat.id, "Привет! Я бот для уведомлений о загруженности велостоянок. Просто отправь "
                                          "мне ближайшую к требуемой велопарковке локацию и я сама буду уведомлять "
                                          "тебя, когда там будет появляться нужное количество велосипедов :)")

    @Bot.message_handler(commands=['status'])
    def handle_status(message):
        Logger.debug(handle_status.__name__)
        CacheLock.acquire()
        try:
            if message.chat.id not in UsersCache:
                Logger.debug("There are no points")
                CacheLock.release()
                return
            Logger.debug(UsersCache[message.chat.id])
            for point_id in UsersCache[message.chat.id]:
                Logger.debug(UsersCache[message.chat.id])
                Logger.debug(point_id)
                point = PointsCache[point_id]
                Logger.debug(point)
                Bot.send_message(message.chat.id, "Адрес: %s\nСвободно велосипедов: %s\nВсего портов: %s"
                                                  % (point["address"],
                                                     point["available_ordinary"],
                                                     point["total_ordinary"]))
                Bot.send_location(message.chat.id, point["location"][0], point["location"][1])
        except KeyError:
            Bot.send_message(message.chat.id, "Упс! У вас еще нет сохраненных точек проката")
        CacheLock.release()

    @Bot.message_handler(content_types=['location'])
    def handle_new_location(message):
        Logger.debug(handle_new_location.__name__)

        CacheLock.acquire()
        user_point = (message.location.latitude, message.location.longitude)
        min_distance = False
        min_bike = -1
        for key in PointsCache.keys():
            item = PointsCache[key]
            distance = haversine(item['location'], user_point, Unit.METERS)
            if min_distance is False or min_distance > distance:
                min_distance = distance
                min_bike = key
        if message.chat.id in UsersCache:
            if min_bike in UsersCache[message.chat.id]:
                Logger.debug(PointsCache)
                Logger.debug("This location alreay exists")
                Bot.send_message(message.chat.id, "Ой. Кажется, вы уже подписаны на ближайщую точку проката")
                CacheLock.release()
                return
            UsersCache[message.chat.id].append(min_bike)
        else:
            UsersCache[message.chat.id] = [min_bike]
        CacheLock.release()

        cursor = Database.cursor()
        cursor.execute('INSERT INTO users VALUES (%s, %s);',
                       (str(message.chat.id),
                        str(min_bike)))
        try:
            Database.commit()
            cursor.close()
        except psycopg2.DatabaseError as error:
            print(error)


def start():
    preinstall_logger(logging.DEBUG)
    preinstall_database(False)
    bind_handlers()

    scrapper_thread = ScraperThread()
    bot_thread = BotThread()
    scrapper_thread.start()
    bot_thread.start()
    scrapper_thread.join()
    bot_thread.join()


if __name__ == "__main__":
    start()
