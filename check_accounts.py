import logging
import tempfile
import traceback
import asyncio
import datetime
# from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import *
from lxml import html
import os
import re
from os import environ
from time import time

from telethon import TelegramClient, events, errors
from telethon.tl.types import DocumentAttributeVideo

logging.basicConfig(level=logging.WARNING)

api_id = environ["api_id"]
api_hash = environ["api_hash"]


client = TelegramClient("tweet_the_check", api_id, api_hash)
client.start(bot_token=environ["bot_token"])


class Timer():
    def __init__(self, current):
        self.current = current
        self.action = "downloading"

    def set_current(self, current):
        self.current = current

    def get_current(self):
        return self.current

    def set_action(self, action):
        self.action = action


class RequestsCounter():

    # class variables
    number_of_requests = 0
    max_requests = 80
    number_of_minutes = 15
    timer = number_of_minutes * 60
    last_datetime = datetime.datetime.now()

    @classmethod
    async def increase_requests(cls, conv):
        cls.number_of_requests += 1
        if cls.number_of_requests > cls.max_requests and cls.is_less_than_number_of_minutes():
            await countdown(cls.timer, conv)
            cls.number_of_requests = 0
        elif not cls.is_less_than_number_of_minutes():
            cls.number_of_requests = 0

    @classmethod
    def print_total_requests(cls):
        print(f"Total Requests = {cls.number_of_requests}")

    @classmethod
    def set_timer(cls, timer_update):
        cls.timer = timer_update

    @classmethod
    def reset_timer(cls):
        cls.timer = cls.number_of_minutes * 60

    @classmethod
    def is_less_than_number_of_minutes(cls):
        time_difference = datetime.timedelta(minutes=cls.number_of_minutes)
        return datetime.datetime.now() < cls.last_datetime + time_difference


async def countdown(timer_sec, conv):
    minutes, seconds = divmod(timer_sec,
                              60)  # to turn the seconds from timer variable into minutes and seconds
    hours, minutes = divmod(minutes, 60)  # to turn the minutes variable into hours and minutes
    countdown_display = f"({str(hours).zfill(2)}:{str(minutes).zfill(2)}:{str(seconds).zfill(2)})"
    message = await conv.send_message(f"{countdown_display}الرجاء الإنتظار لمدة\n")
    while timer_sec > 0:
        await asyncio.sleep(1)
        timer_sec -= 1
        RequestsCounter.set_timer(timer_sec)
        if timer_sec % 60 == 0:
            minutes, seconds = divmod(timer_sec,
                                      60)  # to turn the seconds from timer variable into minutes and seconds
            hours, minutes = divmod(minutes, 60)  # to turn the minutes variable into hours and minutes
            countdown_display = f"({str(hours).zfill(2)}:{str(minutes).zfill(2)}:{str(seconds).zfill(2)})"

            await message.edit(f"{countdown_display}الرجاء الإنتظار لمدة\n")
    RequestsCounter.reset_timer()
    await message.delete()


async def check_account_status(filename, temp_dir, total_accounts, conv):
    count = 0
    temp_usernames_file = f"{temp_dir}/{filename}"  # where usernames are stored
    temp_results = f"{temp_dir}/results.txt"
    message = await conv.send_message("جاري إنشاء المتصفح والتحقق من الحسابات...")

    options = webdriver.ChromeOptions()
    options.binary_location = environ.get("GOOGLE_CHROME_BIN")
    options.add_argument("--window-size=1325x744")  # todo: comment when debugging
    # options.add_argument("start-maximized")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--headless")

    browser = webdriver.Chrome(executable_path=environ["CHROMEDRIVER_PATH"], options=options)
    # browser = webdriver.Chrome(executable_path="./chromedriver", options=options)
    # browser.maximize_window()

    wait = WebDriverWait(browser, timeout=10, poll_frequency=0.5, ignored_exceptions=(NoSuchElementException,))

    with open(temp_usernames_file, 'r') as f_obj:
        for user in f_obj:
            user = user.strip()
            browser.get(f"https://twitter.com/{user}")

            # wait.until(ec.presence_of_element_located(
            #     (By.XPATH, "//div[@role='status']/div[contains(@aria-label,"
            #                " 'New Tweets are available')]//span[contains(text(), 'See new')]")))
            # wait.until(ec.presence_of_element_located((By.XPATH, "//span[contains(text(), 'happening')]")))
            wait.until(ec.presence_of_element_located((By.XPATH, "//div[@role='presentation']")))

            raw_html = browser.page_source
            html_source = html.fromstring(raw_html)

            account = html_source.xpath("//a[@role='tab']//span[text()='Media']")
            suspended = html_source.xpath("//span[contains(text(), 'suspended')]")
            not_found = html_source.xpath("//span[text()='This account doesn’t exist']")
            restricted = html_source.xpath("//span[contains(text(), 'restricted')]")

            if len(account) > 0 and len(suspended) == 0:
                with open(temp_results, 'a+') as r_obj:
                    r_obj.write(f"✅ account {user} works fine.\n")
            elif len(suspended) > 0:
                with open(temp_results, 'a+') as r_obj:
                    r_obj.write(f"❌ account {user} is suspended.\n")
            elif len(restricted) > 0:
                with open(temp_results, 'a+') as r_obj:
                    r_obj.write(f"📞 account {user} is restricted.\n")
            elif len(not_found) > 0:
                with open(temp_results, 'a+') as r_obj:
                    r_obj.write(f"⚠️ account {user} was not found!\n")
            else:
                with open(temp_results, 'a+') as r_obj:
                    r_obj.write(f"account {user} status unknown!!!!!!!!!!\n")
                # with open("html.txt", 'w', encoding="UTF_8") as d_obj:  # todo: uncomment when debugging
                #     d_obj.write(raw_html)

            # check progress every five accounts
            count += 1
            if count % 5 == 0:
                percentage = (count / total_accounts) * 100
                await message.edit(f"تم الإنتهاء من {percentage:.2f}%")

    browser.quit()
    await message.delete()
    return temp_results


# pattern= string pattern for checking the "whole string"
@client.on(events.NewMessage(pattern=r"((.|\n)*\s|\b)?@\w+(\s(.|\n)*|\b)?", func=lambda e: e.is_private))
async def check_accounts(event):

    filename = "check.txt"
    # locate_accounts = re.compile(r"(?:\b|\s)(?P<account>@\w+)(?:\b|\s)")
    locate_accounts = re.compile(r"(?<!\w)@\w+")

    async def progress(cur, tot):
        if time() >= last.get_current() + 2:
            last.set_current(time())
            await message.edit(f'تم {last.action} {round(100 * cur / tot, 2)}% ')

    with tempfile.TemporaryDirectory() as temp_directory:

        async with client.conversation(event.chat_id, timeout=None, total_timeout=None) as conv:
            try:

                message = await conv.send_message("جار التحقق...")

                last = Timer(time())

                accounts = set([i.group() for i in locate_accounts.finditer(event.message.message)])
                total_acc = len(accounts)
                temp_file = f"{temp_directory}/{filename}"

                with open(temp_file, "a+", encoding="UTF8") as f_obj:
                    f_obj.write('\n'.join(accounts) + '\n')

                temp_results = await check_account_status(filename, temp_directory, total_acc, conv)

                await message.delete()
                with open(temp_results, 'r') as send_obj:
                    await conv.send_message("النتائج:")
                    await conv.send_message(send_obj.read())

            except:
                traceback.print_exc()
                await event.reply("حدث خلل ما الرجاء التجربة مرة اخرى")


client.run_until_disconnected()
