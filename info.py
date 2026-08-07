import requests

def get_free_openrouter_models():
    url = "https://openrouter.ai/api/v1/models"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json().get("data", [])
        
        free_models = []
        for model in data:
            pricing = model.get("pricing", {})
            # Konversi aman ke float (menangani string angka atau desimal kecil)
            prompt_price = float(pricing.get("prompt", 1))
            completion_price = float(pricing.get("completion", 1))
            
            # Model dianggap gratis jika prompt dan completion harganya 0 atau mendekati 0
            if prompt_price == 0.0 and completion_price == 0.0:
                free_models.append({
                    "id": model.get("id"),
                    "name": model.get("name"),
                    "context_length": model.get("context_length")
                })
                
        return free_models
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

if __name__ == "__main__":
    free_list = get_free_openrouter_models()
    print(f"Found {len(free_list)} free models.")
    for m in free_list:
        print(f"- {m['id']} ({m['name']})")