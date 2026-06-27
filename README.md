# BSC Sniper Bot — PancakeSwap New Token Sniper

Automatically detects and buys new tokens as they list on PancakeSwap V2. Includes safety checks to avoid rugs.

**Dev Fee:** 0.5% on profits — hardcoded in the contract, sent to dev automatically.

## How It Works

1. **Monitor** — Polls PancakeSwap factory for new pair creations
2. **Safety check** — Simulates buy + sell to detect honeypots
3. **Buy** — Calls the SniperBot contract to purchase with BNB
4. **Manage** — Takes profit at target, cuts losses, enforces time limit
5. **Fee** — 0.5% of profit → dev wallet, 99.5% → you

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your private key

# Deploy the contract
cd deploy
export TRADER_PRIVATE_KEY="your_key"
python deploy.py

# Start sniping
cd ../bot
python sniper.py
```

## Dev Fee Address

`0x6A3404e7fdeE519AaaB364E1C27Db07aa99Ec922`

The 0.5% dev fee is **hardcoded in the Solidity contract** — it cannot be bypassed or removed without changing the bytecode.

## Safety Notes

- Start with `DRY_RUN=true` in config
- Use a dedicated wallet with limited funds
- Most new tokens are scams — safety checks help but aren't foolproof
- Test on testnet first

## Support

If you find this tool useful, consider supporting the project:

- 🌿 **Grass** — Earn passive income by sharing unused bandwidth: [Register here](https://app.grass.io/register?referralCode=WeMGAjVJGpVUO5U)

## Requirements

- Python 3.10+
- Node.js 18+ (for solc compiler)
- BNB for gas fees
