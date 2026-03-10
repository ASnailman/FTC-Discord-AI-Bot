import requests
import json
from operator import itemgetter
from collections import OrderedDict

API_URL = "https://api.ftcscout.org/graphql"
CURRENT_FTC_SEASON = 2025
DEFAULT_REGION = 'All'

def fetch_team_data(team_number: int, season: int = None, region: str = None, event_code: str = None):
    # This query requests EVERY field defined in the schema for Team, Awards, QuickStats, Events, and Matches.
    # It explicitly expands all Fragments for seasons 2019-2025.
    if season is None:
        season = CURRENT_FTC_SEASON
    if region is None:
        region = DEFAULT_REGION  

    query = """
    query GetLiterallyEverything($number: Int!, $season: Int!, $region: RegionOption, $eventCode: String) {
      teamByNumber(number: $number) {
        # --- 1. CORE IDENTITY ---
        number
        name
        schoolName
        sponsors
        rookieYear
        website
        createdAt
        updatedAt
        location {
          venue
          city
          state
          country
        }

        # --- 2. AWARDS ---
        awards(season: $season) {
          season
          eventCode
          teamNumber
          divisionName
          personName
          type
          placement
          createdAt
          updatedAt
          event {
            name
          }
        }

        # --- 3. QUICKSTATS ---
        quickStats(season: $season, region: $region) {
          tot { value rank }
          auto { value rank }
          dc { value rank }
          eg { value rank }
          count
        }

        # --- 4. EVENTS & STATS ---
        events(season: $season) {
          season
          eventCode
          teamNumber
          event {
            code
            name
            start
            end
            type
            location { city state country venue }
            website
            liveStreamURL
            timezone
          }
          stats {
            ... on TeamEventStats2025 { ...Stats2025 }
            ... on TeamEventStats2024 { ...Stats2024 }
            ... on TeamEventStats2023 { ...Stats2023 }
            ... on TeamEventStats2022 { ...Stats2022 }
            ... on TeamEventStats2021Trad { ...Stats2021 }
            ... on TeamEventStats2021Remote { ...Stats2021R }
            ... on TeamEventStats2020Trad { ...Stats2020 }
            ... on TeamEventStats2020Remote { ...Stats2020R }
            ... on TeamEventStats2019 { ...Stats2019 }
          }
        }

        # --- 5. MATCHES & SCORES ---
        matches(season: $season, eventCode: $eventCode) {
          season
          eventCode
          matchId
          station
          alliance
          allianceRole
          surrogate
          noShow
          dq
          onField
          createdAt
          updatedAt
          match {
            description
            matchNum
            series
            tournamentLevel
            scheduledStartTime
            actualStartTime
            postResultTime
            hasBeenPlayed
            scores {
              # --- TRADITIONAL SEASONS (Red/Blue Objects) ---
              ... on MatchScores2025 {
                red { ...Score2025 }
                blue { ...Score2025 }
              }
              ... on MatchScores2024 {
                red { ...Score2024 }
                blue { ...Score2024 }
              }
              ... on MatchScores2023 {
                red { ...Score2023 }
                blue { ...Score2023 }
              }
              ... on MatchScores2022 {
                red { ...Score2022 }
                blue { ...Score2022 }
              }
              ... on MatchScores2021Trad {
                red { ...Score2021 }
                blue { ...Score2021 }
              }
              ... on MatchScores2020Trad {
                red { ...Score2020 }
                blue { ...Score2020 }
              }
              ... on MatchScores2019 {
                red { ...Score2019 }
                blue { ...Score2019 }
              }

              # --- REMOTE SEASONS (Direct Fields - No Red/Blue) ---
              # Fixed: Applied directly to the score object
              ... on MatchScores2021Remote {
                 ...Score2021R
              }
              ... on MatchScores2020Remote {
                 ...Score2020R
              }
            }
          }
        }
      }
    }

    # --- FRAGMENTS ---

    # 2025: INTO THE DEEP
    fragment Stats2025 on TeamEventStats2025 {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints totalPointsNp }
      tot {
        autoLeavePoints autoLeavePointsIndividual
        autoArtifactPoints autoArtifactClassifiedPoints autoArtifactOverflowPoints autoPatternPoints
        dcBasePoints dcBaseBonus dcBasePointsIndividual dcBasePointsCombined
        dcArtifactPoints dcArtifactClassifiedPoints dcArtifactOverflowPoints dcPatternPoints dcDepotPoints
        movementRp goalRp patternRp
        autoPoints dcPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        majorsByOppPoints minorsByOppPoints penaltyPointsByOpp
        totalPointsNp totalPoints
      }
    }
    fragment Score2025 on MatchScores2025Alliance {
      totalPoints totalPointsNp autoPoints dcPoints
      autoLeavePoints autoLeave1 autoLeave2
      autoArtifactPoints autoArtifactClassifiedPoints autoArtifactOverflowPoints
      autoPatternPoints autoClassifierState
      dcBasePoints dcBase1 dcBase2 dcBaseBonus
      dcArtifactPoints dcArtifactClassifiedPoints dcArtifactOverflowPoints
      dcPatternPoints dcDepotPoints dcClassifierState
      movementRp goalRp patternRp
      minorsCommitted majorsCommitted penaltyPointsCommitted
      minorsByOpp majorsByOpp penaltyPointsByOpp
    }

    # 2024: CENTERSTAGE
    fragment Stats2024 on TeamEventStats2024 {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints totalPointsNp }
      tot {
        autoParkPoints autoParkPointsIndividual
        autoSamplePoints autoSpecimenPoints
        autoSampleNetPoints autoSampleLowPoints autoSampleHighPoints
        autoSpecimenLowPoints autoSpecimenHighPoints
        dcParkPoints dcParkPointsIndividual
        dcSamplePoints dcSpecimenPoints
        dcSampleNetPoints dcSampleLowPoints dcSampleHighPoints
        dcSpecimenLowPoints dcSpecimenHighPoints
        autoPoints dcPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        majorsByOppPoints minorsByOppPoints penaltyPointsByOpp
        totalPointsNp totalPoints
      }
    }
    fragment Score2024 on MatchScores2024Alliance {
      totalPoints totalPointsNp autoPoints dcPoints
      autoPark1 autoPark2
      autoSampleNet autoSampleLow autoSampleHigh
      autoSpecimenLow autoSpecimenHigh
      dcPark1 dcPark2
      dcSampleNet dcSampleLow dcSampleHigh
      dcSpecimenLow dcSpecimenHigh
      autoParkPoints autoSamplePoints autoSpecimenPoints
      dcParkPoints dcSamplePoints dcSpecimenPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
      minorsByOpp majorsByOpp penaltyPointsByOpp
    }

    # 2023: POWERPLAY
    fragment Stats2023 on TeamEventStats2023 {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        egNavPoints egNavPointsIndividual
        purplePoints purplePointsIndividual
        yellowPoints yellowPointsIndividual
        autoPixelPoints autoBackstagePoints autoBackdropPoints
        autoNavPoints autoNavPointsIndividual
        dronePoints dronePointsIndividual
        setLinePoints mosaicPoints
        autoPoints dcPoints dcBackdropPoints dcBackstagePoints egPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        majorsByOppPoints minorsByOppPoints penaltyPointsByOpp
        totalPointsNp totalPoints
      }
    }
    fragment Score2023 on MatchScores2023Alliance {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      egNav2023_1 egNav2023_2
      purple1 purple2 yellow1 yellow2
      autoBackdrop autoBackstage
      dcBackstage dcBackdrop
      autoNav1 autoNav2
      drone1 drone2
      maxSetLine mosaics
      egNavPoints purplePoints yellowPoints
      autoPixelPoints autoNavPoints dronePoints
      setLinePoints mosaicPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
      minorsByOpp majorsByOpp penaltyPointsByOpp
    }

    # 2022: FREIGHT FRENZY
    fragment Stats2022 on TeamEventStats2022 {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoNavPoints autoNavPointsIndividual
        autoConePoints autoTerminalPoints autoGroundPoints
        autoLowPoints autoMediumPoints autoHighPoints
        egNavPoints egNavPointsIndividual
        ownershipPoints coneOwnershipPoints beaconOwnershipPoints circuitPoints
        autoPoints dcPoints egPoints
        dcTerminalPoints dcGroundPoints dcLowPoints dcMediumPoints dcHighPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        majorsByOppPoints minorsByOppPoints penaltyPointsByOpp
        totalPointsNp totalPoints
      }
    }
    fragment Score2022 on MatchScores2022Alliance {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      autoNav2022_1 autoNav2022_2
      autoTerminalCones autoGroundCones autoLowCones autoMediumCones autoHighCones
      dcNearTerminalCones dcFarTerminalCones
      dcTerminalCones dcGroundCones dcLowCones dcMediumCones dcHighCones
      egNav1 egNav2
      coneOwnedJunctions beaconOwnedJunctions circuit
      autoNavPoints autoConePoints egNavPoints ownershipPoints circuitPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
      minorsByOpp majorsByOpp penaltyPointsByOpp
    }

    # 2021: ULTIMATE GOAL (Trad + Remote)
    fragment Stats2021 on TeamEventStats2021Trad {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoCarouselPoints autoNavPoints autoNavPointsIndividual
        autoFreightPoints autoFreight1Points autoFreight2Points autoFreight3Points
        autoFreightStoragePoints autoBonusPoints autoBonusPointsIndividual
        dcAllianceHubPoints dcFreight1Points dcFreight2Points dcFreight3Points
        dcSharedHubPoints dcStoragePoints
        egDuckPoints allianceBalancedPoints sharedUnbalancedPoints
        egParkPoints egParkPointsIndividual cappingPoints
        autoPoints dcPoints egPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        totalPointsNp totalPoints
      }
    }
    fragment Stats2021R on TeamEventStats2021Remote {
      rank rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoCarouselPoints autoNavPoints autoNavPointsIndividual
        autoFreightPoints autoFreight1Points autoFreight2Points autoFreight3Points
        autoFreightStoragePoints autoBonusPoints autoBonusPointsIndividual
        dcAllianceHubPoints dcFreight1Points dcFreight2Points dcFreight3Points
        dcStoragePoints egDuckPoints allianceBalancedPoints
        egParkPoints egParkPointsIndividual cappingPoints
        autoPoints dcPoints egPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        totalPointsNp totalPoints
      }
    }
    fragment Score2021 on MatchScores2021Alliance {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      barcodeElement1 barcodeElement2
      autoCarousel autoNav2021_1 autoNav2021_2 autoBonus1 autoBonus2
      autoStorageFreight autoFreight1 autoFreight2 autoFreight3
      dcStorageFreight dcFreight1 dcFreight2 dcFreight3 sharedFreight
      egDucks allianceBalanced sharedUnbalanced
      egPark1 egPark2 capped
      autoCarouselPoints autoNavPoints autoFreightPoints autoBonusPoints
      dcAllianceHubPoints dcSharedHubPoints dcStoragePoints
      egDuckPoints allianceBalancedPoints sharedUnbalancedPoints
      egParkPoints cappingPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
    }
    fragment Score2021R on MatchScores2021Remote {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      barcodeElement autoCarousel autoNav2021 autoBonus
      autoStorageFreight autoFreight1 autoFreight2 autoFreight3
      dcStorageFreight dcFreight1 dcFreight2 dcFreight3
      egDucks allianceBalanced egPark capped
      autoCarouselPoints autoNavPoints autoFreightPoints autoBonusPoints
      dcAllianceHubPoints dcStoragePoints
      egDuckPoints allianceBalancedPoints egParkPoints cappingPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
    }

    # 2020: SKYSTONE (Trad + Remote)
    fragment Stats2020 on TeamEventStats2020Trad {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoNavPoints autoNavPointsIndividual
        autoTowerPoints autoTowerLowPoints autoTowerMidPoints autoTowerHighPoints
        autoWobblePoints autoPowershotPoints
        egWobblePoints egPowershotPoints egWobbleRingPoints
        autoPoints dcPoints egPoints
        dcTowerLowPoints dcTowerMidPoints dcTowerHighPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        totalPointsNp totalPoints
      }
    }
    fragment Stats2020R on TeamEventStats2020Remote {
      rank rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoNavPoints autoNavPointsIndividual
        autoTowerPoints autoTowerLowPoints autoTowerMidPoints autoTowerHighPoints
        autoWobblePoints autoPowershotPoints
        egWobblePoints egPowershotPoints egWobbleRingPoints
        autoPoints dcPoints egPoints
        dcTowerLowPoints dcTowerMidPoints dcTowerHighPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        totalPointsNp totalPoints
      }
    }
    fragment Score2020 on MatchScores2020Alliance {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      autoWobble1 autoWobble2 autoNav2020_1 autoNav2020_2
      autoPowershots autoTowerLow autoTowerMid autoTowerHigh
      dcTowerLow dcTowerMid dcTowerHigh
      wobbleEndPos1 wobbleEndPos2
      egWobbleRings egPowershots
      autoNavPoints autoTowerPoints autoWobblePoints autoPowershotPoints
      egWobblePoints egPowershotPoints egWobbleRingPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
    }
    fragment Score2020R on MatchScores2020Remote {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      autoWobble1 autoWobble2 autoNav2020
      autoPowershots autoTowerLow autoTowerMid autoTowerHigh
      dcTowerLow dcTowerMid dcTowerHigh
      wobbleEndPos1 wobbleEndPos2
      egWobbleRings egPowershots
      autoNavPoints autoTowerPoints autoWobblePoints autoPowershotPoints
      egWobblePoints egPowershotPoints egWobbleRingPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
    }

    # 2019: ROVER RUCKUS
    fragment Stats2019 on TeamEventStats2019 {
      rank wins losses ties rp qualMatchesPlayed
      opr { totalPoints autoPoints dcPoints }
      tot {
        autoNavPoints autoNavPointsIndividual
        autoRepositioningPoints autoDeliveryPoints autoPlacementPoints
        dcDeliveryPoints dcPlacementPoints
        skyscraperBonusPoints cappingPoints cappingPointsIndividual
        egParkPoints egParkPointsIndividual egFoundationMovedPoints
        autoPoints dcPoints egPoints
        majorsCommittedPoints minorsCommittedPoints penaltyPointsCommitted
        majorsByOppPoints minorsByOppPoints penaltyPointsByOpp
        totalPointsNp totalPoints
      }
    }
    fragment Score2019 on MatchScores2019Alliance {
      totalPoints totalPointsNp autoPoints dcPoints egPoints
      autoNav2019_1 autoNav2019_2 repositioned
      autoDelivered autoSkystonesDeliveredFirst
      autoReturned autoFirstReturnedSkystone autoPlaced
      dcDelivered dcReturned dcPlaced skyscraperHeight
      capLevel1 capLevel2
      egFoundationMoved egParked1 egParked2
      autoNavPoints autoRepositioningPoints autoDeliveryPoints autoPlacementPoints
      dcDeliveryPoints dcPlacementPoints skyscraperBonusPoints
      cappingPoints egParkPoints egFoundationMovedPoints
      minorsCommitted majorsCommitted penaltyPointsCommitted
      minorsByOpp majorsByOpp penaltyPointsByOpp
    }
    """
    
    variables = {
        "number": team_number,
        "season": season,
        "region": region,
        "eventCode": event_code
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

def fetch_teams():
    query = """
    query GetTeams {
      teamsSearch(limit: 30000) {
        number
        name
      }
    }
    """

    response = requests.post(API_URL, json={"query": query}, timeout=15)

    if response.status_code != 200:
        print(f"API Error {response.status_code}: {response.text}")
        return None

    data = response.json()
    
    if "errors" in data:
        print(f"Schema Error: {data['errors'][0]['message']}")
        return None
    
    
    # dictionary format: team_name : team_number
    teams_list = data['data']['teamsSearch']
    teams_dict = {}
    for team in teams_list:
        if team['name']:
          team_name = team.get('name')
          team_number = team.get('number')
          teams_dict.update({team_name : team_number})

    return teams_dict

def fetch_teams_by_region(region: str = None):
    if region is None:
        region = DEFAULT_REGION 

    query = """
    query GetTeamsByRegion($region: RegionOption) {
      teamsSearch(region: $region, limit: 30000) {
        number
        name
      }
    }
    """

    variables = {
        "region": region
    }

    response = requests.post(API_URL, json={"query": query, "variables": variables}, timeout=15)

    if response.status_code != 200:
        print(f"API Error {response.status_code}: {response.text}")
        return None

    data = response.json()
    
    if "errors" in data:
        print(f"Schema Error: {data['errors'][0]['message']}")
        return None
    
    
    # dictionary format: team_name : team_number
    teams_list = data['data']['teamsSearch']
    teams_dict = {}
    for team in teams_list:
        if team['name']:
          team_name = team.get('name')
          team_number = team.get('number')
          teams_dict.update({team_name : team_number})

    return sort_dict(teams_dict)

def sort_dict(dict: dict):
    sorted_pairs = sorted(dict.items(), key=itemgetter(1))
    sorted_teams = OrderedDict(sorted_pairs)
    return sorted_teams

if __name__ == "__main__":
    TEAM_NUM = 14469
    YEAR = 2022
    REGION = "All" # can be any state Initial, UnitedStates, International, All, etc

    # result = fetch_team_data(TEAM_NUM, YEAR, REGION)
    #     with open("output.json", "w") as file:
    #         file.write(json.dumps(result, indent=2))

    # team_dict = fetch_teams()
    # sorted_team_dict = sort_dict(team_dict)
    # if sorted_team_dict:
    #     with open("output_names.json", "w") as file:
    #         file.write(json.dumps(sorted_team_dict, indent=2))

    team_dict_region = fetch_teams_by_region('UnitedStates')
    if team_dict_region:
        with open("output_names_region.json", "w") as file:
            file.write(json.dumps(team_dict_region, indent=2))
    
    else:
        print("Failed to fetch data.")