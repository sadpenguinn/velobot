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

MainKeyboard = telebot.types.ReplyKeyboardMarkup()
status_button = telebot.types.KeyboardButton(text='Мои парковки')
manage_button = telebot.types.KeyboardButton(text='Управление')
MainKeyboard.add(status_button, manage_button)


class Transaction:
    @staticmethod
    def open():
        global PointsCache
        global UsersCache
        CacheLock.acquire()
        points_cache_copy = PointsCache.copy()
        users_cache_copy = UsersCache.copy()
        CacheLock.release()
        return points_cache_copy, users_cache_copy

    @staticmethod
    def commit(user, users_changes):
        global UsersCache
        CacheLock.acquire()
        UsersCache[user] = users_changes
        CacheLock.release()


class LoggingUtils:
    @staticmethod
    def log(func_name, message):
        def get_message(t, msg):
            return {
                'text': str(msg.text),
                'location': str(msg.location),
            }.get(t, 'null')

        Logger.debug("%s: New message with type %s from %s %s - @%s - id: %s: %s" % (func_name,
                                                                                     message.content_type,
                                                                                     message.from_user.first_name,
                                                                                     message.from_user.last_name,
                                                                                     message.from_user.username,
                                                                                     message.from_user.id,
                                                                                     get_message(
                                                                                         message.content_type,
                                                                                         message)))


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
    global UsersCache
    cursor = Database.cursor()
    if force:
        cursor.execute('DROP TABLE IF EXISTS %s;' % constants.POSTGRES_TABLE)
        cursor.execute('CREATE TABLE IF NOT EXISTS %s ('
                       'chat_id INTEGER NOT NULL,'
                       'point_id VARCHAR(4) NOT NULL,'
                       'PRIMARY KEY (chat_id, point_id)'
                       ');' % constants.POSTGRES_TABLE)
    cursor.execute('SELECT * FROM %s' % constants.POSTGRES_TABLE)
    records = cursor.fetchall()
    CacheLock.acquire()
    for record in records:
        UsersCache.setdefault(record[0], []).append(str(record[1]))
    CacheLock.release()
    try:
        Database.commit()
    except psycopg2.DatabaseError as error:
        Logger.debug("Database error: %s" % error)
    finally:
        cursor.close()
    Logger.debug("UsersCache: " + str(UsersCache))


def bind_handlers():
    @Bot.message_handler(commands=['start'])
    def handle_start(message):
        LoggingUtils.log(handle_new_location.__name__, message)

        global MainKeyboard
        Bot.send_message(message.chat.id, "Привет! Я бот для уведомлений о загруженности велостоянок. Просто отправь "
                                          "мне несколько локаций и смотри загруженность ближайщих к ним стоянок по "
                                          "кнопке в меню ", reply_markup=MainKeyboard)

    @Bot.message_handler(content_types=['text'], func=lambda message: True if message.text == 'Мои парковки' else False)
    @Bot.message_handler(commands=['status'])
    def handle_status(message):
        LoggingUtils.log(handle_new_location.__name__, message)

        points, users = Transaction.open()
        # check caches consistency
        if message.chat.id not in users:
            Logger.debug("There are no points")
            Bot.send_message(message.chat.id, "Упс! У вас еще нет сохраненных точек проката")
            return
        # send points
        for point_id in users[message.chat.id]:
            point = points[point_id]
            Bot.send_location(message.chat.id, point["location"][0], point["location"][1])
            Bot.send_message(message.chat.id, "Адрес: %s\nДоступно велосипедов: %s\nВсего портов: %s"
                             % (point["address"],
                                point["available_ordinary"],
                                point["total_ordinary"]))

    @Bot.callback_query_handler(func=lambda call: False)
    def callback_handle(call):
        LoggingUtils.log(handle_new_location.__name__, call)

        points, users = Transaction.open()
        # check caches consistency
        try:
            if call.message.chat.id not in users:
                Logger.debug("Unknown user")
                raise VelobotException("Unknown user")
            if (call.data not in users[call.message.chat.id]) or (call.data not in points):
                Logger.debug("Unknown point")
                raise VelobotException("Unknown point")
        except VelobotException:
            Bot.send_message(call.message.chat.id, "Так. Я не волшебник, такое удалять не буду ;(")
            return
        # delete from database
        global Database
        cursor = Database.cursor()
        cursor.execute('DELETE FROM %s WHERE chat_id=%s AND point_id=%s;' %
                       (constants.POSTGRES_TABLE,
                        str(call.message.chat.id),
                        str(call.data)))
        try:
            Database.commit()
        except psycopg2.DatabaseError as error:
            Logger.debug("Database error: %s" % error)
            Bot.send_message(call.message.chat.id, "У меня тут на сервере бд упала :( Так, и куда звонить?")
            return
        finally:
            cursor.close()
        # commit changes
        users[call.message.chat.id].remove(call.data)
        Transaction.commit(call.message.chat.id, users[call.message.chat.id])
        Bot.send_message(call.message.chat.id, "Ок, больше не буду показывать эту точку :)")

    @Bot.message_handler(content_types=['text'], func=lambda message: True if message.text == 'Управление' else False)
    @Bot.message_handler(commands=['manage'])
    def handle_manage(message):
        LoggingUtils.log(handle_new_location.__name__, message)

        points, users = Transaction.open()
        try:
            if message.chat.id not in users:
                Logger.debug("There are no points")
                raise VelobotException("No points for user")
            for point_id in users[message.chat.id]:
                point = points[point_id]
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton(text="Удалить", callback_data=point_id))
                Bot.send_location(message.chat.id, point["location"][0], point["location"][1])
                Bot.send_message(message.chat.id, "Адрес: %s" % (point["address"]), reply_markup=markup)
        except (KeyError, VelobotException):
            Bot.send_message(message.chat.id, "Упс! У вас еще нет сохраненных точек проката")

    # TODO проверять что нет двух транзакций в рамках одного юзера
    @Bot.message_handler(content_types=['location'])
    def handle_new_location(message):
        LoggingUtils.log(handle_new_location.__name__, message)

        class Nearest:
            distance = None
            point = None
            address = None
            location = None

        user_point = (message.location.latitude, message.location.longitude)
        nearest = Nearest
        points, users = Transaction.open()
        changes = []

        # find nearest velobike station
        for key in points.keys():
            item = points[key]
            distance = haversine(item['location'], user_point, Unit.METERS)
            if nearest.distance is None or nearest.distance > distance:
                nearest.distance = distance
                nearest.point = key
                nearest.address = item['address']
                nearest.location = item['location']
        # save new location
        if message.chat.id in users:
            if nearest.point in users[message.chat.id]:
                Bot.send_message(message.chat.id, "Ой. Кажется, вы уже подписаны на ближайщую точку проката")
                return
            else:
                changes = users[message.chat.id]
                changes.append(nearest.point)
        else:
            changes = [nearest.point]
        cursor = Database.cursor()
        cursor.execute("INSERT INTO %s VALUES (%s, '%s');" %
                       (constants.POSTGRES_TABLE,
                        str(message.chat.id),
                        str(nearest.point)))
        try:
            Database.commit()
        except psycopg2.DatabaseError as error:
            Logger.debug("Database error: %s" % error)
            Bot.send_message(message.chat.id, "Упс, кажется я поломался и не смогу добавить эту точку :(")
            return
        finally:
            cursor.close()
        Bot.send_location(message.chat.id, nearest.location[0], nearest.location[1])
        Bot.send_message(message.chat.id, "Я добавил новую велопарковку по адресу %s" % nearest.address)
        # commit changes
        Transaction.commit(message.chat.id, changes)


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
