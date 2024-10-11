import asyncio
import websockets
import json
import os
import logging
from decimal import Decimal
from dotenv import load_dotenv
from itertools import cycle
from frame import Frame
from setinterval import SetInterval
from rgbmatrix import graphics
from millify import millify

logging.basicConfig(level=logging.INFO)

class BinanceSocket(Frame):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_dotenv()

        self.symbols = os.getenv('SYMBOLS', '').split(',')
        if not self.symbols or self.symbols == ['']:
            raise ValueError("No symbols found in environment variable SYMBOLS. Ensure SYMBOLS is set.")

        try:
            self.refresh = int(os.getenv('TOGGLE_RATE', 3))
            if self.refresh <= 0:
                raise ValueError("TOGGLE_RATE must be a positive integer.")
        except ValueError:
            raise ValueError("Invalid TOGGLE_RATE. Please provide a positive integer.")

        self.data = {}
        self.ctr = 0
        self.cycle_symbols = cycle(self.symbols)
        self.current_symbol = next(self.cycle_symbols)

        # Load fonts
        self.fonts = self.load_fonts()
        self.canvas = None

    def load_fonts(self):
        fonts = {}
        try:
            fonts['symbol'] = graphics.Font()
            fonts['symbol'].LoadFont('fonts/7x14B.bdf')

            fonts['price'] = graphics.Font()
            fonts['price'].LoadFont('fonts/6x12.bdf')

            fonts['change'] = graphics.Font()
            fonts['change'].LoadFont('fonts/6x10.bdf')

            fonts['vol'] = graphics.Font()
            fonts['vol'].LoadFont('fonts/5x7.bdf')
        except Exception as e:
            logging.error(f"Error loading fonts: {e}")
            raise
        return fonts

    def get_pairs_payload(self):
        symbols = [f'"{symbol.replace('-', '')}@ticker"' for symbol in self.symbols]
        str_symbols = ','.join(symbols)
        return f'{{"method": "SUBSCRIBE", "params": [{str_symbols}], "id": 1}}'

    async def fetch_ticker_data(self):
        while True:
            try:
                url = f"wss://stream.binance.com:9443/ws/{self.current_symbol.replace('-', '')}@ticker"
                async with websockets.connect(url) as sock:
                    pairs_payload = self.get_pairs_payload()
                    logging.info(f"Subscribing with payload: {pairs_payload}")
                    await sock.send(pairs_payload)

                    async for message in sock:
                        self.handle_message(message)
            except (websockets.ConnectionClosed, asyncio.TimeoutError) as e:
                logging.error(f"WebSocket connection error: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)

    def handle_message(self, message):
        try:
            data = json.loads(message)
            if 'id' not in data:
                self.data[data['s']] = {
                    'change': '{0:.4f}'.format(Decimal(data['P'])),
                    'price': data['c'],
                    'vol': data['v'],
                    'symbol': data['s'],
                    'quote': data['q']
                }
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding message: {e}")

    def render_ticker_canvas(self, symbol):
        key = symbol.replace('-', '').upper()
        if key not in self.data:
            return

        data = self.data[key]

        if not self.canvas:
            self.canvas = self.matrix.CreateFrameCanvas()

        self.canvas.Clear()

        price_change_percent = float(data['change'])
        price = float(data['price'])

        prefix = '' if data['change'].startswith('-') else '+'

        change_width = sum(
            [self.fonts['change'].CharacterWidth(ord(c)) for c in f'{prefix}{price_change_percent:.2f}']
        )

        change_x = 64 - change_width

        change_color = (
            graphics.Color(220, 47, 2) if data['change'].startswith('-') else graphics.Color(0, 255, 0)
        )

        vol_txt = self.get_volume_text(data)

        graphics.DrawText(
            self.canvas, self.fonts['change'], change_x, 9, change_color, f'{prefix}{price_change_percent:.2f}'
        )
        graphics.DrawText(self.canvas, self.fonts['price'], 3, 20, graphics.Color(203, 243, 240), vol_txt)
        graphics.DrawText(self.canvas, self.fonts['symbol'], 3, 11, graphics.Color(255, 209, 102), symbol[0:3].upper())
        graphics.DrawText(self.canvas, self.fonts['price'], 3, 30, change_color, f'{price:,.5f}')

        self.matrix.SwapOnVSync(self.canvas)

    def get_volume_text(self, data):
        prefixes = ['K', 'M', 'B']
        n = self.refresh / 2
        vol_txt = ''

        if self.ctr >= n:
            vol_txt = 'B:' + millify(data['vol'], precision=3, prefixes=prefixes)
        else:
            vol_txt = 'Q:' + millify(data['quote'], precision=3, prefixes=prefixes)

        if self.ctr == self.refresh:
            self.ctr = 0

        self.ctr += 1
        return vol_txt

    def toggle_symbol(self):
        self.current_symbol = next(self.cycle_symbols)
        self.ctr = 0
        logging.info(f"Switched to symbol: {self.current_symbol}")

    def run_ticker(self):
        self.render_ticker_canvas(self.current_symbol)

    def run(self):
        SetInterval(self.refresh, self.toggle_symbol)
        SetInterval(1, self.run_ticker)
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.fetch_ticker_data())
        except KeyboardInterrupt:
            logging.info("Shutting down...")
            loop.stop()

if __name__ == '__main__':
    binance_socket = BinanceSocket()
    binance_socket.initMatrix()
    binance_socket.run()