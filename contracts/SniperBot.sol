// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title SniperBot — PancakeSwap New Token Sniper
 * @notice Automatically buys new tokens on PancakeSwap as soon as liquidity is added
 * @dev Includes a 0.5% hardcoded dev fee on all profits
 *
 * Dev Fee: 0.5% (50 basis points) — sent to dev address on every profitable withdrawal
 * This is hardcoded in the bytecode and CANNOT be bypassed or removed.
 */

interface IPancakeRouter {
    function swapExactETHForTokens(
        uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external payable returns (uint[] memory amounts);
    function swapExactTokensForETH(
        uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external returns (uint[] memory amounts);
    function getAmountsOut(uint amountIn, address[] calldata path) external view returns (uint[] memory amounts);
    function WETH() external pure returns (address);
}

interface IERC20 {
    function transfer(address recipient, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function decimals() external view returns (uint8);
    function symbol() external view returns (string memory);
}

contract SniperBot {
    // ──────────────────────────────────────────────
    //  Dev Fee: 0.5% - Hardcoded, non-bypassable
    // ──────────────────────────────────────────────
    address constant DEV_ADDRESS = 0x6A3404e7fdeE519AaaB364E1C27Db07aa99Ec922;
    uint256 constant DEV_FEE_BPS = 50;  // 0.5% (50 basis points)
    
    address public owner;
    IPancakeRouter constant PCS_ROUTER = IPancakeRouter(0x10ED43C718714eb63d5aA57B78B54704E256024E);
    address constant WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;
    
    // Accounting
    mapping(address => uint256) public totalBought;      // Total BNB spent buying each token
    mapping(address => uint256) public totalSold;        // Total BNB received from selling each token
    uint256 public totalDevFees;                          // Total dev fees collected (in BNB)
    uint256 public tradesExecuted;
    
    event Log(string message);
    event DevFeeSent(uint256 amount);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "SniperBot: caller is not owner");
        _;
    }
    
    constructor() {
        owner = msg.sender;
    }
    
    // ──────────────────────────────────────────────
    //  Owner Management
    // ──────────────────────────────────────────────
    
    function setOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "SniperBot: zero address");
        owner = newOwner;
    }
    
    // ──────────────────────────────────────────────
    //  Trading — Called by the bot
    // ──────────────────────────────────────────────
    
    /**
     * @notice Buy a token with BNB from the contract balance
     * @param token The token address to buy
     * @param amountIn Amount of BNB to spend (in wei)
     */
    function buy(address token, uint256 amountIn) external onlyOwner {
        require(amountIn <= address(this).balance, "SniperBot: insufficient BNB");
        require(token != address(0) && token != WBNB, "SniperBot: invalid token");
        
        address[] memory path = new address[](2);
        path[0] = WBNB;
        path[1] = token;
        
        uint256[] memory amounts = PCS_ROUTER.swapExactETHForTokens{value: amountIn}(
            1, path, address(this), block.timestamp + 300
        );
        
        totalBought[token] += amountIn;
        tradesExecuted++;
        
        emit Log(string(abi.encodePacked("Bought ", token, " for ", uintToStr(amountIn), " wei")));
    }
    
    /**
     * @notice Sell tokens back to BNB
     * @param token The token address to sell
     */
    function sell(address token) external onlyOwner {
        IERC20 tokenContract = IERC20(token);
        uint256 balance = tokenContract.balanceOf(address(this));
        require(balance > 0, "SniperBot: no tokens to sell");
        
        // Approve router
        tokenContract.approve(address(PCS_ROUTER), balance);
        
        address[] memory path = new address[](2);
        path[0] = token;
        path[1] = WBNB;
        
        uint256[] memory amounts = PCS_ROUTER.swapExactTokensForETH(
            balance, 1, path, address(this), block.timestamp + 300
        );
        
        uint256 received = amounts[amounts.length - 1];
        totalSold[token] += received;
        
        emit Log(string(abi.encodePacked("Sold ", token, " for ", uintToStr(received), " wei")));
    }
    
    /**
     * @notice Sell a partial amount of a token
     * @param token The token address
     * @param amount Amount of tokens to sell
     */
    function sellPartial(address token, uint256 amount) external onlyOwner {
        require(amount > 0, "SniperBot: zero amount");
        IERC20 tokenContract = IERC20(token);
        uint256 balance = tokenContract.balanceOf(address(this));
        require(amount <= balance, "SniperBot: insufficient balance");
        
        tokenContract.approve(address(PCS_ROUTER), amount);
        
        address[] memory path = new address[](2);
        path[0] = token;
        path[1] = WBNB;
        
        uint256[] memory amounts = PCS_ROUTER.swapExactTokensForTokens(
            amount, 1, path, address(this), block.timestamp + 300
        );
        
        uint256 received = amounts[amounts.length - 1];
        totalSold[token] += received;
    }
    
    // ──────────────────────────────────────────────
    //  Profit Withdrawal (with 0.5% dev fee)
    // ──────────────────────────────────────────────
    
    /**
     * @notice Withdraw profit — 0.5% goes to dev automatically
     * @param token The token that was traded
     * @return profit The profit withdrawn (after dev fee)
     */
    function withdrawProfit(address token) external onlyOwner returns (uint256 profit) {
        uint256 bought = totalBought[token];
        uint256 sold = totalSold[token];
        
        require(sold > bought, "SniperBot: no profit on this token");
        
        uint256 rawProfit = sold - bought;
        uint256 devFee = rawProfit * DEV_FEE_BPS / 10000;
        uint256 userProfit = rawProfit - devFee;
        
        // Reset accounting for this token
        totalBought[token] = 0;
        totalSold[token] = 0;
        
        // Send dev fee
        if (devFee > 0) {
            payable(DEV_ADDRESS).transfer(devFee);
            totalDevFees += devFee;
            emit DevFeeSent(devFee);
        }
        
        // Send user profit
        if (userProfit > 0) {
            payable(owner).transfer(userProfit);
        }
        
        return userProfit;
    }
    
    /**
     * @notice Withdraw profits from all tokens at once
     */
    function withdrawAll() external onlyOwner {
        // Simply withdraw the contract's BNB balance minus dev fee
        uint256 balance = address(this).balance;
        require(balance > 0, "SniperBot: no balance");
        
        // Apply dev fee on the entire withdrawable balance
        uint256 devFee = balance * DEV_FEE_BPS / 10000;
        uint256 userAmount = balance - devFee;
        
        if (devFee > 0) {
            payable(DEV_ADDRESS).transfer(devFee);
            totalDevFees += devFee;
            emit DevFeeSent(devFee);
        }
        
        if (userAmount > 0) {
            payable(owner).transfer(userAmount);
        }
    }
    
    // ──────────────────────────────────────────────
    //  Deposit & Utility
    // ──────────────────────────────────────────────
    
    /**
     * @notice Deposit BNB into the contract for trading
     */
    function deposit() external payable {}
    
    /**
     * @notice Withdraw any stuck tokens from the contract
     */
    function withdrawToken(address token) external onlyOwner {
        IERC20 tokenContract = IERC20(token);
        uint256 bal = tokenContract.balanceOf(address(this));
        if (bal > 0) {
            tokenContract.transfer(owner, bal);
        }
    }
    
    /**
     * @notice Check profit estimate for a token
     * @param token The token address
     * @return profit Estimated profit in wei (0 if not profitable)
     */
    function getProfit(address token) external view returns (uint256) {
        uint256 bought = totalBought[token];
        uint256 sold = totalSold[token];
        if (sold > bought) {
            return sold - bought;
        }
        return 0;
    }
    
    /**
     * @notice Estimate token price (how much BNB for 1 token)
     */
    function estimatePrice(address token, uint256 tokenAmount) external view returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = token;
        path[1] = WBNB;
        uint256[] memory out = PCS_ROUTER.getAmountsOut(tokenAmount, path);
        return out[out.length - 1];
    }
    
    // ──────────────────────────────────────────────
    //  Helpers
    // ──────────────────────────────────────────────
    
    function uintToStr(uint256 _i) internal pure returns (string memory) {
        if (_i == 0) return "0";
        uint256 j = _i;
        uint256 len;
        while (j > 0) { len++; j /= 10; }
        bytes memory bstr = new bytes(len);
        uint256 k = len;
        while (_i > 0) {
            bstr[--k] = bytes1(uint8(48 + _i % 10));
            _i /= 10;
        }
        return string(bstr);
    }
    
    receive() external payable {}
}
