import requests 
import pandas as pd 

Url = "http://127.0.0.1:8000" 

Headers = {"X-API-Key": "demo-key"}

endpoint_surveys = "/api/v1/surveys" 
endpoint_teams = "/api/v1/teams"
endpoint_agents = "/api/v1/agents"
endpoint_customers = "/api/v1/customers"
endpoint_interactions = "/api/v1/interactions"
endpoint_qa_evaluations = "/api/v1/qa-evaluations"
endpoint_shifts = "/api/v1/shifts"


endpoint_surveys_data = []
endpoint_teams_data = []
endpoint_agents_data =[] 
endpoint_customers_data=[] 
endpoint_interactions_data = []
endpoint_qa_evaluations_data = []
endpoint_shifts_data = []

Data_array = [endpoint_surveys_data, endpoint_teams_data, endpoint_agents_data, endpoint_customers_data, endpoint_interactions_data, endpoint_qa_evaluations_data, endpoint_shifts_data]

endpoints = [endpoint_surveys, endpoint_teams, endpoint_agents, endpoint_customers, endpoint_interactions, endpoint_qa_evaluations, endpoint_shifts] 

df_data = pd.DataFrame()

# Fetch data from the API in batches of 500 and save to CSV file
#/


def fetch_data_from_api(endpoint, data_array):

    offset = 0
    limit = 500

    while True:
        params = {"offset": offset, "limit": limit}
        response = requests.get(Url + endpoint, headers=Headers, params=params)
        if response.status_code == 200:
            records = response.json()["data"]   # the API puts the records under "data"
            if not records:
                break                           # no more pages for this endpoint
            data_array.extend(records)
            offset += len(records)              # move to the next page
        else:
            print(f"Error fetching data from {endpoint}: {response.status_code}")
            break
    print(f"Fetched {len(data_array)} records from {endpoint}") 
    return data_array  

Data_array_count = len(endpoints)

Data_frames = []

for x in range(Data_array_count):
    df = pd.DataFrame(fetch_data_from_api(endpoints[x], Data_array[x]))
   # df.to_csv(f"{endpoints[x][8:]}.csv", index=False)
    Data_frames.append(df)
    print(endpoints[x][8:], len(df), "rows saved")

print(Data_frames[1].head())