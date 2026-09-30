import requests 
import pandas as pd 

Url = "http://localhost:8000" 

Headers = {"X-API-Key": "demo-key"}


endpoint_surveys = "/api/v1/surveys" 
endpoint_teams = "/api/v1/teams"
endpoint_agents = "/api/v1/agents"
endpoint_customers = "/api/v1/customers"
endpoint_interactions = "/api/v1/interactions"
endpoint_qa_evaluations = "/api/v1/qa-evaluations"
endpoint_shifts = "/api/v1/shifts"

endpoints = [endpoint_surveys, endpoint_teams, endpoint_agents, endpoint_customers, endpoint_interactions, endpoint_qa_evaluations, endpoint_shifts] 


# Fetch data from the API in batches of 500 and save to CSV file
limit = 500 
offset = 0 
while True: 
    for endpoint in endpoints: 
        response = requests.get(Url + endpoint, params={"limit": limit, "offset": offset},headers=Headers) 
        data = response.json() 
        df = pd.DataFrame(data) 
        df.to_csv(f"{endpoint[5:]}.csv", mode='a', index=False, header=not bool(offset)) 
        offset = data["meta"]["offset"] 
    

    
    