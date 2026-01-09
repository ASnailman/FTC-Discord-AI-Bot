import requests

API_URL = "https://api.ftcscout.org/graphql"

def safe_get(data, keys):
    """Safely retrieves nested keys from a dictionary."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return "N/A"
    return data if data is not None else "N/A"

def fetch_team_data(team_number: int, season: int, region: str):
    # This MASSIVE query covers every schema definition from 2019 to 2025.
    # It uses 'Inline Fragments' (... on Type) to request year-specific fields.
    query = """
    query GetMassiveSeasonContext($number: Int!, $season: Int!, $region: RegionOption) {
      teamByNumber(number: $number) {
        # TEAM  
        number
        name
        schoolName
        sponsors
        rookieYear
        website
        location {
          city
          state
          country
          venue
        }

        # AWARDS
        awards(season: $season) {
          season
          eventCode
          divisionName
          personName
          type
          placement
          personName
          event {
            name
          }
        }
        
        quickStats(season: $season, region: $region) {
          tot { value rank }
          auto { value rank }
          dc { value rank }
          eg { value rank }
          count
        }

        
        events(season: $season) {
          eventCode
          event {
            name
            start
            type
          }
          stats {
            # 2025: Into the Deep
            ... on TeamEventStats2025 {
              rank wins losses ties rp
              opr { totalPoints autoPoints dcPoints }
            }
            # 2024: CenterStage
            ... on TeamEventStats2024 {
              rank wins losses ties rp
              opr { totalPoints autoPoints dcPoints }
            }
            # 2023: PowerPlay
            ... on TeamEventStats2023 {
              rank wins losses ties rp
              opr { totalPoints autoPoints dcPoints }
            }
            # 2022: Freight Frenzy
            ... on TeamEventStats2022 {
              rank wins losses ties
              opr { totalPoints autoPoints dcPoints }
            }
          }
        }

        matches(season: $season) {
          match {
            description
            matchNum
            scores {
              # 2025 Match Details
              ... on MatchScores2025 {
                red { totalPoints autoPoints dcPoints }
                blue { totalPoints autoPoints dcPoints }
              }
              # 2024 Match Details
              ... on MatchScores2024 {
                red { totalPoints autoPoints dcPoints }
                blue { totalPoints autoPoints dcPoints }
              }
              # 2023 Match Details
              ... on MatchScores2023 {
                red { totalPoints autoPoints dcPoints }
                blue { totalPoints autoPoints dcPoints }
              }
            }
          }
        }
      }
    }
    """
    
    variables = {
        "number": team_number,
        "season": season,
        "region": region
    }
    
    try:
        response = requests.post(API_URL, json={"query": query, "variables": variables}, timeout=15)
        
        if response.status_code != 200:
            print(f"API Error {response.status_code}: {response.text}")
            return None

        data = response.json()
        
        if "errors" in data:
            # This helps debug if the massive query has a typo
            print(f"Schema Error: {data['errors'][0]['message']}")
            return None
            
        return data.get("data", {}).get("teamByNumber")
        
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

if __name__ == "__main__":
    TEAM_NUM = 15005
    YEAR = 2022
    REGION = "All" # can be any state Initial, UnitedStates, International, All, etc

    result = fetch_team_data(TEAM_NUM, YEAR, REGION)
    if result:
        print(result)
        print("-----------\n")

        print("TEAM INFO")
        print(f"Team: {result['name']} {result['number']}")
        print(f"School: {result['schoolName']}")
        print(f"Sponsors: {result['sponsors']}")
        print(f"Rookie Year: {result['rookieYear']}")
        print(f"Website: {result['website']}")
        print(f"Team: {result['name']}")
        print(f"Country: {safe_get(result, ['location', 'country'])}")
        print(f"State: {safe_get(result, ['location', 'state'])}")
        print(f"City: {safe_get(result, ['location', 'city'])}")
        print(f"Venue: {safe_get(result, ['location', 'venue'])}")
        print("-----------\n")
        
        print("AWARDS")
        awards = result.get('awards', [])
        for award in awards:
            print(f"Event: {safe_get(award, ['event'])}")
            print(f"Event Code: {safe_get(award, ['eventCode'])}")
            print(f"Division Name: {safe_get(award, ['divisionName'])}")
            print(f"Person Name: {safe_get(award, ['personName'])}")
            print(f"Placement: {safe_get(award, ['placement'])}")
            print(f"Award Type: {safe_get(award, ['type'])}")
            print("....")
            
        print("-----------\n")
        
        print("MATCHES")
        print("-----------\n")
        
        print("QUICKSTATS")
        qstats = result.get('quickStats', {})
        for cat, stats in qstats.items():
            if isinstance(stats, dict):
                print(f"Category: {cat.upper()}")
                print(f"Value: {safe_get(stats, ['value'])}")
                print(f"Rank: {safe_get(stats, ['rank'])}")
                print("....")
        print(f"Total Teams Scored: {qstats.get('count', 'N/A')}")
        print("-----------\n")
        
        print("EVENTS")
        # events = result.get('events', [])
        print("-----------\n")

    else:
        print("Failed to fetch data.")