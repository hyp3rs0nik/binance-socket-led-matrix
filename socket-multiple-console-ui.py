import asyncio
import websockets
import json
import os
import logging
import sys
import argparse
from decimal import Decimal
from dotenv import load_dotenv
from itertools import cycle
from setinterval import SetInterval
from millify import millify

try:
    import tkinter as tk
    from tkinter import Canvas
except ImportError:
    tk = None

logging.basicConfig(level=logging.INFO)

class BinanceSocket():

    def __init__(self, use_ui=False, *args, **kwargs):
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

        self.use_ui = use_ui
        if self.use_ui and tk is None:
            raise ImportError("Tkinter is required for UI mode but is not available.")

        if self.use_ui:
            self.setup_ui()
        else:
            self.clear_console()

    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Binance Ticker Data")
        self.canvas = Canvas(self.root, width=400, height=200)
        self.canvas.pack()

    def clear_console(self):
        sys.stdout.write("\033[H\033[J")
        sys.stdout.flush()

    def get_pairs_payload(self):
        symbols = [f'"{symbol.replace("-", "")}@ticker"' for symbol in self.symbols]
        str_symbols = ','.join(symbols)
        return f'{{"method": "SUBSCRIBE", "params": [{str_symbols}], "id": 1}}'

    async def fetch_ticker_data(self):
        try:
            url = f"wss://stream.binance.com:9443/ws/{self.current_symbol.replace('-', '')}@ticker"
            async with websockets.connect(url) as sock:
                pairs_payload = self.get_pairs_payload()
                logging.info(f"Subscribing with payload: {pairs_payload}")
                await sock.send(pairs_payload)

                async for message in sock:
                    self.handle_message(message)
                    if self.use_ui:
                        self.update_ui()
                    else:
                        self.update_console()
        except (websockets.ConnectionClosed, asyncio.TimeoutError, websockets.InvalidURI, OSError) as e:
            logging.error(f"WebSocket connection error: {e}. Unable to connect. Exiting...")
            sys.exit(1)

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

    def update_console(self):
        key = self.current_symbol.replace('-', '').upper()
        if key not in self.data:
            return

        data = self.data[key]
        self.clear_console()
        sys.stdout.write(f"Symbol: {data['symbol']}\n")
        sys.stdout.write(f"Price: {data['price']}\n")
        sys.stdout.write(f"Change: {data['change']}%\n")
        sys.stdout.write(f"Volume: {data['vol']}\n")
        sys.stdout.flush()

    def update_ui(self):
        key = self.current_symbol.replace('-', '').upper()
        if key not in self.data:
            return

        data = self.data[key]
        self.canvas.delete("all")
        self.canvas.create_text(200, 50, text=f"Symbol: {data['symbol']}", font=('Helvetica', 16))
        self.canvas.create_text(200, 80, text=f"Price: {data['price']}", font=('Helvetica', 16))
        self.canvas.create_text(200, 110, text=f"Change: {data['change']}%", font=('Helvetica', 16))
        self.canvas.create_text(200, 140, text=f"Volume: {data['vol']}", font=('Helvetica', 16))
        self.root.update()

    def toggle_symbol(self):
        self.current_symbol = next(self.cycle_symbols)
        self.ctr = 0
        logging.info(f"Switched to symbol: {self.current_symbol}")

    def run_ticker(self):
        if not self.use_ui:
            self.update_console()

    def run(self):
        SetInterval(self.refresh, self.toggle_symbol)
        SetInterval(1, self.run_ticker)
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.fetch_ticker_data())
        except KeyboardInterrupt:
            logging.info("Shutting down...")
            loop.stop()
        finally:
            if self.use_ui:
                self.root.destroy()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Binance Ticker Display")
    parser.add_argument('--ui', action='store_true', help="Display using a graphical UI")
    args = parser.parse_args()

    binance_socket = BinanceSocket(use_ui=args.ui)
    binance_socket.run()
