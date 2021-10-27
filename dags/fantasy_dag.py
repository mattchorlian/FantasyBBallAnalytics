import os
import json
import pendulum
from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.utils.task_group import TaskGroup
from airflow.utils.db import provide_session
from airflow.models import XCom, Variable

from load_settings import (
  get_league_id_list,
  get_scoring_period_id
)
from rds_operations import (
  create_rds_tables,
  truncate_rds_tables,
  insert_data_into_rds_tables,
  rds_run_query
)
from bigquery_operations import (
  create_tables,
  check_table_exists,
  transfer_gcs_to_bigquery_table,
  join_draft_and_ratings
)
from extract_espn import (
  extract_from_espn_api
)
from transform_data import (
  transform_raw_to_df,
)
from analyze_data import calculate_and_upload_daily_alert
from upload_to_aws import (
  upload_league_data_to_dynamo
)
from upload_to_cloud import (
  upload_to_firebase, 
  upload_to_gcs
)


local_tz = pendulum.timezone('US/Eastern')

default_args = {
  'owner': 'Airflow',
  'start_date': datetime(2021, 1, 1, tzinfo=local_tz),
  'end_date': None,
  'retries': 1,
  'retry_delay': timedelta(seconds=3),
}


with DAG(
  'fantasy_dag', 
  default_args=default_args, 
  schedule_interval='0 8 * * *', 
  catchup=False,
  template_searchpath='/sql/',
) as dag:
  ### Tasks
  # Initializing tables in RDS (alternative)
  with TaskGroup(group_id='init_rds') as init_rds:
    rds_create = create_rds_tables()
    rds_truncate = truncate_rds_tables()

    rds_create >> rds_truncate

  # Getting league ids from 
  init_league_ids = get_league_id_list()
  scoring_period = get_scoring_period_id()

  # Extracting common data from ESPN (not league specific)
  common_endpoints = {
    'ratings': ['kona_player_info', 'mStatRatings'],
    'daily': ['kona_playercard']
  }
  common_headers = {
    'ratings': '''{"players":{"limit":1000,"sortPercOwned":{"sortAsc":false,"sortPriority":1},"sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"STANDARD"}}}''',
    'daily': '''{"players":{"filterStatsForCurrentSeasonScoringPeriodId":{"value":[%s]},"sortStatIdForScoringPeriodId":{"additionalValue":%s,"sortAsc":false,"sortPriority":2,"value":0},"limit":250}}''' % (scoring_period, scoring_period)
  }

  common_data = {}

  with TaskGroup(group_id='extract_common') as extract_common_tg:
    # Extracting common data (non league specific)
    for endpoint in common_endpoints.keys():

      common_endpoinit_group = []
      with TaskGroup(group_id=f'common_endpoint_{endpoint}') as common_etl:
        header = {'x-fantasy-filter': common_headers[endpoint]}

        raw_data = extract_from_espn_api(0, common_endpoints[endpoint], header)
        df = transform_raw_to_df(endpoint, raw_data)
        insert_data_into_rds_tables(-1, endpoint, df)

        #common_data[endpoint] = 


  # Taskgroup for full ETL for each league
  data_endpoints = {
    'settings': ['mSettings'],
    'teams': ['mTeam'],
    'scoreboard': ['mScoreboard'], 
    'draftRecap': ['mDraftDetail']
  }

  league_ids = Variable.get(
    'league_ids',
    default_var={
      'leagueId': ['48375511'],
      'leagueYear': ['2022'],
      'lastYear': ['2020']
    },
    deserialize_json=True
  )

  league_groups = []
  
  # Creating taskgroups dynamically for each league
  for i in range(len(league_ids['leagueId'])):
    league_id = league_ids['leagueId'][i]
    league_year = league_ids['leagueYear'][i]
    last_year = league_ids['lastYear'][i]
    all_years = range(int(last_year), int(league_year) + 1)
    all_years = list(map(str, all_years))

    # Initializing all league data
    league_data = {
      'leagueId': league_id,
      'leagueYear': league_year,
      'allYears': all_years
    }

    with TaskGroup(group_id=f'etl_league_{league_id}') as etl_league:
      endpoint_groups = []

      for endpoint in data_endpoints.keys():
        api_endpoint = data_endpoints[endpoint]

        with TaskGroup(group_id=f'etl_endpoint_{endpoint}') as etl_endpoint:
          # Extract and Transform data from ESPN
          raw_data = extract_from_espn_api(i, api_endpoint)
          df = transform_raw_to_df(endpoint, raw_data)
          insert_data_into_rds_tables(i, endpoint, df)

          # Saving to data dict
          league_data[endpoint] = df

        endpoint_groups.append(etl_endpoint)

      # All endpoints extracted and transformed
      # Performing queries
      with TaskGroup(group_id=f'queries') as queries_tg:
        draft_query = rds_run_query(i, 'rds/join_draft_and_ratings.sql')

        league_data['draftRecap'] = draft_query


      # Uploading to DynamoDB after all endpoints processed
      upload_dynamo = upload_league_data_to_dynamo(league_data)

      endpoint_groups >> queries_tg >> upload_dynamo

    league_groups.append(etl_league)


  scoring_period >> extract_common_tg >> init_league_ids
  init_league_ids >> league_groups
  init_rds >> league_groups

  # Initializing tables in bigquery
  bq_table = create_tables()
  check_table_team_exists = check_table_exists('teams')
  check_table_scoreboard_exists = check_table_exists('scoreboard')
  check_table_draft_exists = check_table_exists('draft')
  check_table_ratings_exists = check_table_exists('ratings')

  bq_table >> [
    check_table_team_exists,
    check_table_scoreboard_exists,
    check_table_draft_exists,
    check_table_ratings_exists
  ]

  # Daily Score ETL
  #daily_score_raw = extract_daily_score_info()
  #daily_score_df = transform_daily_score_to_df(daily_score_raw)
  #daily_alert = calculate_and_upload_daily_alert(daily_score_df, team_info_df)

