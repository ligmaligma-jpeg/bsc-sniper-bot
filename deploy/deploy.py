"""
Deploy SniperBot contract to BSC.
"""
import json
import os
import sys
import subprocess

RPC_URL = "https://bsc-dataseed1.binance.org"
SOLC_VERSION = "0.8.26"

def main():
    from web3 import Web3

    private_key = os.environ.get("TRADER_PRIVATE_KEY")
    if not private_key:
        print("ERROR: Set TRADER_PRIVATE_KEY environment variable")
        print("  PowerShell: $env:TRADER_PRIVATE_KEY='your_private_key_here'")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("ERROR: Cannot connect to BSC")
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    addr = account.address
    balance = w3.eth.get_balance(addr) / 1e18

    print(f"Connected to BSC")
    print(f"Wallet: {addr}")
    print(f"Balance: {balance:.6f} BNB")

    if balance < 0.002:
        print(f"WARNING: Low balance. Deployment needs ~0.002 BNB.")
        proceed = input("Continue? (y/N): ")
        if proceed.lower() != "y":
            sys.exit(1)

    # Read contract
    script_dir = os.path.dirname(os.path.abspath(__file__))
    contract_path = os.path.join(script_dir, "..", "contracts", "SniperBot.sol")
    with open(contract_path) as f:
        source = f.read()

    print("\nCompiling...")
    result = subprocess.run(
        ["npx", f"solc@{SOLC_VERSION}", "--combined-json", "abi,bin", contract_path],
        capture_output=True, text=True, cwd=script_dir
    )
    if result.returncode != 0:
        print(f"Compilation failed: {result.stderr}")
        sys.exit(1)

    compiled = json.loads(result.stdout)
    contract_key = [k for k in compiled["contracts"].keys() if "SniperBot" in k][0]
    contract_data = compiled["contracts"][contract_key]

    bytecode = "0x" + contract_data["bin"]
    abi = contract_data["abi"]

    print("Deploying...")
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    gas_estimate = Contract.constructor().estimate_gas({"from": addr})
    gas_price = w3.eth.gas_price
    deploy_cost = gas_estimate * gas_price / 1e18

    print(f"  Gas estimate: {gas_estimate:,}")
    print(f"  Est. cost: {deploy_cost:.6f} BNB")

    tx = Contract.constructor().build_transaction({
        "from": addr,
        "nonce": w3.eth.get_transaction_count(addr),
        "gas": gas_estimate + 50000,
        "gasPrice": max(gas_price, int(3 * 1e9)),
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"\nTX sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] == 1:
        contract_addr = receipt["contractAddress"]
        print(f"\nCONTRACT DEPLOYED: {contract_addr}")
        print(f"https://bscscan.com/address/{contract_addr}")

        deployed = {
            "contract_address": contract_addr,
            "deploy_tx": tx_hash.hex(),
            "deploy_block": receipt["blockNumber"],
            "chain_id": w3.eth.chain_id,
            "abi": abi,
        }
        output_path = os.path.join(script_dir, "deployed.json")
        with open(output_path, "w") as f:
            json.dump(deployed, f, indent=2)
        print(f"Saved to {output_path}")
    else:
        print("DEPLOYMENT FAILED")

if __name__ == "__main__":
    main()
