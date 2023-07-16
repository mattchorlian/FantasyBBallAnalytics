import json
import boto3
import psycopg2

from util import invoke_lambda
from espn_helper import get_espn_league_status
from yahoo_auth import get_yahoo_access_token


lambda_client = boto3.client('lambda', region_name='us-east-1')

db_pass = invoke_lambda(lambda_client, 'get_secret', {'key': 'supabase_password'})

conn = psycopg2.connect(
    host='db.lsygyiijbumuybwyuvrn.supabase.co',
    port='5432',
    database='postgres',
    user='postgres',
    password=db_pass
)


def get_league_id_status(event, context):
    print(event)
    
    cursor = conn.cursor()

    league_id = event["queryStringParameters"]['leagueId']
    platform = event["queryStringParameters"]["platform"]

    get_query = open("sql/get_league_info.sql", "r").read()
    get_params = {"league_id": league_id, "platform": platform}

    cursor.execute(get_query, get_params)

    res = cursor.fetchone()

    league_exists = bool(res)
    league_updated = league_exists and res[0]
    league_key = league_exists and res[1]

    print(f"League {league_id} on {platform}, exists {league_exists}, updated {league_updated}")

    if league_updated:
        print("League already updated, returning active")
        return {"statusCode": 200, "body": json.dumps("ACTIVE")}
    
    if platform == "espn":
        cookie_espn_qsp = event["queryStringParameters"].get('cookieEspnS2', None)
        cookie_espn = cookie_espn_qsp or league_key

        cookies = {"espn_s2": cookie_espn}

        status = get_espn_league_status(league_id, cookies)
        if status != "VALID":
            print(f"Invalid league, status: {status}")
            return {"statusCode": 200, "body": json.dumps(status)}

        event["queryStringParameters"]['cookieEspnS2'] = cookie_espn
        
        # Call league analysis lambda
        res = invoke_lambda(lambda_client, "process_espn_league", event)

        sql_file = "sql/update_espn_league_after_process.sql"
    
    elif platform == "yahoo":
        event["queryStringParameters"]["yahooRefreshToken"] = league_key

        tokens = get_yahoo_access_token(event, context)
        if tokens.get("error"):
            return {"statusCode": 200, "body": json.dumps(tokens["error"])}
        
        yahoo_access_token = tokens["yahoo_access_token"]
        yahoo_refresh_token = tokens["yahoo_refresh_token"]
        event["queryStringParameters"]["yahooAccessToken"] = yahoo_access_token
        
        # TODO function
        res = invoke_lambda(lambda_client, "process_yahoo_league", event)

        sql_file = "sql/update_yahoo_league_after_process.sql"

    if res["statusCode"] == 200:
        update_query = open(sql_file, "r").read()
        update_params = {
            "league_id": league_id,
            "platform": platform,
            "cookie_espn": cookie_espn,
            "yahoo_refresh_token": yahoo_refresh_token
        }

        cursor.execute(update_query, update_params)
        conn.commit()
    
        print("League processed, returning active")
        return {"statusCode": 200, "body": json.dumps("ACTIVE")}

    print("Uncommon process error, returning error")
    return {"statusCode": 200, "body": json.dumps("ERROR")}

    

sql_last_viewed = """
    UPDATE public.leagueids
    SET lastViewed = NOW(), viewCount = viewCount + 1
    WHERE leagueid = %s
"""

sql_last_updated = """
    UPDATE public.leagueids
    SET lastUpdated = NOW()
    WHERE leagueid = %s
"""

def update_league_info(event, context):
    print(event)
    league_id = event['queryStringParameters'].get('leagueId')
    method = event['queryStringParameters'].get('method')
    
    cursor = conn.cursor()
    
    if method == 'lastViewed':
        params = (league_id,)
        
        cursor.execute(sql_last_viewed, params)
        
    elif method == 'lastUpdated':
        params = (league_id,)
        
        cursor.execute(sql_last_updated, params)
        
        
    rows_updated = cursor.rowcount
    
    if rows_updated > 0:
        conn.commit()
    else:
        return {
            'statusCode': 500,
            'body': json.dumps('Updated failed') 
        }
            

    return {
        'statusCode': 200,
        'body': json.dumps('Updated successfully')
    }