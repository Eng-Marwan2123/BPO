import requests 
import pandas as pd 

Url = "http://localhost:8000" 



endpoint = "/api/v1/surveys" 
 



limit = 500 
offset = 0 
while True: 
    request = requests.get(Url + endpoint , params = {"limit": limit, "offset": offset},headers={"X-API-Key": "demo-key"})
    if request.status_code != 200: 
        print("Error fetching data:", request.status_code) 
        break
    else:  
        data = request.json()
        surveys = data["data"]
        df = pd.DataFrame(surveys) 
        df.to_csv("surveys_test.csv",mode='a', index=False)
        offset = data["meta"]["next_offset"]
        if offset is None:
            break

    
    