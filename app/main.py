# main.py

"""
Nexus Router: Backend API for intelligent cross-chain transaction routing.
This module provides endpoints for fetching real-time blockchain data
and eventually for routing transactions.
"""

# Standard library imports
import os
import httpx # NEW: Import httpx for async HTTP requests
import google.generativeai as genai # NEW: For Google Gemini API
import asyncio
# Third-party imports (ordered as per PEP 8 suggestion)
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException # NEW: Import HTTPException for errors
from web3 import Web3
from web3.exceptions import Web3Exception # Specific exception for Web3 errors
LI_FI_API_BASE_URL = "https://li.quest/v1" # This is LI.FI's main API base URL
# Load environment variables from .env file at the very start
load_dotenv()
LI_FI_API_KEY = os.getenv("LI_FI_API_KEY")
# In main.py
# Add a new dictionary for common token addresses on different chains
COMMON_TOKEN_ADDRESSES = {
    "USDC": {
        "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "polygon": "0x2791Bca1f2de4661ED88A30C99A7a9226CfF4794",
        "optimism": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
        "bsc": "0x8AC76a51cc950d9822D68b83FdcBc032e4cD7a3d" # BUSD or USDC as relevant
    }
}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not found in .env. Generative AI explanations will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
# --- FastAPI App Instance ---
app = FastAPI()

# --- NEW: Centralized Chain Configuration ---
# This dictionary will hold all static and dynamic info needed for each chain.
# Replace placeholder URLs with your actual RPC URLs from .env
COINGECKO_API_BASE_URL = "https://api.coingecko.com/api/v3"
# Mapping of native token symbols to CoinGecko IDs
# You might need to look up CoinGecko IDs if they're different from the symbol
COINGECKO_TOKEN_MAP = {
    "ETH": "ethereum",
    "MATIC": "matic-network", # CoinGecko ID for Polygon's MATIC
    "AVAX": "avalanche-2", 
     "BNB": "binancecoin",# CoinGecko ID for Avalanche's AVAX
    # Add more if you expand chains
}
async def get_token_prices_usd(token_symbols: list[str]) -> dict:
    """
    Fetches the current USD prices for a list of token symbols from CoinGecko.
    Returns a dictionary mapping token symbol to its USD price.
    """
    coingecko_ids = [COINGECKO_TOKEN_MAP[s] for s in token_symbols if s in COINGECKO_TOKEN_MAP]
    if not coingecko_ids:
        return {}

    ids_string = ",".join(coingecko_ids)
    params = {
        "ids": ids_string,
        "vs_currencies": "usd"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{COINGECKO_API_BASE_URL}/simple/price", params=params, timeout=5)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            data = response.json()

            prices = {}
            for symbol in token_symbols:
                coingecko_id = COINGECKO_TOKEN_MAP.get(symbol)
                if coingecko_id and coingecko_id in data and "usd" in data[coingecko_id]:
                    prices[symbol] = data[coingecko_id]["usd"]
                else:
                    print(f"WARNING: Could not fetch price for {symbol} (CoinGecko ID: {coingecko_id})")
                    prices[symbol] = None # Indicate that price couldn't be fetched
            return prices
        except httpx.RequestError as e:
            print(f"Error fetching prices from CoinGecko (RequestError): {e}")
            return {symbol: None for symbol in token_symbols} # Return None for all if request fails
        except Exception as e:
            print(f"An unexpected error occurred while fetching prices: {e}")
            return {symbol: None for symbol in token_symbols}
        
CHAIN_CONFIGS = {
    "ethereum": {
        "display_name": "Ethereum Mainnet",
        "rpc_url_env_var": "ETHEREUM_RPC_URL",
        "avg_block_time_seconds": 13, # Approx. average block time for Ethereum
        "native_token_symbol": "ETH",
        "chain_id":1,
        "explorer_url": "https://etherscan.io/"
    },
    "polygon": {
        "display_name": "Polygon Mainnet",
        "rpc_url_env_var": "POLYGON_RPC_URL",
        "avg_block_time_seconds": 2.2, # Approx. average block time for Polygon
        "native_token_symbol": "MATIC",
        "chain_id":137,
        "explorer_url": "https://polygonscan.com/"
    },
    # --- NEW: Avalanche C-Chain (EVM Compatible - uses web3.py) ---
    "avalanche": {
        "display_name": "Avalanche C-Chain",
        "rpc_url_env_var": "AVALANCHE_RPC_URL", # You'll need to get this URL from Alchemy/Infura/QuickNode
        "avg_block_time_seconds": 2.0, # Approx. average block time for Avalanche C-Chain
        "native_token_symbol": "AVAX",
        "chain_id":43114,
        "explorer_url": "https://snowtrace.io/" # Or https://avascan.info/
    },
    # --- CONCEPTUAL PLACEHOLDER: Bitcoin (NOT EVM Compatible) ---
    # This entry won't work with web3.py. It would require a different library
    # like python-bitcoinrpc or a dedicated Bitcoin API.
    "bitcoin": {
        "display_name": "Bitcoin",
        "rpc_url_env_var": "BITCOIN_RPC_URL", # This URL would point to a Bitcoin node or a Bitcoin API
        "avg_block_time_seconds": 600, # Fixed average block time: 10 minutes
        "native_token_symbol": "BTC",
        "explorer_url": "https://blockchain.com/explorer"
        # "web3_compatible": False # Add a flag to indicate it's not web3.py compatible
    },
    # --- CONCEPTUAL PLACEHOLDER: Solana (NOT EVM Compatible) ---
    # This entry won't work with web3.py. It would require the solana.py library
    # and a dedicated Solana RPC endpoint.
    "solana": {
        "display_name": "Solana",
        "rpc_url_env_var": "SOLANA_RPC_URL", # This URL would point to a Solana RPC endpoint
        "avg_block_time_seconds": 0.4, # Very fast average block time
        "native_token_symbol": "SOL",
        "explorer_url": "https://solscan.io/"
        # "web3_compatible": False
    },
    "optimism": {
        "display_name": "Optimism Mainnet",
        "rpc_url_env_var": "OPTIMISM_RPC_URL", # Environment variable for Optimism RPC URL
        "avg_block_time_seconds": 0.5, # Approximate average block time (very fast Layer 2)
        "native_token_symbol": "ETH",
        "chain_id":10,# Optimism uses ETH as its native gas token
        "explorer_url": "https://optimistic.etherscan.io/"
    },
    "bsc": { # Binance Smart Chain (often abbreviated as BSC, or BNB Chain)
        "display_name": "BNB Smart Chain",
        "rpc_url_env_var": "BSC_RPC_URL", # Environment variable for BSC RPC URL
        "avg_block_time_seconds": 3.0, # Approximate average block time
        "native_token_symbol": "BNB",
        "chain_id":56,# BNB is the native token for gas
        "explorer_url": "https://bscscan.com/"
    },
    # Add more chains here as you expand!
    # "arbitrum": {
    #     "display_name": "Arbitrum One",
    #     "rpc_url_env_var": "ARBITRUM_RPC_URL", # Make sure you have this in .env
    #     "avg_block_time_seconds": 0.25, # Approx.
    #     "native_token_symbol": "ETH",
    #     "explorer_url": "https://arbiscan.io/"
    # }
}

# --- NEW: Dictionary to store initialized Web3 instances ---
# We'll initialize these once when the app starts
w3_clients = {}

# Initialize Web3 clients for each configured chain
for chain_name, config in CHAIN_CONFIGS.items():
    rpc_url = os.getenv(config["rpc_url_env_var"])
    if rpc_url:
        try:
            w3_clients[chain_name] = Web3(Web3.HTTPProvider(rpc_url))
            # Optional: Check connection immediately
            if not w3_clients[chain_name].is_connected():
                print(f"WARNING: Could not connect to {config['display_name']} RPC at {rpc_url}")
                w3_clients[chain_name] = None # Set to None if connection fails
        except Exception as e:
            print(f"ERROR: Failed to initialize Web3 for {config['display_name']}: {e}")
            w3_clients[chain_name] = None
    else:
        print(f"WARNING: RPC URL for {config['display_name']} not found in .env")
        w3_clients[chain_name] = None

# --- Existing Routes ---
@app.get("/")
async def read_root():
    """
    This function handles GET requests to the root URL (/)
    and returns a welcome message.
    """
    return {"message": "Welcome to Nexus! Your intelligent cross-chain router is starting..."}

@app.get("/status")
async def get_status():
    """
    This function handles GET requests to the /status URL
    and returns the application's status.
    """
    return {"status": "operational", "version": "0.1.0"}

# --- NEW: Unified Endpoint to get Real-Time Chain Metrics ---
@app.get("/chain_metrics/{chain_name}")
async def generate_explanation(request_data: dict, recommendation_data: dict, all_chains_metrics: list[dict]) -> str:
    """
    Generates a natural language explanation for the routing decision
    using a generative AI model.
    """
    if not GEMINI_API_KEY:
        return "Generative AI explanation is not available (API key missing)."

    model = genai.GenerativeModel('gemini-2.0-flash') # Using gemini-pro model

    # Craft a detailed prompt based on the request and recommendation
    prompt = (
        "You are an expert blockchain financial advisor for a personal finance app called 'Mango Web App'. "
        "Your task is to explain a blockchain routing recommendation in a clear, concise, and helpful way. "
        "Highlight why the recommended chain was chosen based on the user's preference and current market data. "
        "Also, briefly mention how other considered chains compare. "
        "Keep the tone professional yet easy to understand for someone managing their finances. "
        "Do not include disclaimers about 'not financial advice'. Focus on the explanation. "
        f"\n\nUser Request: {request_data}"
        f"\nRecommended Chain: {recommendation_data['chain']} (Reason: {recommendation_data['reason']})"
        f"\nRecommended Chain Details: {recommendation_data['details']}"
        f"\nMetrics for all considered chains: {all_chains_metrics}"
        "\n\nBased on this information, provide a concise explanation (max 150 words):"
    )

    try:
        # Running synchronous API call in an async context
        # Use `await asyncio.to_thread` if you encounter performance issues with many sync calls
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except Exception as e:
        print(f"Error generating AI explanation: {e}")
        return f"Could not generate AI explanation: {str(e)}"
async def get_chain_metrics(chain_name: str):
    """
    Fetches real-time metrics (like gas price) and static properties
    for a given blockchain.
    """
    chain_name_lower = chain_name.lower()
    config = CHAIN_CONFIGS.get(chain_name_lower)
    w3 = w3_clients.get(chain_name_lower)

    if not config:
        raise HTTPException(status_code=404, detail=f"Chain '{chain_name}' not supported.")
    if not w3 or not w3.is_connected():
        raise HTTPException(status_code=503, detail=f"RPC for {config['display_name']} not connected or URL not set correctly.")

    try:
        gas_price_wei = w3.eth.gas_price
        gas_price_gwei = w3.from_wei(gas_price_wei, 'gwei')

        return {
            "chain": config["display_name"],
            "native_token_symbol": config["native_token_symbol"],
            "gas_price_wei": gas_price_wei,
            "gas_price_gwei": float(f"{gas_price_gwei:.2f}"),
            "avg_block_time_seconds": config["avg_block_time_seconds"], # This is a static property
            "explorer_url": config["explorer_url"]
        }
    except Web3Exception as e:
        raise HTTPException(status_code=500, detail=f"Web3 error fetching metrics for {config['display_name']}: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while fetching metrics for {config['display_name']}: {str(e)}")

# --- NEW: Import Pydantic for input validation ---
from pydantic import BaseModel, Field # NEW

# Define the structure of a routing request
class RouteRequest(BaseModel):
    transaction_type: str = Field(..., example="simple_transfer", description="Type of transaction (e.g., 'simple_transfer', 'token_swap')")
    amount_usd: float = Field(..., gt=0, example=100.0, description="Estimated USD value of the transaction for relative cost calculation")
    user_preference: str = Field("cheapest", example="cheapest", description="User's preference: 'cheapest' or 'fastest'")
    # For MVP, we assume current chain has the token, and target is just any chain.
    # Later, we can add source_token, target_token, etc.

# --- NEW: Endpoint for Intelligent Routing ---
@app.post("/route")
async def route_transaction(request: RouteRequest):
    """
    Analyzes different blockchains to recommend the optimal one
    based on user preferences and current network conditions,
    now with USD cost estimation.
    """
    # Collect all unique native token symbols from CHAIN_CONFIGS
    native_token_symbols_to_fetch = list(set(
        config["native_token_symbol"] for config in CHAIN_CONFIGS.values()
    ))

    # Fetch token prices concurrently at the start of the routing request
    token_prices_usd = await get_token_prices_usd(native_token_symbols_to_fetch)

    if not token_prices_usd:
        # This is a critical failure for USD cost comparison
        raise HTTPException(status_code=500, detail="Failed to fetch real-time token prices. Cannot perform cost comparison.")

    chain_metrics = []
    for chain_name, config in CHAIN_CONFIGS.items():
        try:
            metrics = await get_chain_metrics(chain_name)

            # --- NEW: Calculate Estimated Fee in USD ---
            native_token_symbol = config["native_token_symbol"]
            native_token_price_usd = token_prices_usd.get(native_token_symbol)

            if native_token_price_usd is None:
                print(f"WARNING: Skipping {config['display_name']} for cost comparison as {native_token_symbol} price not available.")
                # If price is missing, this chain can't be part of 'cheapest' calculation
                metrics["estimated_fee_usd"] = float('inf') # Set to infinity so it's not chosen as cheapest
                metrics["estimated_fee_gwei"] = metrics["gas_price_gwei"] * 21000 # Still calculate gwei
                metrics["native_token_price_usd"] = None
            else:
                estimated_fee_gwei = metrics["gas_price_gwei"] * 21000 # Example gas limit for simple transfer
                estimated_fee_usd = (estimated_fee_gwei / 1_000_000_000) * native_token_price_usd # Gwei to native token unit, then to USD

                metrics["estimated_fee_gwei"] = estimated_fee_gwei
                metrics["estimated_fee_usd"] = estimated_fee_usd
                metrics["native_token_price_usd"] = native_token_price_usd

            chain_metrics.append(metrics)
        except HTTPException as e:
            print(f"Skipping {config['display_name']} due to error: {e.detail}")
            pass # Skip chains that fail to connect/fetch metrics

    if not chain_metrics:
        raise HTTPException(status_code=500, detail="Could not fetch metrics for any supported chain.")

    # --- Refined Routing Logic ---
    optimal_chain = None
    if request.user_preference == "cheapest":
        # Now, compare based on estimated_fee_usd
        # Filter out chains where price wasn't available (estimated_fee_usd is inf)
        comparable_chains = [c for c in chain_metrics if c["estimated_fee_usd"] != float('inf')]
        if not comparable_chains:
            raise HTTPException(status_code=500, detail="No chains available for cost comparison (token prices missing).")
        optimal_chain = min(comparable_chains, key=lambda x: x["estimated_fee_usd"])

    elif request.user_preference == "fastest":
        optimal_chain = min(chain_metrics, key=lambda x: x["avg_block_time_seconds"])
    else:
        raise HTTPException(status_code=400, detail="Invalid user preference. Choose 'cheapest' or 'fastest'.")

    if not optimal_chain:
        raise HTTPException(status_code=500, detail="Could not determine an optimal chain.")
    ai_explanation = await generate_explanation(
    request.dict(), # Pass the request data
    {
        "chain": optimal_chain["chain"],
        "reason": f"Based on your preference for the {request.user_preference} transaction, "
                  f"{optimal_chain['chain']} was chosen.",
        "details": {
            "estimated_gas_fee_gwei": float(f"{optimal_chain['estimated_fee_gwei']:.2f}"),
            "estimated_gas_fee_usd": float(f"{optimal_chain['estimated_fee_usd']:.4f}") if optimal_chain['estimated_fee_usd'] != float('inf') else "N/A",
            "estimated_time_seconds": optimal_chain["avg_block_time_seconds"],
            "native_token": optimal_chain["native_token_symbol"],
            "current_gas_price_gwei": optimal_chain["gas_price_gwei"],
            "native_token_price_usd": optimal_chain.get("native_token_price_usd")
        }
    },
    [
        {
            "chain": m["chain"],
            "estimated_gas_fee_gwei": float(f"{m['estimated_fee_gwei']:.2f}"),
            "estimated_fee_usd": float(f"{m['estimated_fee_usd']:.4f}") if m['estimated_fee_usd'] != float('inf') else "N/A",
            "avg_block_time_seconds": m["avg_block_time_seconds"]
        } for m in chain_metrics
    ]
)

    return {
        "request": request.dict(),
        "recommendation": {
            "chain": optimal_chain["chain"],
            "reason": (f"Based on your preference for the {request.user_preference} transaction, "
                       f"{optimal_chain['chain']} was chosen."),
            "details": {
                "estimated_gas_fee_gwei": float(f"{optimal_chain['estimated_fee_gwei']:.2f}"),
                "estimated_gas_fee_usd": float(f"{optimal_chain['estimated_fee_usd']:.4f}") if optimal_chain['estimated_fee_usd'] != float('inf') else "N/A",
                "estimated_time_seconds": optimal_chain["avg_block_time_seconds"],
                "native_token": optimal_chain["native_token_symbol"],
                "current_gas_price_gwei": optimal_chain["gas_price_gwei"],
                "native_token_price_usd": optimal_chain.get("native_token_price_usd") # Add price for context
            }, "ai_explanation": ai_explanation # NEW: Add the AI explanation here
        }, 
        "all_chains_metrics": [
            {
                "chain": m["chain"],
                "estimated_gas_fee_gwei": float(f"{m['estimated_fee_gwei']:.2f}"),
                "estimated_fee_usd": float(f"{m['estimated_fee_usd']:.4f}") if m['estimated_fee_usd'] != float('inf') else "N/A",
                "avg_block_time_seconds": m["avg_block_time_seconds"]
            } for m in chain_metrics
        ]
    }
