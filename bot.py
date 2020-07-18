import sys
import logging
import json
import time
import urllib.request
from threading import Thread, Lock

import telebot
import psycopg2
from haversine import haversine, Unit

import sensitive
import constants


Logger = logging.getLogger()
Bot = telebot.TeleBot(sensitive.TOKEN)
Database = psycopg2.connect(dbname=constants.POSTGRES_DB,
                            user=sensitive.POSTGRES_USER,
                            password=sensitive.POSTGRES_PASSWD,
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
# 596048: [
#   568349,
#   568352,
# ]
PointsCache = {}
UsersCache = {}
CacheLock = Lock()


class LoggingUtils:
    @staticmethod
    def log_telegram_message(func_name, message):
        Logger.debug("%s: New message with type %s from %s %s @%s %s" % (func_name,
                                                                         message.content_type,
                                                                         message.from_user.first_name,
                                                                         message.from_user.last_name,
                                                                         message.from_user.username,
                                                                         message.from_user.id))


class VelobotException(Exception):
    def __init__(self, *args):
        self.message = args[0] if args else "null"

    def __str__(self):
        return "VelobotException: %s" % self.message


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
    global Database
    cursor = Database.cursor()
    if force:
        cursor.execute('DROP TABLE IF EXISTS %s;' % constants.POSTGRES_TABLE)
        cursor.execute('CREATE TABLE IF NOT EXISTS %s ('
                       'chat_id INTEGER NOT NULL,'
                       'point_id VARCHAR NOT NULL,'
                       'PRIMARY KEY (chat_id, point_id)'
                       ');' % constants.POSTGRES_TABLE)
    cursor.execute('SELECT * FROM %s' % constants.POSTGRES_TABLE)
    records = cursor.fetchall()
    for record in records:
        if record[0] in UsersCache:
            UsersCache[record[0]].append(record[1])
        else:
            UsersCache[record[0]] = [record[1]]
    try:
        Database.commit()
    except psycopg2.DatabaseError as error:
        Logger.debug("Database error: %s" % error)
    finally:
        cursor.close()
    Logger.debug("UsersCache:", UsersCache)


def bind_handlers():
    @Bot.message_handler(commands=['start'])
    def handle_start(message):
        Logger.debug(handle_start.__name__, message)
        Bot.send_message(message.chat.id, "Привет! Я бот для уведомлений о загруженности велостоянок. Просто отправь "
                                          "мне несколько локаций и смотри загруженность ближайщих к ним стоянок через"
                                          " команду /status")

    @Bot.message_handler(commands=['status'])
    def handle_status(message):
        Logger.debug(handle_status.__name__, message)
        CacheLock.acquire()
        try:
            if message.chat.id not in UsersCache:
                Logger.debug("There are no points")
                raise VelobotException("No points for user")
            for point_id in UsersCache[message.chat.id]:
                point = PointsCache[point_id]
                Bot.send_location(message.chat.id, point["location"][0], point["location"][1])
                Bot.send_message(message.chat.id, "Адрес: %s\nДоступно велосипедов: %s\nВсего портов: %s"
                                 % (point["address"],
                                    point["available_ordinary"],
                                    point["total_ordinary"]))
        except (KeyError, VelobotException):
            Bot.send_message(message.chat.id, "Упс! У вас еще нет сохраненных точек проката")
        finally:
            CacheLock.release()

    @Bot.callback_query_handler(func=lambda call: True)
    def callback_handle(call):
        Logger.debug(callback_handle.__name__, call.data)
        global Database
        CacheLock.acquire()
        try:
            assert call.message.chat.id in UsersCache
            assert call.data in UsersCache[call.message.chat.id]
            assert call.data in PointsCache
            cursor = Database.cursor()
            cursor.execute('DELETE FROM %s WHERE chat_id=%s AND point_id=%s;' %
                           (constants.POSTGRES_TABLE,
                            str(call.message.chat.id),
                            str(call.data)))
            try:
                Database.commit()
            except psycopg2.DatabaseError as error:
                Logger.debug("Database error: %s" % error)
            finally:
                cursor.close()
            UsersCache[call.message.chat.id].remove(call.data)
            Bot.send_message(call.message.chat.id, "Ок, больше не буду показывать эту точку :)")
        finally:
            CacheLock.release()

    @Bot.message_handler(commands=['manage'])
    def handle_manage(message):
        Logger.debug(handle_manage.__name__, message)
        CacheLock.acquire()
        try:
            if message.chat.id not in UsersCache:
                Logger.debug("There are no points")
                raise VelobotException("No points for user")
            for point_id in UsersCache[message.chat.id]:
                point = PointsCache[point_id]
                Bot.send_location(message.chat.id, point["location"][0], point["location"][1])
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton(text="Удалить", callback_data=point_id))
                Bot.send_message(message.chat.id, "Адрес: %s" % (point["address"]), reply_markup=markup)
        except (KeyError, VelobotException):
            Bot.send_message(message.chat.id, "Упс! У вас еще нет сохраненных точек проката")
        finally:
            CacheLock.release()

    @Bot.message_handler(content_types=['location'])
    def handle_new_location(message):
        LoggingUtils.log_telegram_message(handle_new_location.__name__, message)
        user_point = (message.location.latitude, message.location.longitude)
        min_distance = False
        min_bike = -1
        min_address = "null"
        min_location = False
        # TODO Добавить поддержку транзакционности
        CacheLock.acquire()
        try:
            for key in PointsCache.keys():
                item = PointsCache[key]
                distance = haversine(item['location'], user_point, Unit.METERS)
                if min_distance is False or min_distance > distance:
                    min_distance = distance
                    min_bike = key
                    min_address = item['address']
                    min_location = item['location']
            if message.chat.id in UsersCache:
                if min_bike in UsersCache[message.chat.id]:
                    Bot.send_message(message.chat.id, "Ой. Кажется, вы уже подписаны на ближайщую точку проката")
                    raise VelobotException("Location already exists")
                UsersCache[message.chat.id].append(min_bike)
            else:
                UsersCache[message.chat.id] = [min_bike]
        except VelobotException:
            pass
        finally:
            CacheLock.release()
        cursor = Database.cursor()
        cursor.execute("INSERT INTO %s VALUES (%s, %s);" %
                       (constants.POSTGRES_TABLE,
                        str(message.chat.id),
                        str(min_bike)))
        try:
            Database.commit()
            Bot.send_location(message.chat.id, min_location[0], min_location[1])
            Bot.send_message(message.chat.id, "Я добавил новую велопарковку по адресу %s" % min_address)
        except psycopg2.DatabaseError as error:
            Logger.debug("Database error: %s" % error)
        finally:
            cursor.close()


def start():
    preinstall_logger(logging.DEBUG)
    preinstall_database(constants.POSTGRES_PREINSTALL)
    bind_handlers()

    try:
        scrapper_thread = ScraperThread()
        bot_thread = BotThread()
        scrapper_thread.start()
        bot_thread.start()
        scrapper_thread.join()
        bot_thread.join()
    except BaseException as error:
        Logger.error("Error occurred: %s" % error)


if __name__ == "__main__":
    start()
