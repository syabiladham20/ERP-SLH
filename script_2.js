
    // Toggle all accordions
    function toggleAllAccordions(expand) {
        const accordionBodies = document.querySelectorAll('#accordionBodyweightLog .accordion-collapse');
        const accordionButtons = document.querySelectorAll('#accordionBodyweightLog .accordion-button');

        accordionBodies.forEach(body => {
            if (expand) {
                body.classList.add('show');
            } else {
                body.classList.remove('show');
            }
        });

        accordionButtons.forEach(btn => {
            if (expand) {
                btn.classList.remove('collapsed');
                btn.setAttribute('aria-expanded', 'true');
            } else {
                btn.classList.add('collapsed');
                btn.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // Charting logic
    document.addEventListener("DOMContentLoaded", function() {
        const houseFilter = document.getElementById('houseFilter');
        const chartContainer = document.getElementById('chartContainer');
        const togglePartitions = document.getElementById('togglePartitions');
        const chartStartWeek = document.getElementById('chartStartWeek');
        const accordionItems = document.querySelectorAll('.bw-log-item');

        let maleChart = null;
        let femaleChart = null;

        // Pass the log data from python to JS
        const logData = "{}";
        if (!logData) return;

        function renderCharts(selectedHouse) {
            // Filter logs by house
            let filteredLogs = logData.filter(log => log.house_name === selectedHouse);

            // Sort by age week ascending for charts
            filteredLogs.sort((a, b) => a.age_weeks - b.age_weeks);

            // Limit by start week selection
            const numWeeks = chartStartWeek.value;
            if (numWeeks !== 'all') {
                const limit = parseInt(numWeeks);
                filteredLogs = filteredLogs.slice(-limit);
            }

            const categories = filteredLogs.map(log => 'Week ' + log.age_weeks);
            const showPartitions = togglePartitions.checked;

            // Generate Series for Male
            let maleSeries = [];
            let femaleSeries = [];

            // Compute Min/Max for dynamic Y-axis
            let allMaleBw = [];
            let allFemaleBw = [];

            function addMainLines(seriesArr, avgData, stdData, unifData, allBwArr) {
                let bwData = avgData.map(v => v ? parseFloat(v) : null);
                let stdBwData = stdData.map(v => v ? parseFloat(v) : null);
                let uData = unifData.map(v => v ? parseFloat(v) : null);

                seriesArr.push({
                    name: 'Average BW',
                    type: 'line',
                    data: bwData
                });
                allBwArr.push(...bwData.filter(v => v !== null));

                seriesArr.push({
                    name: 'Standard BW',
                    type: 'line',
                    data: stdBwData
                });
                allBwArr.push(...stdBwData.filter(v => v !== null));

                seriesArr.push({
                    name: 'Average Uniformity',
                    type: 'line',
                    data: uData
                });
            }

            if (!showPartitions) {
                // Averages only
                addMainLines(
                    maleSeries,
                    filteredLogs.map(log => log.avg_m || null),
                    filteredLogs.map(log => log.std_m || null),
                    filteredLogs.map(log => log.uni_m || null),
                    allMaleBw
                );

                addMainLines(
                    femaleSeries,
                    filteredLogs.map(log => log.avg_f || null),
                    filteredLogs.map(log => log.std_f || null),
                    filteredLogs.map(log => log.uni_f || null),
                    allFemaleBw
                );
            } else {
                // Show partitions for BW, but only avg for Uniformity and Standard

                let stdMBw = filteredLogs.map(log => log.std_m ? parseFloat(log.std_m) : null);
                maleSeries.push({
                    name: 'Standard BW',
                    type: 'line',
                    data: stdMBw
                });
                allMaleBw.push(...stdMBw.filter(v => v !== null));

                maleSeries.push({
                    name: 'Average Uniformity',
                    type: 'line',
                    data: filteredLogs.map(log => log.uni_m ? parseFloat(log.uni_m) : null)
                });

                let stdFBw = filteredLogs.map(log => log.std_f ? parseFloat(log.std_f) : null);
                femaleSeries.push({
                    name: 'Standard BW',
                    type: 'line',
                    data: stdFBw
                });
                allFemaleBw.push(...stdFBw.filter(v => v !== null));

                femaleSeries.push({
                    name: 'Average Uniformity',
                    type: 'line',
                    data: filteredLogs.map(log => log.uni_f ? parseFloat(log.uni_f) : null)
                });

                // Partitions for Male
                let maxMParts = 0;
                filteredLogs.forEach(log => {
                    if (log.m_parts && log.m_parts.length > maxMParts) {
                        maxMParts = log.m_parts.length;
                    }
                });

                if (maxMParts > 0) {
                    for (let i = 0; i < maxMParts; i++) {
                        let pData = filteredLogs.map(log => {
                            if (log.m_parts && log.m_parts[i] && log.m_parts[i].bw) return parseFloat(log.m_parts[i].bw);
                            return null;
                        });
                        maleSeries.push({
                            name: `P${i+1} BW`,
                            type: 'line',
                            data: pData
                        });
                        allMaleBw.push(...pData.filter(v => v !== null));
                    }
                } else {
                    let mAvgData = filteredLogs.map(log => log.avg_m ? parseFloat(log.avg_m) : null);
                    maleSeries.push({
                        name: 'Average BW',
                        type: 'line',
                        data: mAvgData
                    });
                    allMaleBw.push(...mAvgData.filter(v => v !== null));
                }

                // Partitions for Female
                let maxFParts = 0;
                filteredLogs.forEach(log => {
                    if (log.f_parts && log.f_parts.length > maxFParts) {
                        maxFParts = log.f_parts.length;
                    }
                });

                if (maxFParts > 0) {
                    for (let i = 0; i < maxFParts; i++) {
                        let pData = filteredLogs.map(log => {
                            if (log.f_parts && log.f_parts[i] && log.f_parts[i].bw) return parseFloat(log.f_parts[i].bw);
                            return null;
                        });
                        femaleSeries.push({
                            name: `P${i+1} BW`,
                            type: 'line',
                            data: pData
                        });
                        allFemaleBw.push(...pData.filter(v => v !== null));
                    }
                } else {
                    let fAvgData = filteredLogs.map(log => log.avg_f ? parseFloat(log.avg_f) : null);
                    femaleSeries.push({
                        name: 'Average BW',
                        type: 'line',
                        data: fAvgData
                    });
                    allFemaleBw.push(...fAvgData.filter(v => v !== null));
                }
            }

            // Calculate Max for Left Y-Axis to keep BW below Uniformity
            let maleMaxBw = allMaleBw.length > 0 ? Math.max(...allMaleBw) : 1000;
            let femaleMaxBw = allFemaleBw.length > 0 ? Math.max(...allFemaleBw) : 1000;

            // Add a 30% buffer to the max BW to ensure it stays below the uniformity dashed line
            let maleYMax = Math.ceil(maleMaxBw * 1.3);
            let femaleYMax = Math.ceil(femaleMaxBw * 1.3);

            // Common Options
            const getChartOptions = (series, title, yMax) => {
                let colors = [];
                let strokeOptions = {
                    curve: [],
                    width: [],
                    dashArray: []
                };

                // Color palette for partitions
                const partitionColors = ['#008FFB', '#00E396', '#FEB019', '#FF4560', '#775DD0', '#3F51B5', '#546E7A', '#D4526E'];
                let pIndex = 0;

                let yaxisConfig = [];
                let firstBwSet = false;

                series.forEach((s) => {
                    strokeOptions.curve.push('straight');
                    if (s.name === 'Standard BW') {
                        strokeOptions.dashArray.push(0);
                        colors.push('#000000'); // Black
                        strokeOptions.width.push(2);
                    } else if (s.name === 'Average Uniformity') {
                        strokeOptions.dashArray.push(5);
                        colors.push('#FFA500'); // Orange
                        strokeOptions.width.push(2);
                    } else if (s.name === 'Average BW') {
                        strokeOptions.dashArray.push(0);
                        colors.push('#008FFB'); // Primary blue
                        strokeOptions.width.push(2);
                    } else { // Partitions
                        strokeOptions.dashArray.push(0);
                        colors.push(partitionColors[pIndex % partitionColors.length]);
                        strokeOptions.width.push(2);
                        pIndex++;
                    }

                    // Define axes
                    if (s.name === 'Average Uniformity') {
                        yaxisConfig.push({
                            seriesName: s.name,
                            opposite: true,
                            title: { text: 'Uniformity (%)' },
                            max: 100,
                            min: 0,
                            labels: { formatter: function (val) { return Math.round(val) + '%'; } }
                        });
                    } else {
                        if (!firstBwSet) {
                             yaxisConfig.push({
                                seriesName: s.name,
                                show: true,
                                title: { text: 'Grams' },
                                max: yMax,
                                min: 0,
                                labels: { formatter: function (val) { return Math.round(val); } }
                            });
                            firstBwSet = true;
                        } else {
                             yaxisConfig.push({
                                seriesName: s.name,
                                show: false,
                                max: yMax,
                                min: 0
                            });
                        }
                    }
                });


                return {
                    series: series,
                    chart: {
                        type: 'line',
                        height: 350,
                        toolbar: { show: true }
                    },
                    colors: colors,
                    stroke: strokeOptions,
                    dataLabels: {
                        enabled: true,
                        offsetY: -10,
                        formatter: function (val, opts) {
                            if (val === null || val === undefined) return '';
                            let seriesName = opts.w.globals.seriesNames[opts.seriesIndex];

                            if (seriesName === 'Standard BW' || seriesName === 'Average Uniformity') {
                                return val;
                            }

                            if (opts.dataPointIndex === 0) return val;
                            const prevVal = opts.w.globals.series[opts.seriesIndex][opts.dataPointIndex - 1];
                            if (prevVal && val) {
                                const diff = val - prevVal;
                                const sign = diff >= 0 ? '+' : '';
                                return `${val} (${sign}${diff.toFixed(0)})`;
                            }
                            return val;
                        },
                        style: {
                            fontSize: '10px'
                        },
                        background: { enabled: false }
                    },
                    title: { text: title, align: 'left' },
                    xaxis: { categories: categories },
                    yaxis: yaxisConfig,
                    markers: { size: 4 },
                    legend: { show: true },
                    tooltip: {
                        shared: true,
                        intersect: false
                    }
                };
            };

            // Male Chart
            if (maleChart) {
                maleChart.destroy();
            }
            maleChart = new ApexCharts(document.querySelector("#chart-bw-male"), getChartOptions(maleSeries, 'Male Bodyweight', maleYMax));
            maleChart.render();

            // Female Chart
            if (femaleChart) {
                femaleChart.destroy();
            }
            femaleChart = new ApexCharts(document.querySelector("#chart-bw-female"), getChartOptions(femaleSeries, 'Female Bodyweight', femaleYMax));
            femaleChart.render();
        }

        // Filtering Logic
        houseFilter.addEventListener('change', function() {
            const selectedHouse = this.value;

            if (selectedHouse === 'all') {
                chartContainer.style.display = 'none';
                accordionItems.forEach(item => item.style.display = 'block');
            } else {
                chartContainer.style.display = 'block';
                accordionItems.forEach(item => {
                    if (item.getAttribute('data-house') === selectedHouse) {
                        item.style.display = 'block';
                    } else {
                        item.style.display = 'none';
                    }
                });
                renderCharts(selectedHouse);
            }
        });

        // Trigger chart updates
        togglePartitions.addEventListener('change', function() {
            if (houseFilter.value !== 'all') renderCharts(houseFilter.value);
        });

        chartStartWeek.addEventListener('change', function() {
            if (houseFilter.value !== 'all') renderCharts(houseFilter.value);
        });
    });
