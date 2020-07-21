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
