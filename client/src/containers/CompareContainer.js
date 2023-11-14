import React, { useState } from 'react';
import styled from 'styled-components';

import CompareTable from '../tables/CompareTable';
import CompareSummaryTable from '../tables/CompareSummaryTable';
import * as arrayMath from '../utils/arrayMath';
import * as catUtils from '../utils/categoryUtils';
import { calculateMatchup } from '../utils/matchupUtils';
import CompareH2HTable from '../tables/CompareH2HTable';

function CompareContainer(props) {
  const [selectedTeams, setSelectedTeams] = useState([0, 0]);

  const teams = props.teams;
  const scoreboardData = props.data;
  const catSettings = props.settings[0].categoryIds;
  const currentWeek = props.currentWeek;

  const data = [];
  const h2h = [];
  const summaryData = {};

  // Filtering out unselected teams
  const filteredData = scoreboardData.filter((row) =>
    selectedTeams.includes(row.teamId)
  );

  // Filtering out the categories
  const cats = catUtils.categoryDetails.filter(o => {
    return catSettings.includes(o.espnId) && o.name !== 'mins'
  })

  // Calculating Head to Head matchup table
  if (!selectedTeams.includes(0)) {
    const h2hRowOne = {};
    const h2hRowTwo = {};
    const teamOneId = selectedTeams[0];
    const teamTwoId = selectedTeams[1];
    h2hRowOne["rowHeader"] = teams.filter((team) => team.teamId === teamOneId)?.[0]?.fullTeamName;
    h2hRowTwo["rowHeader"] = teams.filter((team) => team.teamId === teamTwoId)?.[0]?.fullTeamName;

    for (let week = 1; week <= currentWeek; week++) {
      const teamOneWeekData = filteredData.filter((o) => o.week === week && o.teamId === teamOneId);
      const teamTwoWeekData = filteredData.filter((o) => o.week === week && o.teamId === teamTwoId);
      const teamOneWin = calculateMatchup(
        teamOneWeekData?.[0],
        teamTwoWeekData?.[0]
      );
      h2hRowOne[`week${week}`] = teamOneWin ? "Won" : "";
      h2hRowTwo[`week${week}`] = !teamOneWin ? "Won" : "";
    }
    h2h.push(h2hRowOne);
    h2h.push(h2hRowTwo);
  }

  // Calculating comparison table and summary table
  if (!selectedTeams.includes(0)) {
    for (const cat of cats) {
      const catName = cat.name;
      const display = cat.display;
      const digits = cat.digits ? cat.digits : 0;

      const allCatValues = [];
      for (const team of selectedTeams) {
        const dataRow = {};
        dataRow['rowHeader'] = display;
        dataRow['catId'] = catName;

        filteredData.forEach((row) => {
          if (row.teamId === team) {
            const dataPoint = row[catName];

            // Setting individual team data
            dataRow['week' + row.week] = dataPoint?.toFixed(digits);

            // Setting summary data
            allCatValues.push(dataPoint);
          }
        });
        const dataRowValues = Object.values(dataRow).splice(1);
        const mean = arrayMath.mean(dataRowValues)?.toFixed(digits);
        const stdev = arrayMath.stdev(dataRowValues)?.toFixed(digits);
        const min = Math.min(...arrayMath.filterNaN(dataRowValues));
        const max = Math.max(...arrayMath.filterNaN(dataRowValues));

        dataRow.mean = mean;
        dataRow.stdev = stdev;
        dataRow.min = min;
        dataRow.max = max;
        data.push(dataRow);
      }
      // Calculating summary cat data
      summaryData[display] = {
        mean: arrayMath.mean(allCatValues),
        stdev: arrayMath.stdev(allCatValues),
      };
    }
  }

  // Calculating the wins between teams for each category
  data.forEach(row => {
    row.wins = 0;
    const filteredCat = data.filter(o => o.rowHeader === row.rowHeader && o !== row)

    // Going through the weeks to add wins
    for (let week = 1; week <= currentWeek; week++) {
      const weekKey = 'week' + week

      const allCatValues = filteredCat.map(val => {
        return val[weekKey]
      })

      if (catUtils.determineWinner(row[weekKey], allCatValues, row.catId)) {
        row.wins = row.wins + 1;
      }
    }
  })

  const isDataLoaded = data.length !== 0 && !selectedTeams.includes(0);

  // Function to handle changing drop down list
  const handleTeamChange = (e) => {
    const position = parseInt(e.target.firstChild.text.slice(-1)) - 1;
    const val = e.target.value;

    const newSelectedTeams = [selectedTeams[0], selectedTeams[1]];
    newSelectedTeams[position] = parseInt(val);

    if (newSelectedTeams[0] !== newSelectedTeams[1]) {
      setSelectedTeams(newSelectedTeams);
    }
  };

  return (
    <Container>
      <DropDownList>
        <DropDown value={selectedTeams[0]} onChange={handleTeamChange}>
          <option value='' key={0}>
            Select Team 1
          </option>
          {teams.map((o) => {
            return (
              <option value={o.teamId} key={o.teamId}>
                {o.fullTeamName}
              </option>
            );
          })}
        </DropDown>
        <DropDown value={selectedTeams[1]} onChange={handleTeamChange}>
          <option value='' key={0}>
            Select Team 2
          </option>
          {teams.map((o) => {
            return (
              <option value={o.teamId} key={o.teamId}>
                {o.fullTeamName}
              </option>
            );
          })}
        </DropDown>
      </DropDownList>
      {isDataLoaded ? (
        <TableContainer>
          <CompareH2HTable
            data={h2h}
            currentWeek={currentWeek}
          />
        </TableContainer>        
      ) : (
        <br />
      )}
      {isDataLoaded ? (
        <TableContainer>
          <CompareTable
            data={data}
            summaryData={summaryData}
            currentWeek={currentWeek}
          />
          <CompareSummaryTable data={data} currentWeek={currentWeek} />
        </TableContainer>
      ) : (
        <br />
      )}
    </Container>
  );
}

const Container = styled.div`
  display: flex;
  flex-direction: column;

  width: 100%;
`;

const DropDownList = styled.div`
  display: flex;
  flex-direction: row;

  margin: 0.2rem auto;
  margin-bottom: 1rem;
`;

const DropDown = styled.select`
  width: 50%;
  margin: 0 0.1rem;
`;

const TableContainer = styled.div`
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: center;
`;

export default CompareContainer;
