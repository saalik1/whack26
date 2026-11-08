from openai import OpenAI

# Initialize the DeepSeek client with your API key hardcoded here:
client = OpenAI(
    api_key="sk-ce9f7f450bda463799e079f055f1a987",  # <--- Paste your key right here
    base_url="https://api.deepseek.com",            # DeepSeek API endpoint
)

def explain_ai_verdict(game_state: dict, careful_result: dict, naive_result: dict, offer_type: str) -> str:
    """
    Sends the current round context and AI outcomes to DeepSeek to generate
    a friendly, educational explanation of why the AIs responded the way they did.
    """
    
    prompt = f"""
    You are the Careful AI (Popper), a rigorous, skeptical data scientist running statistical verification for this retail shop using e-values and baseline modeling.

    Here is what just happened in this hour:
    - Current Time/Date: Sunday, November 8, 2026.
    - Player's Move: {offer_type.upper()} ("good" is a genuine +8% lift, "bad" is a useless 0% trap).
    - Environment: Weather is {game_state.get('weather')} ({game_state.get('temperature_c')}°C), Event active: {game_state.get('event') or 'None'}.
    - Customer Count: {game_state.get('customers_now')} customers (My baseline expected {game_state.get('forecast', {}).get('expected')}).
    
    Your Verdict: {careful_result.get('verdict')} - "{careful_result.get('text')}" (E-value: {careful_result.get('evidence', 1.0)})

    Task:
    In max 2 sentences, speak in first-person as the Careful AI (Popper). Explain why you gave this verdict by analyzing the environment, weather/events, and your accumulating e-values or baseline expectations. Keep it sharp and witty.
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # You can also use "deepseek-reasoner" for R1 thinking traces
            messages=[
                {"role": "system", "content": "You are a witty data science assistant explaining statistical decision-making in a shop game."},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"DeepSeek explanation currently unavailable: {str(e)}"