# coding=utf-8

import time
import logging
import json
from python_anticaptcha import AnticaptchaClient, NoCaptchaTaskProxylessTask, NoCaptchaTask, AnticaptchaException
from deathbycaptcha import SocketClient as DBCClient, DEFAULT_TOKEN_TIMEOUT


logger = logging.getLogger(__name__)


class PitcherRegistry(object):
    pitchers = {}

    def register(self, cls):
        self.pitchers[cls.name] = cls
        return cls

    def get_pitcher(self, name):
        return self.pitchers[name]


registry = pitchers = PitcherRegistry()


class Pitcher(object):
    name = None
    tries = 3
    job = None
    client = None
    website_url = None
    website_key = None
    website_name = None
    solve_time = None
    success = False

    def __init__(self, website_name, website_url, website_key, tries=3):
        self.tries = tries
        self.website_name = website_name
        self.website_key = website_key
        self.website_url = website_url
        self.success = False
        self.solve_time = None

    def get_client(self):
        raise NotImplementedError

    def get_job(self):
        raise NotImplementedError

    def _throw(self):
        self.client = self.get_client()
        self.job = self.get_job()

    def throw(self):
        t = time.time()
        data = self._throw()
        if self.success:
            self.solve_time = time.time() - t
            logger.info("%s: Solving took %ss", self.website_name, int(self.solve_time))
        return data


@registry.register
class AntiCaptchaProxyLessPitcher(Pitcher):
    name = "AntiCaptchaProxyLess"
    host = "api.anti-captcha.com"
    language_pool = "en"
    client_key = None
    use_ssl = True

    def __init__(self, website_name, client_key, website_url, website_key, tries=3, host=None, language_pool=None,
                 use_ssl=True):
        super(AntiCaptchaProxyLessPitcher, self).__init__(website_name, website_url, website_key, tries=tries)
        self.client_key = client_key
        self.host = host or self.host
        self.language_pool = language_pool or self.language_pool
        self.use_ssl = use_ssl

    def get_client(self):
        return AnticaptchaClient(self.client_key, self.language_pool, self.host, self.use_ssl)

    def get_job(self):
        task = NoCaptchaTaskProxylessTask(website_url=self.website_url, website_key=self.website_key)
        return self.client.createTask(task)

    def _throw(self):
        for i in range(self.tries):
            try:
                super(AntiCaptchaProxyLessPitcher, self)._throw()
                self.job.join()
                ret = self.job.get_solution_response()
                if ret:
                    self.success = True
                    return ret
            except AnticaptchaException as e:
                if i >= self.tries - 1:
                    logger.error("%s: Captcha solving finally failed. Exiting", self.website_name)
                    return

                if e.error_code == 'ERROR_ZERO_BALANCE':
                    logger.error("%s: No balance left on captcha solving service. Exiting", self.website_name)
                    return

                elif e.error_code == 'ERROR_NO_SLOT_AVAILABLE':
                    logger.info("%s: No captcha solving slot available, retrying", self.website_name)
                    time.sleep(5.0)
                    continue

                elif e.error_code == 'ERROR_KEY_DOES_NOT_EXIST':
                    logger.error("%s: Bad AntiCaptcha API key", self.website_name)
                    return

                elif e.error_id is None and e.error_code == 250:
                    # timeout
                    if i < self.tries:
                        logger.info("%s: Captcha solving timed out, retrying", self.website_name)
                        time.sleep(1.0)
                        continue
                    else:
                        logger.error("%s: Captcha solving timed out three times; bailing out", self.website_name)
                        return
                raise


@registry.register
class DBCProxyLessPitcher(Pitcher):
    name = "DeathByCaptchaProxyLess"
    username = None
    password = None

    def __init__(self, website_name, username, password, website_url, website_key,
                 timeout=DEFAULT_TOKEN_TIMEOUT, tries=3):
        super(DBCProxyLessPitcher, self).__init__(website_name, website_url, website_key, tries=tries)
        self.username = username
        self.password = password
        self.timeout = timeout

    def get_client(self):
        return DBCClient(self.username, self.password)

    def get_job(self):
        pass

    def _throw(self):
        super(DBCProxyLessPitcher, self)._throw()
        payload = json.dumps({
            "googlekey": self.website_key,
            "pageurl": self.website_url
        })
        try:
            #balance = self.client.get_balance()
            data = self.client.decode(timeout=self.timeout, type=4, token_params=payload)
            if data and data["is_correct"]:
                self.success = True
                return data["text"]
        except:
            raise

