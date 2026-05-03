import ollama

# If you are running this on the 4GB Pi, change 'localhost' to the 8GB Pi's IP
# If you are running this ON the 8GB Pi, keep it 'localhost'
host_ip = 'localhost' 

client = ollama.Client(host=f'http://{host_ip}:11434')

def run_smart_analysis(user_input):
    print(f"Thinking (using llama3.2)...")
    
    response = client.chat(model='llama3.2', messages=[
        {
            'role': 'system',
            'content': 'You are a professional trading bot. Give concise, data-driven advice.'
        },
        {
            'role': 'user',
            'content': user_input,
        },
    ])
    return response['message']['content']

# Test it out
if __name__ == "__main__":
    prompt = "BTC RSI is 25 and it is at a major support level. What is the sentiment?"
    answer = run_smart_analysis(prompt)
    print(f"\nAnalysis: {answer}")
