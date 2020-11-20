import asyncio
import pyppeteer
import logging
import time
import random
import string
import json
import re
from stealth import stealth
from aiocfscrape import CloudflareScraper
from bs4 import BeautifulSoup
import sys
import base64
from typing import Optional
from fastapi import FastAPI, Form
import urllib.parse
from solver import PuzleSolver
import hashlib

async def url_2_image(url: str):
	async with CloudflareScraper() as session:
		async with session.get(url) as response:
			return await response.read()

def base64_decode(text: str) -> str:
	return base64.b64decode(text.encode('utf-8')).decode('utf-8')

def sha1(value) -> str:
	value = str(value)
	return hashlib.sha1(value.encode('utf-8')).hexdigest()

if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def base36_encode(number: int, alphabet: str = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ') -> str:
	base36 = ''
	sign = ''
	if number < 0:
		sign = '-'
		number = -number
	if 0 <= number <= len(alphabet):
		return sign + alphabet[number]

	while number != 0:
		number, i = divmod(number, len(alphabet))
		base36 = alphabet[i] + base36
	return sign + base36

def glkote_init() -> str:
	chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"[:]
	chars_len = len(chars)
	scenarioTitle = base36_encode(int(time.time() * 1000))
	uuid = [0] * 36
	uuid[8] = uuid[13] = uuid[18] = uuid[23] = '_'
	uuid[14] = '4'

	for i in range(36):
		if uuid[i] != 0:
			continue
		r = int(random.random() * chars_len)
		uuid[i] = chars[int((3 & r) | 8 if 19 == i else r)]

	return f'verify_{scenarioTitle.lower()}_{"".join(uuid)}'

class Browser:
	_browser = None
	_verifyFp = None
	_session = None
	_loop = None
	def __init__(self, loop):
		self._loop = loop if loop is not None else asyncio.get_event_loop()

	@property	
	def browser(self):
		return self._browser

	@property
	def width(self):
		return self._width
		
	@property
	def height(self):
		return self._height

	@property
	def cookies(self):
		return self._cookies

	async def __aenter__(self):
		await self.start()
		return self

	async def start(self):
		self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36"
		self._options = {
			'args': [
						"--no-sandbox",
						"--disable-setuid-sandbox",
						"--disable-infobars",
						"--window-position=0,0",
						"--ignore-certifcate-errors",
						"--ignore-certifcate-errors-spki-list",
						"--user-agent=" + self.user_agent
					],
			'headless': True,
			'ignoreHTTPSErrors': True,
			'userDataDir': "./tmp",
			'handleSIGINT': False,
			'handleSIGTERM': False,
			'handleSIGHUP': False
		}
		self._browser = await pyppeteer.launch(self._options)
		self._page = await self._browser.newPage()
		await self._page.evaluateOnNewDocument('() => { delete navigator.__proto__.webdriver; }')
		await stealth(self._page)
		await self._page.goto('https://www.tiktok.com/foryou?lang=ru', {'waitUntil': 'load'})

		self._user_agent = await self._page.evaluate('() => { return navigator.userAgent; }')
		# await self._page.evaluate('() => { ' + await self.__get_js() + ' }')
		self._cookies = {x['name']: x['value'] for x in await self._page.cookies()}
		def _verifyFp():
			return ''.join(random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits) for i in range(16))
		self._verifyFp = self._cookies.get('tt_csrf_token', _verifyFp())
		
		self._width = await self._page.evaluate('() => { return screen.width; }')
		self._height = await self._page.evaluate('() => { return screen.height; }')

	@property
	def verifyFp(self):
		return glkote_init()

	async def _signature(self, url) -> str:
		return await self._page.evaluate('() => { return window.byted_acrawler.sign( { url: "' + url + '" } ); }')

	async def signature(self, url: str, kwargs: dict):
		kwargs.setdefault('verifyFp', self.verifyFp)
		_parametrs = '&'.join([f'{key}={value}' for key, value in kwargs.items()])
		_signature = await self._signature(f'{url}?{_parametrs}')
		kwargs.setdefault('_signature', _signature)

		parametrs = '&'.join([f'{key}={value}' for key, value in kwargs.items()])  
		return f'{url}?{parametrs}'

	async def __get_js(self):
		async with CloudflareScraper(loop=self._loop, headers={}) as session:
			async with session.get('https://sf-tb-sg.ibytedtos.com/obj/rc-web-sdk-sg/acrawler.js') as response:
				return await response.text()

	async def __aexit__(self, *args):
		await self._browser.close()
		self._browser.process.communicate()

class TikTok:
	_browser = None
	_re_tiktok_pc_url = re.compile(r'http(s)?://.*tiktok\.com/@(?P<username>.+)/video/(?P<tiktok_id>\d+)')
	_re_tiktok_mobile_url = re.compile(r'http(s)?://.+\.tiktok\.com/v/(?P<tiktok_id>\d+)')
	_re_tiktok_mobile_2_url = re.compile(r'http(s)?://.+\.tiktok\.com/(?P<id>\w+)')

	_re_donor_no_wm = re.compile(r'tt:\'(?P<tt>.+)\',\s+ts:(?P<ts>\d+)')

	def __init__(self, loop = None):
		self._loop = loop if loop is not None else asyncio.get_event_loop()
		self._browser = Browser(loop=self._loop)

	@property
	def browser(self):
		return self._browser
	
	async def start(self) -> None:
		await self._browser.start()
		self._user_agent = self._browser.user_agent
		def _params_formatter(parametr: str) -> str:
			return parametr.replace("/", "%2F").replace(" ", "+").replace(";", "%3B")

	async def request(self, url: str, kwargs: dict = {}, return_bytes=False, payload=None) -> dict:
		async with CloudflareScraper(loop=self._loop, headers={
																'authority': 'm.tiktok.com',
																'accept': 'application/json, text/plain, */*',
																'accept-encoding': 'gzip, deflate',
																'accept-language': 'en-US,en;q=0.9',
																'referrer': 'https://m.tiktok.com/',
																'sec-fetch-dest': 'empty',
																'sec-fetch-mode': 'cors',
																'sec-fetch-site': 'same-site',
																'user-agent': self._user_agent,
																'cookie': ';'.join([f'{key}={value}' for key, value in self.browser.cookies.items()])
															}) as session:
			url = await self._browser.signature(url, kwargs)
			if payload is not None:
				async with session.post(url, json=payload) as response:
					return await response.text()

			async with session.get(url) as response:
				if return_bytes:
					return response.content
				try:
					_json = await response.json(content_type=None)
					code = _json.get('code', -1)
					if code != '10000':
						return _json
					return await self.captcha(_json, url, kwargs, return_bytes)

				except Exception as e:
					logging.error(e, exc_info=True)
					print(f'Failed on {url}; Converting to json error; Text: {await response.text()}')
					raise Exception('Invalid Response!!!')


	async def captcha(self, _captcha:dict, url:str, kwargs:dict = {}, return_bytes:bool = False) -> dict: #TODO: Not be completed
		api_url = 'https://verification-va.byteoversea.com/captcha/get'
		api_kwargs = {
			'lang': 'ru',
			'app_name': '',
			'h5_sdk_version': '2.15.17',
			'sdk_version': '',
			'iid': 0,
			'did': 0,
			'device_id': 0,
			'ch': 'web_text',
			'aid': 1988,
			'os_type': 2,
			'tmp': int(time.time() * 1000),
			'platform': 'pc',
			'webdriver': 'undefined',
			'fp': _captcha.get('fp', self.browser.verifyFp),
			'type': 'verify',
			'detail': urllib.parse.quote(str({"exempt_duration":86400,"punish_duration":30,"region":"va"})),
			'subtype': 'slide',
			'challenge_code': 3058,
			'os_name': 'windows'
		}

		result = await self.request(
									url = api_url,
									kwargs = api_kwargs,
									return_bytes = False
								)

		if not result:
			return None
		if result.get('code', -1) != 200:
			return None

		data = result.get('data', {})
		questions = data.get('question', {})
		background = questions.get('url1', None)
		puzzle = questions.get('url2', None)
		offset_y = questions.get('tip_y', None)
		challenge_code = data.get('challenge_code', 99999)

		if not (background and puzzle and offset_y and challenge_code):
			return None

		background = await url_2_image(background)
		puzzle = await url_2_image(puzzle)

		solver = PuzleSolver(puzzle, background)
		solution = solver.get_position(offset_y)
		if not solution:
			return

		x, _ = solution

		count = random.randint(60, 100)

		Y = [offset_y] * count
		X = [1]
		for i in range(count):
			step = random.randint(2, 5)
			X.append(X[-1] + step)
		times = [101]
		for i in range(count):
			step = random.randint(10, 15)
			times.append(times[-1] + step)
		reply = [
			{
				'x': X[i],
				'y': Y[i],
				'relative_time': times[i]
			}

			for i in range(count)
		]

		#generate in captcha -> handleDrag
		tmp = time.time() - 5000 - times[-1] * 1000
		times_full = [x*1000 + tmp for x in times]

		m = [
			{
				'x': X[i] + random.randint(60, 65),
				'y': Y[i] + 254.5,
				'time': times_full[i]
			}

			for i in range(count)
		]

		model = sha1(time.time() * 1000)
		payload = {
			'modified_img_width': 336,
			'id': model,
			'mode': 'slide',
			'reply': reply,
			'models': {
				'x': {},
				'y': {},
				'z': [],
				't': [],
				'm': m #тоже, что и reply, но время полное, а координаты по всему экрану
			},
			'log_params': {

			}
		}

		api_url = 'https://verification-va.byteoversea.com/captcha/verify'
		api_kwargs = {
			'lang': 'ru',
			'app_name': '',
			'h5_sdk_version': '2.15.17',
			'sdk_version': '',
			'iid': 0,
			'did': 0,
			'device_id': 0,
			'ch': 'web_text',
			'aid': 1988,
			'os_type': 2,
			'tmp': int(time.time() * 1000),
			'platform': 'pc',
			'webdriver': 'undefined',
			'fp': _captcha.get('fp', self.browser.verifyFp),
			'type': 'verify',
			'detail': urllib.parse.quote(str({"exempt_duration":86400,"punish_duration":30,"region":"va"})),
			'subtype': 'slide',
			'challenge_code': challenge_code,
			'os_name': 'windows'
		}
		#Last query ( Verify ) not working, because payload incorrect

		print(_captcha.get('fp', self.browser.verifyFp))
		result = await self.request(url=api_url, kwargs=api_kwargs, return_bytes=False, payload=payload)
		print(result)
		return result


	async def trending(self, count:int = 30, language:str = 'en', region:str = 'US') -> list:
		data = []
		max_count = 50
		max_cursor = 0
		first = True
		while len(data) < count:
			real_count = count if count < max_count else max_count
			kwargs = {
				'count': real_count,
				'id': 1,
				'type': 5,
				'secUid': '',
				'maxCursor': max_cursor,
				'minCursor': 0,
				'sourceType': 12,
				'appId': 1233,
				'region': region,
				'language': language
			}
			response = await self.request('https://m.tiktok.com/api/item_list/', kwargs, False)
			if not response:
				return
			if 'items' in response:
				data.extend(response['items'])

			if not (response['hasMore'] and first):
				return data
			first = False
		return data[:count]

	async def tiktok_by_id(self, id: int):
		return await self.request('https://m.tiktok.com/api/item/detail/', {
				'itemId': id,
				'language': 'en'
			})

	async def tiktok_by_url(self, url: str):
		m_pc = self._re_tiktok_pc_url.search(url)
		m_mobile = self._re_tiktok_mobile_url.search(url)
		m_mobile_2 = self._re_tiktok_mobile_2_url.search(url)

		if m_pc:
			return await self.tiktok_by_id(int(m_pc.group('tiktok_id')))
		elif m_mobile:
			return await self.tiktok_by_id(int(m_mobile.group('tiktok_id')))
		elif m_mobile_2:
			async with CloudflareScraper(loop=self._loop, headers={
																	'authority': 'm.tiktok.com',
																	'accept': 'application/json, text/plain, */*',
																	'accept-encoding': 'gzip, deflate',
																	'accept-language': 'en-US,en;q=0.9',
																	'referrer': 'https://www.tiktok.com/',
																	'sec-fetch-dest': 'empty',
																	'sec-fetch-mode': 'cors',
																	'sec-fetch-site': 'same-site',
																	'user-agent': self._user_agent
																}) as session:
				async with session.get(url) as response:
					m_pc = self._re_tiktok_pc_url.search(str(response.url))
					if m_pc:
						return await self.tiktok_by_id(int(m_pc.group('tiktok_id')))
			return False
		else:
			return False

	async def tiktok_video_no_watermark(self, url: str):
		async with CloudflareScraper(headers={'user-agent': self._user_agent}) as session:
			page = await session.get('https://ssstiktok.io/ru')
			if page.status != 200:
				return {'url': None}
			soup = BeautifulSoup(await page.text(), features="html.parser")  # Иницилизация обработки HTML тегов
			form = soup.find(class_='pure-form pure-g hide-after-request')
			endpoint = form['data-hx-post']
			vals = form['include-vals']
			m = self._re_donor_no_wm.search(vals)
			if not m:
				return {'url': None}
			tt, ts = m.group('tt', 'ts')

			response = await session.post(f'https://ssstiktok.io{endpoint}', data={
					'id': url,
					'locale': 'ru',
					'tt': tt,
					'ts': ts
				})
			soup = BeautifulSoup(await response.text(), features="html.parser")

			for link in soup.find_all('a'):
				return {'url': base64_decode(link['href'].split('/dl?url=').pop())}
		return {'url': None}

	async def user_profile(self, username: str):
		return await self.request('https://m.tiktok.com/api/user/detail/', {
				'uniqueId': username, 'language': 'en'
			})

	async def user_videos(self, user_id: int, user_sec_uid: str, count: int):
		data = []
		max_count = 50
		max_cursor = 0
		first = True
		while len(data) < count:
			real_count = count if count < max_count else max_count
			kwargs = {
				'count': real_count,
				'id': user_id,
				'type': 0,
				'secUid': user_sec_uid,
				'maxCursor': max_cursor,
				'minCursor': 0,
				'sourceType': 8,
				'appId': 1233,
			}
			response = await self.request('https://m.tiktok.com/api/item_list/', kwargs, False)
			if 'items' in response:
				data.extend(response['items'])

			if not (response['hasMore'] and first):
				return data
			first = False
		return data[:count]

tiktok = None
app = FastAPI()

@app.on_event("startup")
async def on_startup():
	global tiktok
	tiktok = TikTok()
	await tiktok.start()

@app.on_event("shutdown")
async def on_shutdown():
	global tiktok
	await tiktok.browser.browser.close()
	tiktok.browser.browser.process.communicate()

@app.post('/trending')
async def trending(count: int = Form(30, title='Count videos')):
	return await tiktok.trending(count)

@app.post('/tiktokById')
async def trending(id: int = Form(..., title='Video id')):
	return await tiktok.tiktok_by_id(id)

@app.post('/tiktokByUrl')
async def trending(url: str = Form(..., title='Video url ( tiktok )')):
	return await tiktok.tiktok_by_url(url)

@app.post('/tiktokVideoNoWaterMark')
async def trending(url: str = Form(..., title='Video url ( tiktok )')):
	return await tiktok.tiktok_video_no_watermark(url)

@app.post('/userProfile')
async def trending(username: str = Form(..., title='Username of user')):
	return await tiktok.user_profile(username)

@app.post('/userVideos')
async def trending(userId: int = Form(..., title='User id'), userSecUid: str = Form(..., title='SecUid user'), count: int = Form(..., title='Count videos')):
	return await tiktok.user_videos(userId, userSecUid, count)

@app.post('/signature')
async def signature(url: int = Form(..., title='URL with kwargs')):
	return await tiktok.browser.signature(url, {})

@app.get('/cookies')
async def signature():
	return tiktok.browser.cookies

@app.get('/')
async def mainpage():
	return await tiktok.trending(30)

@app.get('/captcha')
async def captcha():
	return await tiktok.captcha({
			'fp': tiktok.browser.verifyFp
		}, '', {})