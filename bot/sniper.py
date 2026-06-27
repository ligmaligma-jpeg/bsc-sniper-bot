"""
BSC New Token Sniper Bot
Monitors PancakeSwap factory for new pairs, buys via the SniperBot contract.
Executes safety checks before each trade to avoid obvious rugs/honeypots.
"""
import json
import os
import sys
import time
from datetime import datetime
from web3 import Web3

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import *

# ── Constants ──────────────────────────────────
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
PCS_ROUTER_ADDR = Web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E")
PCS_FACTORY_ADDR = Web3.to_checksum_address("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73")
ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# ── ABI ────────────────────────────────────────
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"}]')
ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"type":"function"},{"constant":true,"inputs":[{"name":"","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"type":"function"}]')
FACTORY_ABI = json.loads('[{"constant":true,"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"allPairs","outputs":[{"internalType":"address","name":"","type":"address"}],"type":"function"},{"constant":true,"inputs":[],"name":"allPairsLength","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"type":"function"}]')
PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"type":"function"},{"constant":true,"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"type":"function"}]')
SNIPER_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amountIn","type":"uint256"}],"name":"buy","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"}],"name":"sell","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"}],"name":"withdrawProfit","outputs":[{"internalType":"uint256","name":"profit","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"withdrawAll","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"token","type":"address"}],"name":"getProfit","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]')


class SniperBot:
    """Monitors PancakeSwap for new token pairs and snipes them."""

    def __init__(self, w3, contract_address):
        self.w3 = w3
        self.account = w3.eth.account.from_key(PRIVATE_KEY)
        self.wallet = self.account.address
        
        self.factory = w3.eth.contract(address=PCS_FACTORY_ADDR, abi=FACTORY_ABI)
        self.router = w3.eth.contract(address=PCS_ROUTER_ADDR, abi=ROUTER_ABI)
        self.sniper = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=SNIPER_ABI)
        
        self.known_pair_count = self.factory.functions.allPairsLength().call()
        self.seen_pairs = set()
        self.positions = {}  # token_addr -> {symbol, entry_bnb, time}
        
        self.log(f"SniperBot initialized")
        self.log(f"Contract: {contract_address}")
        self.log(f"Known pairs: {self.known_pair_count}")

    def log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    def get_token_info(self, addr):
        try:
            t = self.w3.eth.contract(address=addr, abi=ERC20_ABI)
            sym = t.functions.symbol().call()
            dec = t.functions.decimals().call()
            return sym, dec
        except:
            return "???", 18

    def check_safety(self, token_addr) -> tuple:
        """Run safety checks: can we buy, sell, is there liquidity?"""
        try:
            # Check contract exists
            code = self.w3.eth.get_code(token_addr)
            if len(code) < 100:
                return False, "no/minimal bytecode"

            # Simulate buy: 0.001 BNB -> token
            amount = int(0.001 * 1e18)
            amounts_out = self.router.functions.getAmountsOut(amount, [WBNB, token_addr]).call()
            token_out = amounts_out[-1]
            if token_out == 0:
                return False, "zero buy output (no liquidity?)"

            # Check token isn't extremely diluted (> 1 quadrillion decimals worth)
            _, dec = self.get_token_info(token_addr)
            if dec > 18:
                max_tokens = 10**dec
                if token_out >= max_tokens:
                    return False, "suspicious token amount"

            # Simulate sell: half back
            sell_amount = token_out // 2
            if sell_amount == 0:
                return False, "zero sell amount"

            out2 = self.router.functions.getAmountsOut(sell_amount, [token_addr, WBNB]).call()
            if out2[-1] == 0:
                return False, "zero sell output (honeypot?)"

            return True, "ok"
        except Exception as e:
            return False, str(e)[:60]

    def check_new_pairs(self):
        """Poll allPairs() for new pairs since last check."""
        try:
            current_count = self.factory.functions.allPairsLength().call()
            if current_count <= self.known_pair_count:
                return []

            new_pairs = []
            for i in range(self.known_pair_count, current_count):
                try:
                    pair_addr = self.factory.functions.allPairs(i).call()
                    if pair_addr in self.seen_pairs or pair_addr == ZERO_ADDR:
                        continue
                    self.seen_pairs.add(pair_addr)

                    pc = self.w3.eth.contract(address=pair_addr, abi=PAIR_ABI)
                    t0 = pc.functions.token0().call()
                    t1 = pc.functions.token1().call()

                    new_pairs.append({"token0": t0, "token1": t1, "pair": pair_addr})
                    self.log(f"New pair #{i}: {pair_addr[:10]} ({t0[:10]}/{t1[:10]})")
                except:
                    pass

            self.known_pair_count = current_count
            return new_pairs
        except Exception as e:
            self.log(f"Poll error: {e}")
            return []

    def execute_buy(self, token_addr):
        """Call the contract's buy function."""
        try:
            nonce = self.w3.eth.get_transaction_count(self.wallet)
            tx = self.sniper.functions.buy(token_addr, int(TRADE_SIZE_BNB * 1e18)).build_transaction({
                "from": self.wallet,
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": int(self.w3.eth.gas_price * 1.1),
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.log(f"BUY TX: {tx_hash.hex()[:20]}...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return receipt["status"] == 1
        except Exception as e:
            self.log(f"BUY FAILED: {e}")
            return False

    def execute_sell(self, token_addr):
        """Call the contract's sell function."""
        try:
            nonce = self.w3.eth.get_transaction_count(self.wallet)
            tx = self.sniper.functions.sell(token_addr).build_transaction({
                "from": self.wallet,
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": int(self.w3.eth.gas_price * 1.1),
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.log(f"SELL TX: {tx_hash.hex()[:20]}...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return receipt["status"] == 1
        except Exception as e:
            self.log(f"SELL FAILED: {e}")
            return False

    def execute_withdraw(self, token_addr):
        """Withdraw profit from a token trade."""
        try:
            nonce = self.w3.eth.get_transaction_count(self.wallet)
            tx = self.sniper.functions.withdrawProfit(token_addr).build_transaction({
                "from": self.wallet,
                "nonce": nonce,
                "gas": 150000,
                "gasPrice": int(self.w3.eth.gas_price * 1.1),
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return receipt["status"] == 1
        except Exception as e:
            self.log(f"WITHDRAW FAILED: {e}")
            return False

    def check_positions(self):
        """Monitor open positions for profit/sell signals."""
        now = time.time()
        for addr in list(self.positions.keys()):
            pos = self.positions[addr]

            try:
                # Estimate current value
                token = self.w3.eth.contract(address=addr, abi=ERC20_ABI)
                bal = token.functions.balanceOf(self.sniper.address).call()
                if bal == 0:
                    self.log(f"{pos['symbol']}: no balance anymore")
                    del self.positions[addr]
                    continue

                out = self.router.functions.getAmountsOut(bal, [addr, WBNB]).call()
                current_bnb = out[-1] / 1e18
                entry_bnb = pos["entry_bnb"]
                mult = current_bnb / entry_bnb if entry_bnb > 0 else 0

                self.log(f"{pos['symbol']}: {mult:.2f}x (entry: {entry_bnb:.6f} BNB, now: {current_bnb:.6f} BNB)")

                # Take profit
                if entry_bnb > 0 and current_bnb >= entry_bnb * PROFIT_TARGET:
                    self.log(f"PROFIT! Selling {pos['symbol']} at {mult:.2f}x")
                    if self.execute_sell(addr):
                        self.execute_withdraw(addr)
                        del self.positions[addr]

                # Stop loss
                elif entry_bnb > 0 and current_bnb <= entry_bnb * STOP_LOSS:
                    self.log(f"STOP LOSS! Selling {pos['symbol']} at {mult:.2f}x")
                    if self.execute_sell(addr):
                        del self.positions[addr]

                # Time limit
                elif now - pos["time"] > MAX_HOLD_TIME:
                    self.log(f"TIME LIMIT! Selling {pos['symbol']} (held {(now - pos['time'])/60:.0f} min)")
                    if self.execute_sell(addr):
                        del self.positions[addr]

            except Exception as e:
                self.log(f"Check {pos['symbol']}: {e}")

    def deposit_bnb(self, amount_bnb):
        """Deposit BNB into the contract."""
        try:
            nonce = self.w3.eth.get_transaction_count(self.wallet)
            tx = self.sniper.functions.deposit().build_transaction({
                "from": self.wallet,
                "value": int(amount_bnb * 1e18),
                "nonce": nonce,
                "gas": 50000,
                "gasPrice": int(self.w3.eth.gas_price * 1.1),
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.log(f"Deposited {amount_bnb} BNB. TX: {tx_hash.hex()[:20]}...")
            self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            return True
        except Exception as e:
            self.log(f"Deposit failed: {e}")
            return False

    def run(self):
        """Main monitor loop."""
        bal = self.w3.eth.get_balance(self.wallet) / 1e18
        contract_bal = self.w3.eth.get_balance(self.sniper.address) / 1e18
        
        self.log("=" * 50)
        self.log("SNIPER BOT STARTED")
        self.log(f"Trade size: {TRADE_SIZE_BNB:.4f} BNB")
        self.log(f"Max positions: {MAX_SNIPES}")
        self.log(f"Profit target: {PROFIT_TARGET}x | Stop loss: {STOP_LOSS}x")
        self.log(f"Wallet: {bal:.6f} BNB | Contract: {contract_bal:.6f} BNB")
        self.log("=" * 50)

        cycle = 0
        while True:
            cycle += 1

            # Check new pairs
            pairs = self.check_new_pairs()
            for pair in pairs:
                # Determine which token is the new one (not WBNB)
                if pair["token0"] == WBNB:
                    token_addr = pair["token1"]
                elif pair["token1"] == WBNB:
                    token_addr = pair["token0"]
                else:
                    continue  # Not a BNB pair, skip

                if len(self.positions) >= MAX_SNIPES:
                    self.log(f"Max positions ({MAX_SNIPES}) reached, skipping {token_addr[:10]}")
                    continue

                sym, dec = self.get_token_info(token_addr)
                self.log(f"Token: {sym} ({token_addr[:10]}...)")

                safe, reason = self.check_safety(token_addr)
                if safe:
                    self.log(f"SAFE: {sym} — buying...")
                    if self.execute_buy(token_addr):
                        self.positions[token_addr] = {
                            "symbol": sym,
                            "entry_bnb": TRADE_SIZE_BNB,
                            "time": time.time(),
                        }
                        self.log(f"Position opened: {sym}")
                    else:
                        self.log(f"BUY FAILED for {sym}")
                else:
                    self.log(f"SKIP {sym}: {reason}")

            # Monitor existing positions
            if self.positions:
                self.check_positions()

            # Status
            bal = self.w3.eth.get_balance(self.wallet) / 1e18
            contract_bal = self.w3.eth.get_balance(self.sniper.address) / 1e18
            self.log(f"Cycle {cycle} | Wallet: {bal:.6f} | Contract: {contract_bal:.6f} | Positions: {len(self.positions)}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    import config
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))
    
    if not w3.is_connected():
        print("Cannot connect to BSC RPC")
        sys.exit(1)

    # Load deployed contract address
    deploy_path = os.path.join("..", "deploy", "deployed.json")
    if not os.path.exists(deploy_path):
        print(f"No deployed.json found. Deploy the contract first with deploy/deploy.py")
        sys.exit(1)
    
    with open(deploy_path) as f:
        deployed = json.load(f)
    contract_addr = deployed["contract_address"]

    bot = SniperBot(w3, contract_addr)
    bot.run()
