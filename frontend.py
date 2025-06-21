# frontend.py

import streamlit as st
import httpx # Used to make HTTP requests to your FastAPI backend
import asyncio # For running async code in Streamlit (Streamlit doesn't natively run async functions directly)

# --- Configuration for your FastAPI Backend ---
FASTAPI_BASE_URL = "http://127.0.0.1:8000" # Your FastAPI app's URL

# --- Async function to call your FastAPI /route endpoint ---
async def get_routing_recommendation(transaction_type: str, amount_usd: float, user_preference: str):
    url = f"{FASTAPI_BASE_URL}/route"
    payload = {
        "transaction_type": transaction_type,
        "amount_usd": amount_usd,
        "user_preference": user_preference
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=10) # Add a timeout
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except httpx.RequestError as e:
            st.error(f"Network error communicating with backend: {e}")
            return None
        except httpx.HTTPStatusError as e:
            st.error(f"Backend returned an error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            return None

# --- Streamlit UI Layout ---
st.set_page_config(
    page_title="Nexus Router",
    page_icon="🔗",
    layout="centered"
)

st.title("🔗 Nexus Router: Your Intelligent Cross-Chain Guide")
st.write("Find the optimal blockchain for your transaction based on real-time data.")

# --- User Input Form ---
with st.form("routing_form"):
    st.subheader("Your Transaction Details")

    transaction_type = st.selectbox(
        "Transaction Type:",
        ["simple_transfer", "token_swap", "nft_mint"], # Example types
        index=0,
        help="Select the type of blockchain transaction you plan to make."
    )

    amount_usd = st.number_input(
        "Estimated Transaction Value (USD):",
        min_value=1.0,
        value=100.0,
        step=10.0,
        help="Estimate the USD value of your transaction. This helps in comparing costs."
    )

    user_preference = st.radio(
        "Prioritize:",
        ["cheapest", "fastest"],
        index=0,
        help="Do you prefer the lowest transaction cost or the quickest confirmation time?"
    )

    submit_button = st.form_submit_button("Find Optimal Chain")

# --- Display Recommendation ---
if submit_button:
    st.subheader("Nexus's Recommendation:")

    with st.spinner("Analyzing blockchain networks..."):
        # Run the async function using asyncio
        # Streamlit runs synchronous code, so we need to manage async calls
        recommendation_data = asyncio.run(
            get_routing_recommendation(transaction_type, amount_usd, user_preference)
        )

    if recommendation_data:
        rec = recommendation_data.get("recommendation")
        all_metrics = recommendation_data.get("all_chains_metrics", [])

        if rec:
            st.success(f"**Optimal Chain: {rec['chain']}**")
            st.write(f"Reason: {rec['reason']}")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    label="Estimated Gas Fee (USD)",
                    value=f"${rec['details']['estimated_gas_fee_usd']:.4f}" if rec['details']['estimated_gas_fee_usd'] != "N/A" else "N/A"
                )
            with col2:
                st.metric(
                    label="Estimated Time (Seconds)",
                    value=f"{rec['details']['estimated_time_seconds']:.1f}s"
                )
            with col3:
                st.metric(
                    label="Native Token Price (USD)",
                    value=f"${rec['details']['native_token_price_usd']:.2f}" if rec['details']['native_token_price_usd'] else "N/A"
                )

            st.info(f"Current Gas Price on {rec['chain']}: {rec['details']['current_gas_price_gwei']:.2f} Gwei")

            st.markdown("---")
            st.subheader("Comparison Across Chains:")
            st.markdown("---")
            # NEW: Display AI Explanation
            ai_explanation = rec.get("ai_explanation")
            if ai_explanation:
                st.subheader("Why Nexus Made This Recommendation:")
                st.markdown(ai_explanation) # Use markdown to render potential formatting
            else:
                st.info("No AI explanation available.")

            st.markdown("---")
            st.subheader("Comparison Across Chains:")

            # Prepare data for display
            display_data = []
            for m in all_metrics:
                display_data.append({
                    "Chain": m["chain"],
                    "Est. Gas (USD)": f"${m['estimated_fee_usd']:.4f}" if m['estimated_fee_usd'] != "N/A" else "N/A",
                    "Est. Time (s)": f"{m['avg_block_time_seconds']:.1f}"
                })

            st.dataframe(display_data, use_container_width=True)

        else:
            st.warning("No specific recommendation could be generated.")
    else:
        st.error("Failed to get a recommendation from the backend. Please check the backend server.")

st.markdown("---")
st.caption(f"Backend API URL: `{FASTAPI_BASE_URL}`. Ensure your FastAPI server is running!")
